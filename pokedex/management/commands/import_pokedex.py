"""
Importiert den Pokédex aus dem CSV-Export (veekun-Format, Trennzeichen ';')
in die eigenen Django-Models.

    python manage.py import_pokedex                  # alles neu importieren
    python manage.py import_pokedex --if-empty       # nur wenn DB noch leer ist (Docker)
"""
import csv
import re
import time
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pokedex.models import (
    Ability, DamageClass, Generation, Move, MoveMethod, Pokemon, PokemonAbility,
    PokemonMove, PokemonType, Species, Type, TypeEfficacy,
)

GERMAN, ENGLISH = '6', '9'
STAT_FIELDS = {'1': 'hp', '2': 'attack', '3': 'defense', '4': 'special_attack',
               '5': 'special_defense', '6': 'speed'}
MARKUP_RE = re.compile(r'\[([^\]]*)\]\{[^:}]+:([^}]+)\}')
ROMAN = {'i': 'I', 'ii': 'II', 'iii': 'III', 'iv': 'IV', 'v': 'V', 'vi': 'VI',
         'vii': 'VII', 'viii': 'VIII', 'ix': 'IX'}


def clean_text(text):
    """Entfernt Zeilenumbrüche/Steuerzeichen aus Spieltexten und veekun-Markup."""
    if not text:
        return ''
    text = text.replace('­\n', '').replace('-\n', '-').replace('\x0c', ' ').replace('\n', ' ')
    text = MARKUP_RE.sub(lambda m: m.group(1) or m.group(2).replace('-', ' '), text)
    return re.sub(r'\s+', ' ', text).strip()


def to_int(value, default=None):
    return int(value) if value not in (None, '') else default


class Command(BaseCommand):
    help = 'Importiert die Pokédex-CSV-Dateien (data/csv) in die Datenbank.'

    def add_arguments(self, parser):
        parser.add_argument('--csv-dir', default=str(settings.BASE_DIR / 'data' / 'csv'))
        parser.add_argument('--if-empty', action='store_true',
                            help='Nichts tun, wenn bereits Pokémon in der DB sind.')

    # ------------------------------------------------------------------ helpers
    def read(self, name):
        path = self.csv_dir / f'{name}.csv'
        if not path.exists():
            raise CommandError(f'CSV fehlt: {path}')
        with open(path, newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f, delimiter=';'))

    def localized(self, name, id_col, lang_col='local_language_id', value_col='name'):
        """{id: Text} – Deutsch, sonst Englisch."""
        result, fallback = {}, {}
        for row in self.read(name):
            value = row[value_col]
            if not value:
                continue
            if row[lang_col] == GERMAN:
                result[row[id_col]] = value
            elif row[lang_col] == ENGLISH:
                fallback[row[id_col]] = value
        return {**fallback, **result}

    def latest_flavor(self, name, id_col):
        """Neuester Spieltext je ID – Deutsch, sonst Englisch."""
        best = {}  # id -> (prio, version, text)
        for row in self.read(name):
            lang = row['language_id']
            if lang not in (GERMAN, ENGLISH):
                continue
            version = int(row.get('version_group_id') or row.get('version_id'))
            key = (1 if lang == GERMAN else 0, version)
            if row[id_col] not in best or key > best[row[id_col]][0]:
                best[row[id_col]] = (key, row['flavor_text'])
        return {k: clean_text(v[1]) for k, v in best.items()}

    def step(self, label):
        self.stdout.write(f'  - {label} ({time.time() - self.t0:.1f}s)')

    # ------------------------------------------------------------------ main
    def handle(self, *args, **options):
        self.csv_dir = Path(options['csv_dir'])
        if options['if_empty'] and Pokemon.objects.exists():
            self.stdout.write('Pokédex bereits importiert – übersprungen.')
            return

        self.t0 = time.time()
        self.stdout.write(f'Importiere Pokédex aus {self.csv_dir} ...')
        with transaction.atomic():
            self.clear()
            self.import_generations()
            self.import_types()
            self.import_abilities()
            self.import_moves()
            self.import_species()
            self.import_pokemon()
            self.import_pokemon_moves()
        self.stdout.write(self.style.SUCCESS(
            f'Fertig in {time.time() - self.t0:.1f}s: {Species.objects.count()} Arten, '
            f'{Pokemon.objects.count()} Pokémon/Formen, {Move.objects.count()} Attacken, '
            f'{Ability.objects.count()} Fähigkeiten, {PokemonMove.objects.count()} erlernbare Attacken.'
        ))

    def clear(self):
        # Reihenfolge wegen PROTECT-Beziehungen; Favoriten/Teams hängen per CASCADE an Pokemon
        for model in (PokemonMove, PokemonAbility, PokemonType, Pokemon, Species, Move,
                      MoveMethod, DamageClass, Ability, TypeEfficacy, Type, Generation):
            model.objects.all().delete()

    def import_generations(self):
        names = self.localized('generation_names', 'generation_id')
        objs = []
        for row in self.read('generations'):
            roman = ROMAN.get(row['identifier'].split('-')[-1], row['identifier'])
            objs.append(Generation(id=row['id'], identifier=row['identifier'],
                                   name=names.get(row['id']) or f'Generation {roman}'))
        Generation.objects.bulk_create(objs)
        self.step(f'{len(objs)} Generationen')

    def import_types(self):
        names = self.localized('type_names', 'type_id')
        types = [Type(id=r['id'], identifier=r['identifier'], name=names.get(r['id'], r['identifier']))
                 for r in self.read('types') if int(r['id']) < 10000]
        Type.objects.bulk_create(types)
        self.type_ids = {t.id for t in Type.objects.all()}
        eff = [TypeEfficacy(attacker_id=r['damage_type_id'], defender_id=r['target_type_id'],
                            factor=r['damage_factor']) for r in self.read('type_efficacy')]
        TypeEfficacy.objects.bulk_create(eff)
        self.step(f'{len(types)} Typen, {len(eff)} Effektivitäten')

    def import_abilities(self):
        names = self.localized('ability_names', 'ability_id')
        effects = self.localized('ability_prose', 'ability_id', value_col='short_effect')
        flavors = self.latest_flavor('ability_flavor_text', 'ability_id')
        objs = [Ability(id=r['id'], identifier=r['identifier'], name=names.get(r['id'], r['identifier']),
                        generation_id=r['generation_id'], short_effect=clean_text(effects.get(r['id'], '')),
                        flavor_text=flavors.get(r['id'], ''))
                for r in self.read('abilities') if r['is_main_series'] == '1']
        Ability.objects.bulk_create(objs)
        self.ability_ids = {int(a.id) for a in objs}
        self.step(f'{len(objs)} Fähigkeiten')

    def import_moves(self):
        DamageClass.objects.bulk_create(
            DamageClass(id=r['id'], identifier=r['identifier']) for r in self.read('move_damage_classes'))
        methods = self.localized('pokemon_move_method_prose', 'pokemon_move_method_id')
        german_methods = {'level-up': 'Levelaufstieg', 'machine': 'TM/TP', 'egg': 'Zucht',
                          'tutor': 'Attacken-Lehrer'}
        MoveMethod.objects.bulk_create(
            MoveMethod(id=r['id'], identifier=r['identifier'],
                       name=german_methods.get(r['identifier']) or methods.get(r['id'], r['identifier']))
            for r in self.read('pokemon_move_methods'))

        self.move_names = self.localized('move_names', 'move_id')
        flavors = self.latest_flavor('move_flavor_text', 'move_id')
        objs = []
        for r in self.read('moves'):
            if int(r['id']) >= 10000 or int(r['type_id']) not in self.type_ids:
                continue  # Crypto-/Schatten-Attacken aus Colosseum/XD
            objs.append(Move(
                id=r['id'], identifier=r['identifier'], name=self.move_names.get(r['id'], r['identifier']),
                generation_id=r['generation_id'], type_id=r['type_id'],
                damage_class_id=to_int(r['damage_class_id']), power=to_int(r['power']),
                pp=to_int(r['pp']), accuracy=to_int(r['accuracy']), priority=to_int(r['priority'], 0),
                flavor_text=flavors.get(r['id'], ''),
            ))
        Move.objects.bulk_create(objs, batch_size=1000)
        self.move_ids = {int(m.id) for m in objs}
        self.step(f'{len(objs)} Attacken')

    def evolution_text(self, row, item_names, species_names, type_names):
        trigger = row['evolution_trigger_id']
        parts = []
        if trigger == '1':
            if row['minimum_level']:
                parts.append(f"ab Level {row['minimum_level']}")
            if row['minimum_happiness']:
                parts.append('hohe Freundschaft')
            if row['minimum_affection']:
                parts.append('hohe Zuneigung')
            if row['minimum_beauty']:
                parts.append('hohe Schönheit')
            if row['known_move_id']:
                parts.append(f"kennt {self.move_names.get(row['known_move_id'], '?')}")
            if row['known_move_type_id']:
                parts.append(f"kennt {type_names.get(row['known_move_type_id'], '?')}-Attacke")
            if row['held_item_id']:
                parts.append(f"trägt {item_names.get(row['held_item_id'], '?')}")
            if row['location_id']:
                parts.append('an bestimmtem Ort')
            if row['party_species_id']:
                parts.append(f"{species_names.get(row['party_species_id'], '?')} im Team")
            if row['party_type_id']:
                parts.append(f"{type_names.get(row['party_type_id'], '?')}-Pokémon im Team")
            if row['needs_overworld_rain'] == '1':
                parts.append('bei Regen')
            if row['turn_upside_down'] == '1':
                parts.append('Konsole umdrehen')
            rel = row['relative_physical_stats']
            if rel:
                parts.append({'1': 'Angriff > Verteidigung', '-1': 'Angriff < Verteidigung',
                              '0': 'Angriff = Verteidigung'}.get(rel, ''))
            if row['time_of_day']:
                parts.append({'day': 'tagsüber', 'night': 'nachts'}.get(row['time_of_day'], row['time_of_day']))
            if row['gender_id']:
                parts.append({'1': 'nur weiblich', '2': 'nur männlich'}.get(row['gender_id'], ''))
            return ', '.join(p for p in parts if p) or 'Levelaufstieg'
        if trigger == '2':
            text = 'Tausch'
            if row['held_item_id']:
                text += f" mit {item_names.get(row['held_item_id'], '?')}"
            if row['trade_species_id']:
                text += f" gegen {species_names.get(row['trade_species_id'], '?')}"
            return text
        if trigger == '3':
            return item_names.get(row['trigger_item_id'], 'Item')
        if trigger == '4':
            return 'freier Platz im Team (bei Ninjask-Entwicklung)'
        return 'Spezialbedingung'

    def import_species(self):
        names = self.localized('pokemon_species_names', 'pokemon_species_id')
        genera = self.localized('pokemon_species_names', 'pokemon_species_id', value_col='genus')
        flavors = self.latest_flavor('pokemon_species_flavor_text', 'species_id')
        rows = self.read('pokemon_species')
        objs = [Species(
            id=r['id'], identifier=r['identifier'], name=names.get(r['id'], r['identifier']),
            genus=genera.get(r['id'], ''), generation_id=r['generation_id'],
            evolution_chain_id=to_int(r['evolution_chain_id']), capture_rate=to_int(r['capture_rate'], 0),
            base_happiness=to_int(r['base_happiness']), gender_rate=to_int(r['gender_rate'], -1),
            is_baby=r['is_baby'] == '1', is_legendary=r['is_legendary'] == '1',
            is_mythical=r['is_mythical'] == '1', flavor_text=flavors.get(r['id'], ''),
        ) for r in rows]
        Species.objects.bulk_create(objs, batch_size=1000)

        # Zweiter Durchlauf: Selbstreferenz + Evolutionsbedingung
        item_names = self.localized('item_names', 'item_id')
        type_names = {str(t.id): t.name for t in Type.objects.all()}
        evo = {}
        for row in self.read('pokemon_evolution'):
            evo.setdefault(row['evolved_species_id'], row)  # erste Methode reicht für die Anzeige
        by_id = {str(o.id): o for o in objs}
        for r in rows:
            sp = by_id[r['id']]
            sp.evolves_from_id = to_int(r['evolves_from_species_id'])
            if r['id'] in evo:
                sp.evolution_trigger = self.evolution_text(evo[r['id']], item_names, names, type_names)[:200]
        Species.objects.bulk_update(objs, ['evolves_from', 'evolution_trigger'], batch_size=1000)
        self.step(f'{len(objs)} Arten')

    def import_pokemon(self):
        form_names = self.localized('pokemon_form_names', 'pokemon_form_id', value_col='form_name')
        form_by_pokemon = {}
        for f in self.read('pokemon_forms'):
            if f['is_default'] == '1':
                form_by_pokemon[f['pokemon_id']] = form_names.get(f['id']) or (
                    f['form_identifier'].replace('-', ' ').title() if f['form_identifier'] else '')

        stats = defaultdict(dict)
        for s in self.read('pokemon_stats'):
            if s['stat_id'] in STAT_FIELDS:
                stats[s['pokemon_id']][STAT_FIELDS[s['stat_id']]] = int(s['base_stat'])

        objs = []
        for r in self.read('pokemon'):
            st = stats[r['id']]
            objs.append(Pokemon(
                id=r['id'], identifier=r['identifier'], species_id=r['species_id'],
                form_name=form_by_pokemon.get(r['id'], ''), height=to_int(r['height'], 0),
                weight=to_int(r['weight'], 0), base_experience=to_int(r['base_experience']),
                order=to_int(r['order'], 0), is_default=r['is_default'] == '1',
                total=sum(st.values()), **st,
            ))
        Pokemon.objects.bulk_create(objs, batch_size=1000)
        self.pokemon_ids = {int(p.id) for p in objs}

        PokemonType.objects.bulk_create(
            (PokemonType(pokemon_id=r['pokemon_id'], type_id=r['type_id'], slot=r['slot'])
             for r in self.read('pokemon_types') if int(r['pokemon_id']) in self.pokemon_ids),
            batch_size=2000)
        PokemonAbility.objects.bulk_create(
            (PokemonAbility(pokemon_id=r['pokemon_id'], ability_id=r['ability_id'],
                            is_hidden=r['is_hidden'] == '1', slot=r['slot'])
             for r in self.read('pokemon_abilities')
             if int(r['ability_id']) in self.ability_ids and int(r['pokemon_id']) in self.pokemon_ids),
            batch_size=2000)
        self.step(f'{len(objs)} Pokémon inkl. Typen, Fähigkeiten, Statuswerte')

    def import_pokemon_moves(self):
        vg_order, vg_name = {}, {}
        for r in self.read('version_groups'):
            vg_order[r['id']] = int(r['order'])
            vg_name[r['id']] = r['identifier'].replace('-', ' / ', 1).replace('-', ' ').title()

        rows = self.read('pokemon_moves')
        latest = {}
        for r in rows:
            o = vg_order[r['version_group_id']]
            if o > latest.get(r['pokemon_id'], (-1, None))[0]:
                latest[r['pokemon_id']] = (o, r['version_group_id'])

        seen, objs = set(), []
        for r in rows:
            pid, vg = r['pokemon_id'], r['version_group_id']
            if latest[pid][1] != vg or int(r['move_id']) not in self.move_ids \
                    or int(pid) not in self.pokemon_ids:
                continue
            key = (pid, r['move_id'], r['pokemon_move_method_id'], r['level'])
            if key in seen:
                continue
            seen.add(key)
            objs.append(PokemonMove(pokemon_id=pid, move_id=r['move_id'], method_id=r['pokemon_move_method_id'],
                                    level=to_int(r['level'], 0), version_group=vg_name[vg]))
        PokemonMove.objects.bulk_create(objs, batch_size=5000)
        self.step(f'{len(objs)} erlernbare Attacken (neueste Edition je Pokémon)')
