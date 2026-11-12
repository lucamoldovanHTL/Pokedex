from django.test import TestCase
from django.urls import reverse

from .models import Generation, Pokemon, PokemonType, Species, Type, TypeEfficacy
from .typechart import defensive_profile, simulate_battle, team_analysis


def make_pokemon(pid, ident, name, types, gen, **stats):
    species = Species.objects.create(id=pid, identifier=ident, name=name, generation=gen)
    base = dict(hp=50, attack=50, defense=50, special_attack=50, special_defense=50, speed=50)
    base.update(stats)
    p = Pokemon.objects.create(id=pid, identifier=ident, species=species, height=10, weight=100,
                               total=sum(base.values()), **base)
    for slot, t in enumerate(types, 1):
        PokemonType.objects.create(pokemon=p, type=t, slot=slot)
    return p


class PokedexTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        gen = Generation.objects.create(id=1, identifier='generation-i', name='Generation I')
        cls.fire = Type.objects.create(id=10, identifier='fire', name='Feuer')
        cls.water = Type.objects.create(id=11, identifier='water', name='Wasser')
        cls.grass = Type.objects.create(id=12, identifier='grass', name='Pflanze')
        chart = {(10, 10): 50, (10, 11): 50, (10, 12): 200,
                 (11, 10): 200, (11, 11): 50, (11, 12): 50,
                 (12, 10): 50, (12, 11): 200, (12, 12): 50}
        for (a, d), f in chart.items():
            TypeEfficacy.objects.create(attacker_id=a, defender_id=d, factor=f)
        cls.glumanda = make_pokemon(4, 'charmander', 'Glumanda', [cls.fire], gen, speed=65)
        cls.schiggy = make_pokemon(7, 'squirtle', 'Schiggy', [cls.water], gen, defense=65)
        cls.bisasam = make_pokemon(1, 'bulbasaur', 'Bisasam', [cls.grass], gen)


class TypeChartTests(PokedexTestData):
    def test_defensive_profile(self):
        groups = {label: [t.identifier for t in ts] for label, _, ts in defensive_profile([self.fire])}
        self.assertEqual(groups['2×'], ['water'])
        self.assertCountEqual(groups['½×'], ['fire', 'grass'])

    def test_battle_type_advantage_wins(self):
        result = simulate_battle(self.glumanda, self.schiggy)
        self.assertEqual(result['winner'], self.schiggy)
        self.assertEqual(result['atk_b']['effectiveness'], 2.0)

    def test_team_analysis_coverage(self):
        analysis = team_analysis([self.glumanda, self.schiggy, self.bisasam])
        self.assertEqual(analysis['uncovered'], [])
        fire_row = next(r for r in analysis['rows'] if r['type'] == self.fire)
        self.assertEqual(fire_row['weak'], 1)


class ViewTests(PokedexTestData):
    def test_list_and_search(self):
        r = self.client.get(reverse('pokedex:list'), {'q': 'schig'})
        self.assertContains(r, 'Schiggy')
        self.assertNotContains(r, 'Glumanda')

    def test_search_by_number(self):
        r = self.client.get(reverse('pokedex:list'), {'q': '#4'})
        self.assertContains(r, 'Glumanda')
        self.assertEqual(r.context['page'].paginator.count, 1)

    def test_type_filter(self):
        r = self.client.get(reverse('pokedex:list'), {'type': 'grass'})
        self.assertEqual([p.identifier for p in r.context['page']], ['bulbasaur'])

    def test_detail(self):
        r = self.client.get(reverse('pokedex:detail', args=['charmander']))
        self.assertContains(r, 'Glumanda')
        self.assertContains(r, 'Basiswerte')

    def test_detail_404(self):
        self.assertEqual(self.client.get('/pokedex/missingno/').status_code, 404)

    def test_battle_page(self):
        r = self.client.get(reverse('pokedex:battle'), {'a': 'charmander', 'b': 'bulbasaur'})
        self.assertContains(r, 'Glumanda gewinnt')

    def test_api_search(self):
        r = self.client.get(reverse('pokedex:api_search'), {'q': 'bisa'})
        self.assertEqual(r.json()['results'][0]['identifier'], 'bulbasaur')

    def test_home_and_types(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertContains(self.client.get(reverse('pokedex:types')), 'Typen-Tabelle')
