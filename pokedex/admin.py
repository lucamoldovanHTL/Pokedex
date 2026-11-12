from django.contrib import admin

from .models import Ability, Generation, Move, Pokemon, PokemonAbility, PokemonType, Species, Type


class PokemonTypeInline(admin.TabularInline):
    model = PokemonType
    extra = 0


class PokemonAbilityInline(admin.TabularInline):
    model = PokemonAbility
    extra = 0
    autocomplete_fields = ['ability']


@admin.register(Pokemon)
class PokemonAdmin(admin.ModelAdmin):
    list_display = ['id', 'identifier', 'species', 'form_name', 'is_default', 'total']
    list_filter = ['is_default', 'species__generation', 'pokemon_types__type']
    search_fields = ['identifier', 'species__name', 'form_name']
    list_select_related = ['species']
    inlines = [PokemonTypeInline, PokemonAbilityInline]
    raw_id_fields = ['species']


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'genus', 'generation', 'is_legendary', 'is_mythical']
    list_filter = ['generation', 'is_legendary', 'is_mythical', 'is_baby']
    search_fields = ['name', 'identifier']
    raw_id_fields = ['evolves_from']


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'type', 'damage_class', 'power', 'accuracy', 'pp']
    list_filter = ['type', 'damage_class', 'generation']
    search_fields = ['name', 'identifier']


@admin.register(Ability)
class AbilityAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'generation']
    search_fields = ['name', 'identifier']


admin.site.register(Type)
admin.site.register(Generation)
