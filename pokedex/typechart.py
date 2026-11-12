"""Typ-Effektivität, Team-Analyse und eine einfache, deterministische Kampfsimulation."""
import math

from .models import Type, TypeEfficacy


def load_chart():
    """Liefert (Typenliste, {(angreifer_id, verteidiger_id): faktor als float})."""
    types = list(Type.objects.all())
    chart = {(e.attacker_id, e.defender_id): e.factor / 100
             for e in TypeEfficacy.objects.all()}
    return types, chart


def multiplier(chart, attack_type, defender_types):
    m = 1.0
    for t in defender_types:
        m *= chart.get((attack_type.id, t.id), 1.0)
    return m


def defensive_profile(defender_types, types=None, chart=None):
    """Schadensmultiplikatoren aller Angriffstypen gegen ein Pokémon, gruppiert."""
    if chart is None:
        types, chart = load_chart()
    groups = {4.0: [], 2.0: [], 0.5: [], 0.25: [], 0.0: []}
    for atk in types:
        m = multiplier(chart, atk, defender_types)
        if m in groups:
            groups[m].append(atk)
    return [
        ('4×', 'danger', groups[4.0]), ('2×', 'warning', groups[2.0]),
        ('½×', 'success', groups[0.5]), ('¼×', 'success', groups[0.25]),
        ('0×', 'secondary', groups[0.0]),
    ]


def team_analysis(pokemon_list):
    """Für jeden Angriffstyp: wie viele Teammitglieder sind schwach / resistent / immun.
    Außerdem: welche Typen kann das Team mit eigenen Typen (STAB) sehr effektiv treffen."""
    types, chart = load_chart()
    rows = []
    for atk in types:
        weak = resist = immune = 0
        for p in pokemon_list:
            m = multiplier(chart, atk, p.types)
            if m == 0:
                immune += 1
            elif m > 1:
                weak += 1
            elif m < 1:
                resist += 1
        rows.append({'type': atk, 'weak': weak, 'resist': resist, 'immune': immune,
                     'danger': weak >= 3 and resist + immune == 0})

    own_types = {t.id: t for p in pokemon_list for t in p.types}
    coverage = []
    for target in types:
        hit_by = [t for t in own_types.values() if chart.get((t.id, target.id), 1.0) > 1]
        coverage.append({'type': target, 'covered': bool(hit_by), 'by': hit_by})
    return {'rows': rows, 'coverage': coverage,
            'uncovered': [c['type'] for c in coverage if not c['covered']],
            'threats': [r['type'] for r in rows if r['danger']]}


# --------------------------------------------------------------------- Kampf
LEVEL = 50
BASE_POWER = 80  # angenommene Stärke einer typischen Attacke


def _stat(base, is_hp=False):
    """Statuswert auf Level 50 mit IV 31, ohne EVs/Wesen."""
    if is_hp:
        return (2 * base + 31) * LEVEL // 100 + LEVEL + 10
    return (2 * base + 31) * LEVEL // 100 + 5


def _best_attack(chart, attacker, defender):
    """Wählt den eigenen Typ (STAB) und die Angriffsart (physisch/speziell) mit dem meisten Schaden."""
    best = None
    for atk_type in attacker.types:
        eff = multiplier(chart, atk_type, defender.types)
        for kind, a_stat, d_stat in (('physisch', attacker.attack, defender.defense),
                                     ('speziell', attacker.special_attack, defender.special_defense)):
            base = ((2 * LEVEL / 5 + 2) * BASE_POWER * _stat(a_stat) / _stat(d_stat)) / 50 + 2
            dmg = base * 1.5 * eff
            if best is None or dmg > best['damage']:
                best = {'type': atk_type, 'kind': kind, 'effectiveness': eff, 'damage': dmg}
    best['damage'] = round(best['damage'])
    return best


def simulate_battle(a, b):
    """Rundenbasierter Vergleich: wer braucht weniger Treffer bis zum K.O.?
    Gleichstand bei den Treffern entscheidet die Initiative (der Schnellere greift zuerst an)."""
    _, chart = load_chart()
    hp_a, hp_b = _stat(a.hp, True), _stat(b.hp, True)
    atk_a, atk_b = _best_attack(chart, a, b), _best_attack(chart, b, a)
    hits_a = math.ceil(hp_b / atk_a['damage']) if atk_a['damage'] else math.inf  # Treffer, die A braucht
    hits_b = math.ceil(hp_a / atk_b['damage']) if atk_b['damage'] else math.inf
    a_first = a.speed > b.speed or (a.speed == b.speed and a.total >= b.total)

    if hits_a == math.inf and hits_b == math.inf:
        winner = None
    elif hits_a < hits_b or (hits_a == hits_b and a_first):
        winner = a
    else:
        winner = b

    stat_rows = []
    for (key, label) in a.STAT_FIELDS:
        va, vb = getattr(a, key), getattr(b, key)
        stat_rows.append({'label': label, 'a': va, 'b': vb, 'max': max(va, vb, 1)})

    return {
        'a': a, 'b': b, 'winner': winner, 'a_first': a_first,
        'hp_a': hp_a, 'hp_b': hp_b, 'atk_a': atk_a, 'atk_b': atk_b,
        'hits_a': None if hits_a == math.inf else hits_a,
        'hits_b': None if hits_b == math.inf else hits_b,
        'pct_a': min(100, round(atk_a['damage'] / hp_b * 100)),
        'pct_b': min(100, round(atk_b['damage'] / hp_a * 100)),
        'stat_rows': stat_rows,
    }
