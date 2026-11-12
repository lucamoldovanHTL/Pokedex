"""Kampf-Logik der Arena. Arbeitet nur auf einem JSON-fähigen dict (Battle.state).

Vereinfachte Regeln: Level 50, nur Schadensattacken (Stärke, Genauigkeit, Priorität, Typ, STAB,
Volltreffer, Zufallsfaktor). Beide Trainer wählen gleichzeitig eine Attacke oder einen Wechsel;
Wechsel kommen zuerst, danach greift das schnellere Pokémon zuerst an.
"""
import random

from pokedex.models import ARTWORK_URL, SPRITE_URL, Move, Pokemon

LEVEL = 50
MAX_MOVES = 4
# Attacken, deren Nachteil (Selbst-K.O., Aufladen, Aussetzen …) hier nicht simuliert wird
BANNED_MOVES = {
    'explosion', 'self-destruct', 'misty-explosion', 'dream-eater', 'focus-punch', 'last-resort', 'belch',
    'hyper-beam', 'giga-impact', 'frenzy-plant', 'blast-burn', 'hydro-cannon', 'rock-wrecker', 'roar-of-time',
    'prismatic-laser', 'eternabeam', 'meteor-assault', 'solar-beam', 'solar-blade', 'sky-attack', 'skull-bash',
    'razor-wind', 'freeze-shock', 'ice-burn', 'meteor-beam', 'future-sight', 'doom-desire', 'fake-out',
    'first-impression', 'steel-beam', 'mind-blown',
}
STRUGGLE = {'name': 'Verzweifler', 'type_id': None, 'type_name': '—', 'color': '#888888',
            'power': 50, 'acc': None, 'prio': 0, 'cls': 'physical'}


def _stat(base, is_hp=False):
    if is_hp:
        return (2 * base + 31) * LEVEL // 100 + LEVEL + 10
    return (2 * base + 31) * LEVEL // 100 + 5


def learnset(pokemon):
    """Alle wählbaren Schadensattacken eines Pokémon (Formen ohne eigene Liste erben von der Grundform)."""
    def query(p):
        return list(Move.objects.filter(pokemon=p, power__gt=0).exclude(identifier__in=BANNED_MOVES)
                    .select_related('type', 'damage_class').distinct().order_by('-power', 'name'))
    moves = query(pokemon)
    if not moves and not pokemon.is_default:
        base = Pokemon.objects.filter(species_id=pokemon.species_id, is_default=True).first()
        if base:
            moves = query(base)
    return moves


def auto_moves(pokemon, pool):
    """Sinnvolle Standardauswahl: starke, genaue Attacken, möglichst verschiedene Typen, STAB bevorzugt."""
    own = {t.id for t in pokemon.types}

    def score(m):
        cls = m.damage_class.identifier if m.damage_class else 'physical'
        stat = pokemon.attack if cls == 'physical' else pokemon.special_attack
        return m.power * (1.5 if m.type_id in own else 1) * (m.accuracy or 100) / 100 * (stat + 40)

    ranked = sorted(pool, key=score, reverse=True)
    picked, seen = [], set()
    for m in ranked:
        if m.type_id not in seen:
            picked.append(m)
            seen.add(m.type_id)
        if len(picked) == MAX_MOVES:
            return picked
    for m in ranked:
        if len(picked) == MAX_MOVES:
            break
        if m not in picked:
            picked.append(m)
    return picked


def moves_for(member, pool=None):
    """Die gewählten Attacken eines Teammitglieds, sonst die automatische Auswahl."""
    pool = learnset(member.pokemon) if pool is None else pool
    allowed = {m.id: m for m in pool}
    chosen = [allowed[m.id] for m in member.moves.all() if m.id in allowed][:MAX_MOVES]
    return chosen or auto_moves(member.pokemon, pool)


def _move_dict(m):
    return {'name': m.name, 'type_id': m.type_id, 'type_name': m.type.name, 'color': m.type.color,
            'power': m.power, 'acc': m.accuracy, 'prio': m.priority,
            'cls': m.damage_class.identifier if m.damage_class else 'physical'}


def build_side(user, team):
    members = list(team.members.select_related('pokemon__species')
                   .prefetch_related('pokemon__pokemon_types__type', 'moves'))
    mons = []
    for member in members:
        p = member.pokemon
        hp = _stat(p.hp, True)
        mons.append({
            'name': member.nickname or p.display_name, 'species': p.display_name,
            'art': ARTWORK_URL.format(p.id), 'sprite': SPRITE_URL.format(p.id),
            'types': [{'id': t.id, 'name': t.name, 'color': t.color} for t in p.types],
            'max_hp': hp, 'hp': hp,
            'atk': _stat(p.attack), 'def': _stat(p.defense), 'spa': _stat(p.special_attack),
            'spd': _stat(p.special_defense), 'spe': _stat(p.speed),
            'moves': [_move_dict(m) for m in moves_for(member)] or [dict(STRUGGLE)],
        })
    return {'name': user.username, 'team': team.name, 'active': 0, 'mons': mons,
            'boss': bool(team.is_boss and user.is_superuser)}


def new_state(user1, team1, user2, team2):
    state = {'turn': 1, 'v': 1, 'sides': [build_side(user1, team1), build_side(user2, team2)],
             'actions': [None, None], 'log': []}
    for side in state['sides']:
        _log(state, f'{side["name"]} schickt {side["mons"][0]["name"]} in den Kampf!', 'switch', turn=0)
    return state


# ------------------------------------------------------------------ Ablauf

def active(state, i):
    side = state['sides'][i]
    return side['mons'][side['active']]


def alive(state, i):
    return [n for n, m in enumerate(state['sides'][i]['mons']) if m['hp'] > 0]


def is_forced(state):
    """True, wenn nach einem K.O. erst ein neues Pokémon nachrücken muss."""
    return any(active(state, i)['hp'] <= 0 for i in (0, 1))


def needed(state):
    """Welche Seiten müssen gerade etwas wählen? Nach einem K.O. nur die Seite, die nachrücken muss."""
    forced = [i for i in (0, 1) if active(state, i)['hp'] <= 0]
    return forced or [0, 1]


def loser(state):
    """Index der Seite ohne kampffähige Pokémon (oder None)."""
    for i in (0, 1):
        if not alive(state, i):
            return i
    return None


def valid_action(state, i, kind, index):
    side = state['sides'][i]
    if i not in needed(state) or state['actions'][i] is not None:
        return None
    if kind == 'switch':
        if index != side['active'] and index in alive(state, i):
            return {'type': 'switch', 'i': index}
    elif kind == 'move' and not is_forced(state):
        if 0 <= index < len(active(state, i)['moves']):
            return {'type': 'move', 'i': index}
    return None


def default_action(state, i):
    """Automatische Wahl (erste Attacke bzw. nächstes fittes Pokémon)."""
    if active(state, i)['hp'] <= 0:
        return {'type': 'switch', 'i': alive(state, i)[0]}
    return {'type': 'move', 'i': 0}


def submit(state, i, action, chart, rng=random):
    """Trägt eine Aktion ein und rechnet die Runde aus, sobald alle nötigen Aktionen da sind.
    Liefert True, wenn die Runde ausgewertet wurde."""
    state['actions'][i] = action
    state['v'] += 1
    if any(state['actions'][n] is None for n in needed(state)):
        return False
    _resolve(state, chart, rng)
    return True


def _log(state, text, kind='', turn=None):
    state['log'].append({'t': state['turn'] if turn is None else turn, 'text': text, 'kind': kind})


def _label(state, i):
    return f'{active(state, i)["name"]} ({state["sides"][i]["name"]})'


def _switch(state, i, index):
    side = state['sides'][i]
    side['active'] = index
    _log(state, f'{side["name"]} schickt {side["mons"][index]["name"]} in den Kampf!', 'switch')


def _resolve(state, chart, rng):
    actions, state['actions'] = state['actions'], [None, None]
    if is_forced(state):
        for i in (0, 1):
            if actions[i]:
                _switch(state, i, actions[i]['i'])
        return

    for i in (0, 1):
        if actions[i]['type'] == 'switch':
            _log(state, f'{state["sides"][i]["name"]} ruft {active(state, i)["name"]} zurück.', 'switch')
            _switch(state, i, actions[i]['i'])

    movers = [i for i in (0, 1) if actions[i]['type'] == 'move']
    movers.sort(key=lambda i: (state['sides'][i]['boss'], active(state, i)['moves'][actions[i]['i']]['prio'],
                               active(state, i)['spe'], rng.random()), reverse=True)
    for i in movers:
        if active(state, i)['hp'] > 0 and active(state, 1 - i)['hp'] > 0:
            _attack(state, i, actions[i]['i'], chart, rng)
    state['turn'] += 1


def _attack(state, i, move_index, chart, rng):
    att, target = active(state, i), active(state, 1 - i)
    move = att['moves'][move_index]
    _log(state, f'{_label(state, i)} setzt {move["name"]} ein!', 'move')

    if state['sides'][i]['boss']:
        # Admin-Team: trifft immer und besiegt den Gegner mit einem Schlag
        damage = target['hp']
        _log(state, 'Ein Volltreffer!', 'crit')
    else:
        if move['acc'] and rng.random() * 100 >= move['acc']:
            _log(state, 'Die Attacke ging daneben!', 'miss')
            return
        eff = 1.0
        if move['type_id'] is not None:
            for t in target['types']:
                eff *= chart.get((move['type_id'], t['id']), 1.0)
        if eff == 0:
            _log(state, f'Es hat keine Wirkung auf {target["name"]}.', 'miss')
            return
        a, d = (att['atk'], target['def']) if move['cls'] == 'physical' else (att['spa'], target['spd'])
        stab = 1.5 if any(t['id'] == move['type_id'] for t in att['types']) else 1.0
        crit = rng.random() < 1 / 24
        damage = ((2 * LEVEL / 5 + 2) * move['power'] * a / d / 50 + 2) * stab * eff * rng.uniform(0.85, 1.0)
        damage = max(1, int(damage * (1.5 if crit else 1)))
        if crit:
            _log(state, 'Ein Volltreffer!', 'crit')
        if eff > 1:
            _log(state, 'Das ist sehr effektiv!', 'good')
        elif eff < 1:
            _log(state, 'Das ist nicht sehr effektiv …', 'bad')
        if state['sides'][1 - i]['boss']:
            # Admin-Team: behält immer mindestens 1 KP
            damage = min(damage, target['hp'] - 1)
            if damage <= 0:
                _log(state, f'{target["name"]} hält eisern durch!', 'bad')
                return

    target['hp'] = max(0, target['hp'] - damage)
    pct = max(1, round(damage / target['max_hp'] * 100))
    _log(state, f'{_label(state, 1 - i)} verliert {pct} % KP.', 'dmg')
    if target['hp'] == 0:
        _log(state, f'{_label(state, 1 - i)} wurde besiegt!', 'ko')


def elo_delta(rating_a, rating_b, score_a, k=32):
    expected = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    return round(k * (score_a - expected))
