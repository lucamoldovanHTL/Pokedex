"""Legt Demo-Trainer mit Favoriten und Teams an (setzt importierten Pokédex voraus).

    python manage.py load_demo
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from pokedex.models import Pokemon
from trainer.models import Favorite, Team, TeamMember

DEMO = {
    'ash': {
        'favorites': ['pikachu', 'charizard', 'greninja', 'lucario'],
        'teams': [
            ('Kanto-Klassiker', 'Mein erstes Team aus Alabastia', True,
             ['pikachu', 'charizard', 'blastoise', 'venusaur', 'snorlax', 'lapras']),
            ('Regen-Team', 'Wasser-Pokémon mit Niesel', False,
             ['pelipper', 'barraskewda', 'ferrothorn', 'kingdra']),
        ],
    },
    'misty': {
        'favorites': ['starmie', 'psyduck', 'gyarados'],
        'teams': [('Wasser-Arena', 'Die Arenaleiterin von Azuria', True,
                   ['starmie', 'gyarados', 'lapras', 'vaporeon', 'golduck', 'politoed'])],
    },
}


class Command(BaseCommand):
    help = 'Erstellt Demo-Benutzer (Passwort: demo1234) mit Favoriten und Teams.'

    def handle(self, *args, **options):
        if not Pokemon.objects.exists():
            raise CommandError('Zuerst den Pokédex importieren: python manage.py import_pokedex')
        pokemon = {p.identifier: p for p in Pokemon.objects.filter(
            identifier__in={i for d in DEMO.values() for i in d['favorites'] + [x for t in d['teams'] for x in t[3]]})}

        for username, data in DEMO.items():
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password('demo1234')
                user.save()
            user.teams.all().delete()
            user.favorites.all().delete()
            Favorite.objects.bulk_create(Favorite(user=user, pokemon=pokemon[i]) for i in data['favorites'] if i in pokemon)
            for name, desc, public, members in data['teams']:
                team = Team.objects.create(user=user, name=name, description=desc, is_public=public)
                TeamMember.objects.bulk_create(
                    TeamMember(team=team, pokemon=pokemon[i], slot=slot)
                    for slot, i in enumerate((m for m in members if m in pokemon), 1))
            self.stdout.write(f'  - {username} / demo1234')
        self.stdout.write(self.style.SUCCESS('Demo-Daten angelegt.'))
