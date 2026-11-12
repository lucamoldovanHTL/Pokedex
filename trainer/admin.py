from django.contrib import admin

from .models import Favorite, Team, TeamMember


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    raw_id_fields = ['pokemon']
    exclude = ['moves']


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_public', 'is_boss', 'updated_at']
    list_filter = ['is_public', 'is_boss']
    search_fields = ['name', 'user__username']
    inlines = [TeamMemberInline]


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'pokemon', 'created_at']
    raw_id_fields = ['pokemon']
