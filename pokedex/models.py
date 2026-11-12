"""
Datenmodell des Pokédex.

Im Gegensatz zum A20-Projekt (managed=False, nur IntegerFields) ist das hier ein
normalisiertes Schema mit echten Fremdschlüsseln. Befüllt wird es mit
`python manage.py import_pokedex` aus den CSV-Dateien in data/csv/.
Texte werden bevorzugt auf Deutsch gespeichert (Fallback: Englisch).
"""
from django.db import models
from django.urls import reverse

ARTWORK_URL = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{}.png'
SPRITE_URL = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{}.png'

# Typfarben für Badges (Hex)
TYPE_COLORS = {
    'normal': '#9fa19f', 'fighting': '#ff8000', 'flying': '#81b9ef', 'poison': '#9141cb',
    'ground': '#915121', 'rock': '#afa981', 'bug': '#91a119', 'ghost': '#704170',
    'steel': '#60a1b8', 'fire': '#e62829', 'water': '#2980ef', 'grass': '#3fa129',
    'electric': '#fac000', 'psychic': '#ef4179', 'ice': '#3dcef3', 'dragon': '#5060e1',
    'dark': '#624d4e', 'fairy': '#ef70ef',
}


class Generation(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    identifier = models.CharField(max_length=40)
    name = models.CharField(max_length=60)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Type(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    identifier = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=60)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name

    @property
    def color(self):
        return TYPE_COLORS.get(self.identifier, '#888888')


class TypeEfficacy(models.Model):
    """Schadensmultiplikator in Prozent (0, 50, 100, 200)."""
    attacker = models.ForeignKey(Type, on_delete=models.CASCADE, related_name='efficacy_attacking')
    defender = models.ForeignKey(Type, on_delete=models.CASCADE, related_name='efficacy_defending')
    factor = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('attacker', 'defender')
        verbose_name_plural = 'Type efficacies'


class Ability(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    identifier = models.CharField(max_length=80)
    name = models.CharField(max_length=80)
    generation = models.ForeignKey(Generation, on_delete=models.PROTECT)
    short_effect = models.TextField(blank=True)
    flavor_text = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Abilities'

    def __str__(self):
        return self.name


class DamageClass(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    identifier = models.CharField(max_length=20)

    LABELS = {'status': 'Status', 'physical': 'Physisch', 'special': 'Speziell'}

    def __str__(self):
        return self.LABELS.get(self.identifier, self.identifier)


class Move(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    identifier = models.CharField(max_length=80)
    name = models.CharField(max_length=80)
    generation = models.ForeignKey(Generation, on_delete=models.PROTECT)
    type = models.ForeignKey(Type, on_delete=models.PROTECT, related_name='moves')
    damage_class = models.ForeignKey(DamageClass, on_delete=models.PROTECT, null=True)
    power = models.PositiveSmallIntegerField(null=True, blank=True)
    pp = models.PositiveSmallIntegerField(null=True, blank=True)
    accuracy = models.PositiveSmallIntegerField(null=True, blank=True)
    priority = models.SmallIntegerField(default=0)
    flavor_text = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class MoveMethod(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    identifier = models.CharField(max_length=40)
    name = models.CharField(max_length=60)

    def __str__(self):
        return self.name


class Species(models.Model):
    id = models.PositiveIntegerField(primary_key=True)  # = National-Dex-Nummer
    identifier = models.CharField(max_length=80)
    name = models.CharField(max_length=80, db_index=True)
    genus = models.CharField(max_length=80, blank=True)
    generation = models.ForeignKey(Generation, on_delete=models.PROTECT, related_name='species')
    evolves_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='evolves_to')
    evolution_chain_id = models.PositiveIntegerField(null=True, db_index=True)
    capture_rate = models.PositiveSmallIntegerField(default=0)
    base_happiness = models.PositiveSmallIntegerField(null=True)
    gender_rate = models.SmallIntegerField(default=-1)  # -1 = geschlechtslos, sonst Achtel weiblich
    is_baby = models.BooleanField(default=False)
    is_legendary = models.BooleanField(default=False)
    is_mythical = models.BooleanField(default=False)
    flavor_text = models.TextField(blank=True)
    # Evolutionsbedingung (wie entsteht diese Art aus evolves_from)
    evolution_trigger = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name_plural = 'Species'

    def __str__(self):
        return self.name

    @property
    def female_percent(self):
        return None if self.gender_rate < 0 else self.gender_rate * 12.5

    @property
    def male_percent(self):
        return None if self.gender_rate < 0 else 100 - self.gender_rate * 12.5


class PokemonQuerySet(models.QuerySet):
    def with_relations(self):
        return self.select_related('species').prefetch_related('pokemon_types__type')


class Pokemon(models.Model):
    """Ein konkretes Pokémon bzw. eine Form (z. B. Alola-Vulpix, Mega-Glurak)."""
    id = models.PositiveIntegerField(primary_key=True)
    identifier = models.CharField(max_length=80, unique=True)
    species = models.ForeignKey(Species, on_delete=models.CASCADE, related_name='varieties')
    form_name = models.CharField(max_length=80, blank=True)
    height = models.PositiveIntegerField(help_text='in Dezimetern')
    weight = models.PositiveIntegerField(help_text='in Hektogramm')
    base_experience = models.PositiveIntegerField(null=True)
    order = models.IntegerField(default=0)
    is_default = models.BooleanField(default=True)

    hp = models.PositiveSmallIntegerField(default=0)
    attack = models.PositiveSmallIntegerField(default=0)
    defense = models.PositiveSmallIntegerField(default=0)
    special_attack = models.PositiveSmallIntegerField(default=0)
    special_defense = models.PositiveSmallIntegerField(default=0)
    speed = models.PositiveSmallIntegerField(default=0)
    total = models.PositiveSmallIntegerField(default=0, db_index=True)

    abilities = models.ManyToManyField(Ability, through='PokemonAbility', related_name='pokemon')
    moves = models.ManyToManyField(Move, through='PokemonMove', related_name='pokemon')

    objects = PokemonQuerySet.as_manager()

    class Meta:
        ordering = ['species_id', 'order']
        verbose_name_plural = 'Pokemon'

    def __str__(self):
        return self.display_name

    def get_absolute_url(self):
        return reverse('pokedex:detail', args=[self.identifier])

    @property
    def display_name(self):
        if self.form_name and not self.is_default:
            if self.species.name in self.form_name:  # z. B. „Mega-Glurak X“
                return self.form_name
            return f'{self.species.name} ({self.form_name})'
        return self.species.name

    @property
    def dex_number(self):
        return f'#{self.species_id:04d}'

    @property
    def artwork(self):
        return ARTWORK_URL.format(self.id)

    @property
    def sprite(self):
        return SPRITE_URL.format(self.id)

    @property
    def types(self):
        # nutzt den Prefetch-Cache, wenn vorhanden
        return [pt.type for pt in sorted(self.pokemon_types.all(), key=lambda pt: pt.slot)]

    @property
    def height_m(self):
        return self.height / 10

    @property
    def weight_kg(self):
        return self.weight / 10

    STAT_FIELDS = [
        ('hp', 'KP'), ('attack', 'Angriff'), ('defense', 'Verteidigung'),
        ('special_attack', 'Sp.-Angriff'), ('special_defense', 'Sp.-Verteidigung'), ('speed', 'Initiative'),
    ]

    @property
    def stats(self):
        return [{'key': k, 'label': label, 'value': getattr(self, k)} for k, label in self.STAT_FIELDS]


class PokemonType(models.Model):
    pokemon = models.ForeignKey(Pokemon, on_delete=models.CASCADE, related_name='pokemon_types')
    type = models.ForeignKey(Type, on_delete=models.CASCADE, related_name='pokemon_types')
    slot = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('pokemon', 'slot')
        ordering = ['slot']


class PokemonAbility(models.Model):
    pokemon = models.ForeignKey(Pokemon, on_delete=models.CASCADE, related_name='pokemon_abilities')
    ability = models.ForeignKey(Ability, on_delete=models.CASCADE)
    is_hidden = models.BooleanField(default=False)
    slot = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['slot']


class PokemonMove(models.Model):
    """Nur die Attacken aus der neuesten Editionsgruppe, in der das Pokémon vorkommt."""
    pokemon = models.ForeignKey(Pokemon, on_delete=models.CASCADE, related_name='pokemon_moves')
    move = models.ForeignKey(Move, on_delete=models.CASCADE)
    method = models.ForeignKey(MoveMethod, on_delete=models.CASCADE)
    level = models.PositiveSmallIntegerField(default=0)
    version_group = models.CharField(max_length=60)

    class Meta:
        ordering = ['method_id', 'level']
