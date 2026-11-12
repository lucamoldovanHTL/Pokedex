"""
Django-Einstellungen für den Pokédex.

Alles, was sich zwischen lokal und Server unterscheidet, kommt aus Umgebungsvariablen
(siehe .env.example). Ohne Variablen läuft das Projekt lokal mit SQLite im DEBUG-Modus.
"""
import os
from pathlib import Path

import dj_database_url
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [v.strip() for v in os.environ.get(name, default).split(',') if v.strip()]


DEBUG = env_bool('DJANGO_DEBUG', True)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-nur-fuer-lokale-entwicklung')
if not DEBUG and SECRET_KEY.startswith('django-insecure'):
    raise RuntimeError('DJANGO_SECRET_KEY muss in Produktion gesetzt sein.')

ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'pokedex',
    'trainer',
    'arena',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'config.security.RejectNullBytesMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Lokal: SQLite. Server: DATABASE_URL=postgres://user:pass@host:5432/dbname
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'de-at'
TIME_ZONE = 'Europe/Vienna'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG
        else 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Login-Bremse (config/security.py) zuerst, danach die normale Passwortprüfung
AUTHENTICATION_BACKENDS = [
    'config.security.LoginThrottleBackend',
    'django.contrib.auth.backends.ModelBackend',
]
BEHIND_PROXY = not DEBUG  # am Server steht Caddy davor (X-Forwarded-For)
if not DEBUG:
    # gemeinsamer Zähler für alle Gunicorn-Worker
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
                          'LOCATION': '/tmp/pokedex-cache'}}

# Content-Security-Policy: nur eigene Dateien, Bootstrap-CDN und die Pokémon-Bilder
SECURE_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.UNSAFE_INLINE, 'https://cdn.jsdelivr.net'],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE, 'https://cdn.jsdelivr.net'],
    'font-src': [CSP.SELF, 'https://cdn.jsdelivr.net'],
    'img-src': [CSP.SELF, 'data:', 'https://raw.githubusercontent.com'],
    'connect-src': [CSP.SELF],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

LOGIN_URL = 'trainer:login'
LOGIN_REDIRECT_URL = 'pokedex:home'
LOGOUT_REDIRECT_URL = 'pokedex:home'

# Sicherheit hinter einem Reverse-Proxy (Caddy) mit HTTPS
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', True)
    CSRF_COOKIE_SECURE = env_bool('DJANGO_SECURE_COOKIES', True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    CSRF_COOKIE_HTTPONLY = True
    # HTTP→HTTPS-Weiterleitung übernimmt Caddy (docker/Caddyfile)
    SILENCED_SYSTEM_CHECKS = ['security.W008']

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
