from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .security import MAX_PER_ACCOUNT


class SecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('ash', password='pikachu-2026!')
        self.login_url = reverse('trainer:login')

    def tearDown(self):
        cache.clear()

    def test_login_still_works(self):
        r = self.client.post(self.login_url, {'username': 'ash', 'password': 'pikachu-2026!'})
        self.assertEqual(r.status_code, 302)

    def test_login_is_blocked_after_too_many_failures(self):
        for _ in range(MAX_PER_ACCOUNT):
            self.client.post(self.login_url, {'username': 'ash', 'password': 'falsch'})
        r = self.client.post(self.login_url, {'username': 'ash', 'password': 'pikachu-2026!'})
        self.assertEqual(r.status_code, 200)  # trotz richtigem Passwort nicht eingeloggt
        self.assertContains(r, 'Zu viele Fehlversuche')
        self.assertNotIn('_auth_user_id', self.client.session)
        # andere Konten vom selben Gerät sind nicht betroffen
        User.objects.create_user('misty', password='starmie-2026!')
        r = self.client.post(self.login_url, {'username': 'misty', 'password': 'starmie-2026!'})
        self.assertEqual(r.status_code, 302)

    def test_admin_login_is_throttled_too(self):
        url = reverse('admin:login')
        for _ in range(MAX_PER_ACCOUNT):
            self.client.post(url, {'username': 'ash', 'password': 'falsch'})
        self.client.post(url, {'username': 'ash', 'password': 'pikachu-2026!'})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_signup_logs_in_and_is_rate_limited(self):
        url = reverse('trainer:signup')
        for i in range(5):
            r = self.client.post(url, {'username': f'neu{i}', 'email': '',
                                       'password1': 'Starmie-123!', 'password2': 'Starmie-123!'})
            self.assertEqual(r.status_code, 302)
            self.assertIn('_auth_user_id', self.client.session)
            self.client.logout()
        r = self.client.post(url, {'username': 'neu9', 'email': '',
                                   'password1': 'Starmie-123!', 'password2': 'Starmie-123!'})
        self.assertEqual(r.status_code, 429)
        self.assertFalse(User.objects.filter(username='neu9').exists())

    def test_null_bytes_are_rejected(self):
        self.assertEqual(self.client.get('/pokedex/?q=a%00b').status_code, 400)
        self.assertEqual(self.client.post(self.login_url, {'username': 'a\x00', 'password': 'x'}).status_code, 400)

    def test_bad_numbers_do_not_crash(self):
        for limit in ('abc', '-5', '99999999999999999999', ''):
            self.assertEqual(self.client.get(reverse('pokedex:api_search'), {'limit': limit}).status_code, 200)
        self.client.force_login(self.user)
        r = self.client.post(reverse('arena:queue_join'), {'team': 'abc'})
        self.assertRedirects(r, reverse('arena:lobby'))

    def test_security_headers(self):
        r = self.client.get(reverse('pokedex:home'))
        self.assertIn("frame-ancestors 'none'", r['Content-Security-Policy'])
        self.assertEqual(r['X-Frame-Options'], 'DENY')
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
