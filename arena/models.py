"""Online-Kämpfe zwischen Trainern und die Rangliste (Elo-Wertung)."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from trainer.models import Team

START_ELO = 1000


class Rating(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='rating')
    elo = models.IntegerField(default=START_ELO, db_index=True)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-elo', '-wins']

    def __str__(self):
        return f'{self.user} ({self.elo})'

    @property
    def games(self):
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self):
        return round(self.wins / self.games * 100) if self.games else 0


class Battle(models.Model):
    OPEN, ACTIVE, FINISHED, CANCELLED = 'open', 'active', 'finished', 'cancelled'
    STATUS = [(OPEN, 'Wartet auf Gegner'), (ACTIVE, 'Läuft'), (FINISHED, 'Beendet'), (CANCELLED, 'Abgebrochen')]
    REASONS = {'ko': 'K.O.', 'forfeit': 'Aufgabe', 'timeout': 'Zeitüberschreitung'}

    player1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='battles_started')
    player2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='battles_joined')
    # gesetzt = gezielte Herausforderung, leer = Warteschlange
    invited = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='battle_invites')
    team1 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, related_name='+')
    team2 = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    status = models.CharField(max_length=10, choices=STATUS, default=OPEN, db_index=True)
    state = models.JSONField(default=dict, blank=True)
    winner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='battles_won')
    reason = models.CharField(max_length=10, blank=True)
    elo_change1 = models.IntegerField(default=0)
    elo_change2 = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now_add=True)  # Lebenszeichen von Spieler 1, solange er wartet
    turn_deadline = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Kampf #{self.pk}: {self.player1} vs. {self.player2 or "?"}'

    def get_absolute_url(self):
        return reverse('arena:battle', args=[self.pk])

    @property
    def reason_label(self):
        return self.REASONS.get(self.reason, '')

    def side_of(self, user):
        if user.id == self.player1_id:
            return 0
        if user.id == self.player2_id:
            return 1
        return None
