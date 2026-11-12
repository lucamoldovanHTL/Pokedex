from django.contrib import admin

from .models import Battle, Rating


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'elo', 'wins', 'losses', 'draws']
    search_fields = ['user__username']


@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = ['id', 'player1', 'player2', 'status', 'winner', 'reason', 'created_at']
    list_filter = ['status', 'reason']
    raw_id_fields = ['player1', 'player2', 'invited', 'team1', 'team2', 'winner']
