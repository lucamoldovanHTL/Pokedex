"""Schutzmaßnahmen: Login-Bremse gegen Passwort-Raten, Anfrage-Limits, Null-Byte-Filter.

Die Login-Bremse hängt als erstes Backend in AUTHENTICATION_BACKENDS und gilt damit für
jeden Login-Weg (Trainer-Login und /admin/). Gezählt werden nur Fehlversuche.
"""
import hashlib
import logging
import time

from django.conf import settings
from django.contrib.auth.signals import user_login_failed
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver
from django.http import HttpResponseBadRequest

logger = logging.getLogger('security')

WINDOW = 300            # Sekunden
MAX_PER_ACCOUNT = 5     # Fehlversuche pro IP + Benutzername
MAX_PER_IP = 30         # Fehlversuche pro IP insgesamt


def client_ip(request):
    if request is None:
        return 'unknown'
    if getattr(settings, 'BEHIND_PROXY', False):
        # Caddy hängt die echte Client-IP als letzten Eintrag an
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _key(scope, *parts):
    digest = hashlib.sha256('|'.join(str(p).lower() for p in parts).encode()).hexdigest()[:32]
    return f'throttle:{scope}:{digest}'


def _count(key, window):
    entry = cache.get(key)
    if not entry or time.time() - entry[1] > window:
        return 0
    return entry[0]


def _hit(key, window):
    now = time.time()
    entry = cache.get(key)
    if not entry or now - entry[1] > window:
        entry = (0, now)
    cache.set(key, (entry[0] + 1, entry[1]), window)


def rate_limited(request, scope, limit, window):
    """Zählt einen Aufruf pro IP und liefert True, sobald das Limit im Zeitfenster überschritten ist."""
    key = _key(scope, client_ip(request))
    if _count(key, window) >= limit:
        return True
    _hit(key, window)
    return False


class LoginThrottleBackend:
    """Blockiert weitere Login-Versuche nach zu vielen Fehlversuchen (prüft selbst keine Passwörter)."""

    def authenticate(self, request, username=None, **kwargs):
        ip = client_ip(request)
        name = username or kwargs.get('email') or ''
        if (_count(_key('login', ip, name), WINDOW) >= MAX_PER_ACCOUNT
                or _count(_key('login-ip', ip), WINDOW) >= MAX_PER_IP):
            if request is not None:
                request.login_throttled = True
            logger.warning('Login gesperrt (zu viele Fehlversuche): ip=%s benutzer=%r', ip, name[:150])
            raise PermissionDenied
        return None


@receiver(user_login_failed)
def _count_failed_login(sender, credentials, request=None, **kwargs):
    ip = client_ip(request)
    name = credentials.get('username') or credentials.get('email') or ''
    _hit(_key('login', ip, name), WINDOW)
    _hit(_key('login-ip', ip), WINDOW)
    logger.warning('Fehlgeschlagener Login: ip=%s benutzer=%r', ip, str(name)[:150])


class RejectNullBytesMiddleware:
    """PostgreSQL verträgt keine Null-Bytes in Texten – solche Anfragen sofort mit 400 ablehnen."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '\x00' in request.META.get('QUERY_STRING', '') or '%00' in request.META.get('QUERY_STRING', ''):
            return HttpResponseBadRequest('Ungültige Anfrage.')
        if request.method == 'POST' and request.content_type in ('application/x-www-form-urlencoded',
                                                                 'multipart/form-data'):
            for values in request.POST.lists():
                if any('\x00' in v for v in values[1]) or '\x00' in values[0]:
                    return HttpResponseBadRequest('Ungültige Anfrage.')
        return self.get_response(request)
