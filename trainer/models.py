from django.conf import settings
from django.db import models
from django.urls import reverse

from pokedex.models import Move, Pokemon

MAX_TEAM_SIZE = 6


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    pokemon = models.ForeignKey(Pokemon, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'pokemon')
        ordering = ['pokemon__species_id', 'pokemon__order']

    def __str__(self):
        return f'{self.user} ♥ {self.pokemon}'


class Team(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField('Teamname', max_length=60)
    description = models.CharField('Beschreibung', max_length=200, blank=True)
    is_public = models.BooleanField('Öffentlich sichtbar', default=False)
    # Geheimes Admin-Team: in der Arena unbesiegbar, wirkt nur bei Superusern (siehe arena/engine.py)
    is_boss = models.BooleanField('Admin-Team (unbesiegbar)', default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('trainer:team_detail', args=[self.pk])

    @property
    def is_full(self):
        return self.members.count() >= MAX_TEAM_SIZE


class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    pokemon = models.ForeignKey(Pokemon, on_delete=models.CASCADE)
    nickname = models.CharField('Spitzname', max_length=30, blank=True)
    slot = models.PositiveSmallIntegerField()
    # Bis zu 4 vorab gewählte Attacken für die Arena (leer = automatische Auswahl)
    moves = models.ManyToManyField(Move, blank=True, related_name='+')

    class Meta:
        ordering = ['slot']
        unique_together = ('team', 'slot')

    def __str__(self):
        return self.nickname or str(self.pokemon)
