from django.contrib.auth.models import User
from django.urls import reverse

from pokedex.tests import PokedexTestData

from .models import Favorite, Team


class TrainerTests(PokedexTestData):
    def setUp(self):
        self.user = User.objects.create_user('ash', password='pikachu-2026!')
        self.client.force_login(self.user)

    def test_signup(self):
        self.client.logout()
        r = self.client.post(reverse('trainer:signup'), {
            'username': 'misty', 'email': '', 'password1': 'Starmie-123!', 'password2': 'Starmie-123!'})
        self.assertRedirects(r, reverse('trainer:dashboard'))
        self.assertTrue(User.objects.filter(username='misty').exists())

    def test_dashboard_requires_login(self):
        self.client.logout()
        r = self.client.get(reverse('trainer:dashboard'))
        self.assertEqual(r.status_code, 302)

    def test_toggle_favorite(self):
        url = reverse('trainer:toggle_favorite', args=[self.glumanda.id])
        self.client.post(url)
        self.assertTrue(Favorite.objects.filter(user=self.user, pokemon=self.glumanda).exists())
        self.client.post(url)
        self.assertFalse(Favorite.objects.exists())

    def test_team_flow(self):
        r = self.client.post(reverse('trainer:team_create'), {'name': 'Starter'})
        team = Team.objects.get(user=self.user)
        self.assertRedirects(r, team.get_absolute_url())
        for ident in ['charmander', 'squirtle', 'bulbasaur']:
            self.client.post(reverse('trainer:team_add', args=[team.pk]), {'pokemon': ident})
        self.assertEqual(team.members.count(), 3)
        r = self.client.get(team.get_absolute_url())
        self.assertContains(r, 'Defensive Analyse')
        member = team.members.first()
        self.client.post(reverse('trainer:team_remove', args=[team.pk, member.pk]))
        self.assertEqual(team.members.count(), 2)

    def test_team_max_six(self):
        team = Team.objects.create(user=self.user, name='Voll')
        for _ in range(7):
            self.client.post(reverse('trainer:team_add', args=[team.pk]), {'pokemon': 'charmander'})
        self.assertEqual(team.members.count(), 6)

    def test_private_team_hidden_from_others(self):
        team = Team.objects.create(user=self.user, name='Geheim')
        other = User.objects.create_user('gary', password='eevee-2026!')
        self.client.force_login(other)
        self.assertEqual(self.client.get(team.get_absolute_url()).status_code, 404)
        # fremdes Team darf nicht verändert werden
        self.client.post(reverse('trainer:team_add', args=[team.pk]), {'pokemon': 'charmander'})
        self.assertEqual(team.members.count(), 0)
        team.is_public = True
        team.save()
        self.assertEqual(self.client.get(team.get_absolute_url()).status_code, 200)
