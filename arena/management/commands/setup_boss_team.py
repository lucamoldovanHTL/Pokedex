"""Legt für jeden Superuser das geheime Admin-Team an (nur einmal).

    python manage.py setup_boss_team

Das Team sieht harmlos aus, ist in der Arena aber unbesiegbar: seine Pokémon greifen immer
zuerst an, besiegen den Gegner mit einem Treffer und behalten selbst immer mindestens 1 KP.
Das gilt nur, solange das Team einem Superuser gehört (Team.is_boss).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from pokedex.models import Pokemon
from trainer.models import Team, TeamMember

BOSS_TEAM = ['magikarp', 'feebas', 'sunkern', 'caterpie', 'wooper', 'bidoof']


class Command(BaseCommand):
    help = 'Erstellt das unbesiegbare Admin-Team für alle Superuser (falls noch nicht vorhanden).'

    def handle(self, *args, **options):
        pokemon = {p.identifier: p for p in Pokemon.objects.filter(identifier__in=BOSS_TEAM)}
        if not pokemon:
            self.stdout.write('  Pokedex ist leer - Admin-Team uebersprungen.')
            return
        for user in get_user_model().objects.filter(is_superuser=True):
            if Team.objects.filter(user=user, is_boss=True).exists():
                self.stdout.write(f'  - {user.username}: Admin-Team existiert bereits.')
                continue
            team = Team.objects.create(user=user, name='Teichfreunde', is_boss=True, is_public=False,
                                       description='Harmlose kleine Freunde vom Teich.')
            TeamMember.objects.bulk_create(
                TeamMember(team=team, pokemon=pokemon[i], slot=slot)
                for slot, i in enumerate((i for i in BOSS_TEAM if i in pokemon), 1))
            self.stdout.write(self.style.SUCCESS(f'  - {user.username}: Admin-Team angelegt.'))
