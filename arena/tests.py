import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from pokedex.models import DamageClass, Generation, Move, MoveMethod, PokemonMove
from pokedex.tests import PokedexTestData
from pokedex.typechart import load_chart
from trainer.models import Team, TeamMember

from . import engine
from .models import Battle, Rating


class ArenaTestData(PokedexTestData):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        gen = Generation.objects.get(id=1)
        special = DamageClass.objects.create(id=3, identifier='special')
        method = MoveMethod.objects.create(id=1, identifier='level-up', name='Level')
        cls.moves = {}
        for mid, (ident, type_, power) in enumerate([('ember', cls.fire, 40), ('flamethrower', cls.fire, 90),
                                                     ('water-gun', cls.water, 40), ('surf', cls.water, 90),
                                                     ('hyper-beam', cls.fire, 150)], 1):
            cls.moves[ident] = Move.objects.create(id=mid, identifier=ident, name=ident.title(), generation=gen,
                                                   type=type_, damage_class=special, power=power, accuracy=100)
        for pokemon, idents in ((cls.glumanda, ['ember', 'flamethrower', 'hyper-beam']),
                                (cls.schiggy, ['water-gun', 'surf'])):
            for ident in idents:
                PokemonMove.objects.create(pokemon=pokemon, move=cls.moves[ident], method=method, version_group='x')

        cls.ash = User.objects.create_user('ash', password='pikachu-2026!')
        cls.misty = User.objects.create_user('misty', password='starmie-2026!')
        cls.admin = User.objects.create_superuser('admin', password='admin-2026!')
        cls.team_ash = cls.make_team(cls.ash, [cls.glumanda, cls.bisasam])
        cls.team_misty = cls.make_team(cls.misty, [cls.schiggy])
        cls.team_boss = cls.make_team(cls.admin, [cls.bisasam], is_boss=True)

    @staticmethod
    def make_team(user, pokemon, **kwargs):
        team = Team.objects.create(user=user, name=f'Team {user.username}', **kwargs)
        for slot, p in enumerate(pokemon, 1):
            TeamMember.objects.create(team=team, pokemon=p, slot=slot)
        return team


class EngineTests(ArenaTestData):
    def play(self, state, a0, a1, seed=1):
        rng, chart = random.Random(seed), load_chart()[1]
        engine.submit(state, 0, a0, chart, rng)
        return engine.submit(state, 1, a1, chart, rng)

    def test_learnset_excludes_banned_moves(self):
        names = [m.identifier for m in engine.learnset(self.glumanda)]
        self.assertEqual(names, ['flamethrower', 'ember'])

    def test_chosen_moves_are_used(self):
        member = self.team_ash.members.get(slot=1)
        member.moves.set([self.moves['ember']])
        side = engine.build_side(self.ash, self.team_ash)
        self.assertEqual([m['name'] for m in side['mons'][0]['moves']], ['Ember'])
        self.assertEqual(side['mons'][1]['moves'][0]['name'], 'Verzweifler')  # Bisasam hat keine Attacken

    def test_turn_resolves_when_both_chose(self):
        state = engine.new_state(self.ash, self.team_ash, self.misty, self.team_misty)
        chart = load_chart()[1]
        self.assertFalse(engine.submit(state, 0, {'type': 'move', 'i': 0}, chart, random.Random(1)))
        self.assertTrue(engine.submit(state, 1, {'type': 'move', 'i': 0}, chart, random.Random(1)))
        self.assertEqual(state['turn'], 2)
        self.assertLess(engine.active(state, 0)['hp'], engine.active(state, 0)['max_hp'])

    def test_knockout_forces_switch_and_ends_battle(self):
        state = engine.new_state(self.ash, self.team_ash, self.misty, self.team_misty)
        while engine.loser(state) is None:
            if engine.is_forced(state):
                side = engine.needed(state)[0]
                self.assertIsNone(engine.valid_action(state, side, 'move', 0))
                engine.submit(state, side, engine.default_action(state, side), load_chart()[1])
            else:
                self.play(state, {'type': 'move', 'i': 0}, {'type': 'move', 'i': 0})
        self.assertIn(engine.loser(state), (0, 1))

    def test_boss_team_cannot_lose(self):
        state = engine.new_state(self.ash, self.team_ash, self.admin, self.team_boss)
        self.assertTrue(state['sides'][1]['boss'])
        for seed in range(30):
            if engine.loser(state) is not None:
                break
            if engine.is_forced(state):
                side = engine.needed(state)[0]
                engine.submit(state, side, engine.default_action(state, side), load_chart()[1])
            else:
                self.play(state, {'type': 'move', 'i': 0}, {'type': 'move', 'i': 0}, seed)
        self.assertEqual(engine.loser(state), 0)
        self.assertGreater(engine.active(state, 1)['hp'], 0)

    def test_boss_flag_needs_superuser(self):
        self.team_ash.is_boss = True
        self.assertFalse(engine.build_side(self.ash, self.team_ash)['boss'])

    def test_elo_is_zero_sum(self):
        self.assertEqual(engine.elo_delta(1000, 1000, 1), 16)
        self.assertEqual(engine.elo_delta(1000, 1000, 0), -16)
        self.assertLess(engine.elo_delta(1400, 1000, 1), 16)


class ArenaViewTests(ArenaTestData):
    def setUp(self):
        self.c1, self.c2 = Client(), Client()
        self.c1.force_login(self.ash)
        self.c2.force_login(self.misty)

    def start(self):
        self.c1.post(reverse('arena:queue_join'), {'team': self.team_ash.pk})
        r = self.c2.post(reverse('arena:queue_join'), {'team': self.team_misty.pk})
        battle = Battle.objects.get()
        self.assertRedirects(r, battle.get_absolute_url())
        return battle

    def act(self, client, battle, kind='move', index=0):
        return client.post(reverse('arena:battle_action', args=[battle.pk]), {'type': kind, 'index': index})

    def test_lobby_requires_login(self):
        self.assertEqual(Client().get(reverse('arena:lobby')).status_code, 302)
        self.assertContains(self.c1.get(reverse('arena:lobby')), 'Gegner suchen')

    def test_queue_matches_two_trainers(self):
        battle = self.start()
        self.assertEqual(battle.status, Battle.ACTIVE)
        self.assertEqual((battle.player1, battle.player2), (self.ash, self.misty))
        data = self.c2.get(reverse('arena:battle_state', args=[battle.pk])).json()
        self.assertTrue(data['need_action'])
        self.assertEqual(data['you']['name'], 'misty')
        self.assertNotIn('moves', data['opp']['mons'][0])
        self.assertNotIn('boss', data['opp'])

    def test_full_battle_updates_ranking(self):
        battle = self.start()
        for _ in range(60):
            battle.refresh_from_db()
            if battle.status != Battle.ACTIVE:
                break
            for client, side in ((self.c1, 0), (self.c2, 1)):
                if side in engine.needed(battle.state):
                    kind = 'switch' if engine.is_forced(battle.state) else 'move'
                    index = engine.default_action(battle.state, side)['i']
                    self.act(client, battle, kind, index)
                    battle.refresh_from_db()
                    if battle.status != Battle.ACTIVE:
                        break
        self.assertEqual(battle.status, Battle.FINISHED)
        self.assertEqual(battle.reason, 'ko')
        winner, loser = Rating.objects.get(user=battle.winner), Rating.objects.exclude(user=battle.winner).get()
        self.assertEqual((winner.elo, loser.elo), (1016, 984))
        self.assertEqual((winner.wins, loser.losses), (1, 1))
        self.assertContains(self.client.get(reverse('arena:leaderboard')), battle.winner.username)
        result = self.c1.get(reverse('arena:battle_state', args=[battle.pk])).json()['result']
        self.assertEqual(result['won'], battle.winner == self.ash)

    def test_invalid_and_double_actions_are_rejected(self):
        battle = self.start()
        self.assertEqual(self.act(self.c1, battle, 'move', 9).status_code, 400)
        self.assertEqual(self.act(self.c1, battle, 'switch', 0).status_code, 400)
        self.assertEqual(self.act(self.c1, battle).status_code, 200)
        self.assertEqual(self.act(self.c1, battle).status_code, 400)

    def test_outsider_cannot_see_battle(self):
        battle = self.start()
        c3 = Client()
        c3.force_login(self.admin)
        self.assertEqual(c3.get(reverse('arena:battle_state', args=[battle.pk])).status_code, 404)
        self.assertEqual(self.act(c3, battle).status_code, 404)

    def test_challenge_accept(self):
        r = self.c1.post(reverse('arena:challenge'), {'opponent': 'MISTY', 'team': self.team_ash.pk})
        battle = Battle.objects.get()
        self.assertRedirects(r, battle.get_absolute_url())
        self.assertEqual(battle.invited, self.misty)
        self.assertContains(self.c2.get(reverse('arena:lobby')), 'fordert dich heraus')
        self.c2.post(reverse('arena:challenge_accept', args=[battle.pk]), {'team': self.team_misty.pk})
        battle.refresh_from_db()
        self.assertEqual(battle.status, Battle.ACTIVE)

    def test_challenge_is_not_matched_by_queue(self):
        self.c1.post(reverse('arena:challenge'), {'opponent': 'admin', 'team': self.team_ash.pk})
        self.c2.post(reverse('arena:queue_join'), {'team': self.team_misty.pk})
        self.assertEqual(Battle.objects.filter(status=Battle.OPEN).count(), 2)

    def test_forfeit_and_timeout(self):
        battle = self.start()
        self.c1.post(reverse('arena:battle_forfeit', args=[battle.pk]))
        battle.refresh_from_db()
        self.assertEqual((battle.status, battle.winner, battle.reason), (Battle.FINISHED, self.misty, 'forfeit'))

        battle = self.start_second()
        self.act(self.c1, battle)
        Battle.objects.filter(pk=battle.pk).update(turn_deadline=timezone.now() - timedelta(seconds=1))
        self.c1.get(reverse('arena:battle_state', args=[battle.pk]))
        battle.refresh_from_db()
        self.assertEqual((battle.status, battle.winner, battle.reason), (Battle.FINISHED, self.ash, 'timeout'))

    def start_second(self):
        self.c1.post(reverse('arena:queue_join'), {'team': self.team_ash.pk})
        self.c2.post(reverse('arena:queue_join'), {'team': self.team_misty.pk})
        return Battle.objects.filter(status=Battle.ACTIVE).get()

    def test_member_moves_selection(self):
        member = self.team_ash.members.get(slot=1)
        url = reverse('trainer:member_moves', args=[self.team_ash.pk, member.pk])
        self.assertContains(self.c1.get(url), 'Flamethrower')
        self.assertEqual(self.c2.get(url).status_code, 404)
        self.c1.post(url, {'moves': [self.moves['ember'].pk, self.moves['hyper-beam'].pk, self.moves['surf'].pk]})
        self.assertEqual(list(member.moves.all()), [self.moves['ember']])  # nur erlernbare, erlaubte Attacken
