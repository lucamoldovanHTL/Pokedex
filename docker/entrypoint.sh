#!/bin/sh
set -e

echo "==> Migrationen ausführen"
python manage.py migrate --noinput

echo "==> Pokédex importieren (nur beim ersten Start)"
python manage.py import_pokedex --if-empty

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> Admin-Benutzer sicherstellen"
    python manage.py createsuperuser --noinput 2>/dev/null || echo "    Admin existiert bereits."
fi

echo "==> Admin-Team sicherstellen"
python manage.py setup_boss_team

if [ "$LOAD_DEMO_DATA" = "1" ]; then
    echo "==> Demo-Daten laden"
    python manage.py load_demo
fi

exec "$@"
