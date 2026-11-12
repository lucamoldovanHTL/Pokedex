import datetime
from collections import OrderedDict

from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Generation, Pokemon, PokemonAbility, PokemonMove, Species, Type
from .typechart import defensive_profile, load_chart, simulate_battle

SORT_OPTIONS = OrderedDict([
    ('dex', ('Nr.', ['species_id', 'order'])),
    ('name', ('Name', ['species__name'])),
    ('-total', ('Gesamtwerte ↓', ['-total', 'species_id'])),
    ('-hp', ('KP ↓', ['-hp', 'species_id'])),
    ('-attack', ('Angriff ↓', ['-attack', 'species_id'])),
    ('-defense', ('Verteidigung ↓', ['-defense', 'species_id'])),
    ('-special_attack', ('Sp.-Angriff ↓', ['-special_attack', 'species_id'])),
    ('-special_defense', ('Sp.-Verteidigung ↓', ['-special_defense', 'species_id'])),
    ('-speed', ('Initiative ↓', ['-speed', 'species_id'])),
    ('-weight', ('Gewicht ↓', ['-weight', 'species_id'])),
    ('-height', ('Größe ↓', ['-height', 'species_id'])),
])


def search_pokemon(qs, query):
    query = query.strip().lstrip('#')
    if not query:
        return qs
    if query.isdigit():
        return qs.filter(species_id=int(query))
    return qs.filter(Q(species__name__icontains=query) | Q(identifier__icontains=query)
                     | Q(form_name__icontains=query))


def home(request):
    total_species = Species.objects.count()
    featured = None
    if total_species:
        species_id = datetime.date.today().toordinal() % total_species + 1
        featured = Pokemon.objects.with_relations().filter(species_id=species_id, is_default=True).first()
    context = {
        'featured': featured,
        'counts': {
            'species': total_species,
            'pokemon': Pokemon.objects.count(),
            'types': Type.objects.count(),
            'generations': Generation.objects.count(),
        },
        'types': Type.objects.all(),
        'generations': Generation.objects.annotate(n=Count('species')),
        'strongest': Pokemon.objects.with_relations().filter(is_default=True,
                                                              species__is_legendary=False,
                                                              species__is_mythical=False)
                                                      .order_by('-total')[:6],
    }
    return render(request, 'pokedex/home.html', context)


def pokemon_list(request):
    qs = Pokemon.objects.with_relations()
    p = request.GET
    show_forms = p.get('forms') == '1'
    if not show_forms:
        qs = qs.filter(is_default=True)
    qs = search_pokemon(qs, p.get('q', ''))
    for param in ('type', 'type2'):
        if p.get(param):
            qs = qs.filter(pokemon_types__type__identifier=p[param])
    if p.get('gen', '').isdigit():
        qs = qs.filter(species__generation_id=int(p['gen']))
    status = p.get('status')
    if status == 'legendary':
        qs = qs.filter(species__is_legendary=True)
    elif status == 'mythical':
        qs = qs.filter(species__is_mythical=True)
    elif status == 'baby':
        qs = qs.filter(species__is_baby=True)
    sort = p.get('sort', 'dex')
    qs = qs.order_by(*SORT_OPTIONS.get(sort, SORT_OPTIONS['dex'])[1]).distinct()

    page = Paginator(qs, 48).get_page(p.get('page'))
    params = p.copy()
    params.pop('page', None)
    favorite_ids = set()
    if request.user.is_authenticated:
        favorite_ids = set(request.user.favorites.values_list('pokemon_id', flat=True))
    for poke in page.object_list:
        poke.is_fav = poke.id in favorite_ids
    return render(request, 'pokedex/pokemon_list.html', {
        'page': page, 'types': Type.objects.all(), 'generations': Generation.objects.all(),
        'sort_options': [(k, v[0]) for k, v in SORT_OPTIONS.items()], 'sort': sort,
        'show_forms': show_forms, 'querystring': params.urlencode(),
        'show_total': sort not in ('dex', 'name'),
    })


def _evolution_stages(species):
    """Liefert die Entwicklungsreihe als Liste von Stufen: [[Species, …], [Species, …], …]."""
    if not species.evolution_chain_id:
        return []
    members = list(Species.objects.filter(evolution_chain_id=species.evolution_chain_id))
    if len(members) < 2:
        return []
    defaults = {p.species_id: p for p in Pokemon.objects.with_relations()
                .filter(species__in=members, is_default=True)}
    for m in members:
        m.default_pokemon = defaults.get(m.id)
    children = {}
    for m in members:
        children.setdefault(m.evolves_from_id, []).append(m)
    ids = {m.id for m in members}
    stage = [m for m in members if m.evolves_from_id not in ids]
    stages = []
    while stage:
        stages.append(stage)
        stage = [c for s in stage for c in children.get(s.id, [])]
    return stages


def pokemon_detail(request, identifier):
    pokemon = get_object_or_404(
        Pokemon.objects.with_relations().prefetch_related(
            Prefetch('pokemon_abilities', queryset=PokemonAbility.objects.select_related('ability'))),
        identifier=identifier)
    species = pokemon.species

    moves = (PokemonMove.objects.filter(pokemon=pokemon)
             .select_related('move__type', 'move__damage_class', 'method')
             .order_by('method_id', 'level', 'move__name'))
    move_groups = OrderedDict()
    for pm in moves:
        move_groups.setdefault(pm.method.name, []).append(pm)

    neighbours = Pokemon.objects.filter(is_default=True).select_related('species')
    prev_p = neighbours.filter(species_id=species.id - 1).first()
    next_p = neighbours.filter(species_id=species.id + 1).first()

    context = {
        'pokemon': pokemon, 'species': species,
        'varieties': Pokemon.objects.with_relations().filter(species=species).exclude(pk=pokemon.pk),
        'defense': defensive_profile(pokemon.types),
        'stages': _evolution_stages(species),
        'move_groups': move_groups, 'version_group': moves[0].version_group if moves else '',
        'prev': prev_p, 'next': next_p,
        'max_stat': 255,
    }
    if request.user.is_authenticated:
        context['is_favorite'] = request.user.favorites.filter(pokemon=pokemon).exists()
        context['teams'] = request.user.teams.annotate(n=Count('members'))
    return render(request, 'pokedex/pokemon_detail.html', context)


def type_chart(request):
    types, chart = load_chart()
    matrix = [{'attacker': a, 'cells': [chart.get((a.id, d.id), 1.0) for d in types]} for a in types]
    return render(request, 'pokedex/type_chart.html', {'types': types, 'matrix': matrix})


def battle(request):
    a_ident, b_ident = request.GET.get('a', ''), request.GET.get('b', '')
    context = {'a_ident': a_ident, 'b_ident': b_ident}
    if a_ident or b_ident:
        qs = Pokemon.objects.with_relations()
        a = qs.filter(identifier=a_ident).first()
        b = qs.filter(identifier=b_ident).first()
        if not a or not b:
            context['error'] = 'Bitte zwei Pokémon aus der Vorschlagsliste wählen.'
        else:
            context['result'] = simulate_battle(a, b)
        context['a'], context['b'] = a, b
    return render(request, 'pokedex/battle.html', context)


# ----------------------------------------------------------------- JSON-API

def _pokemon_json(p, full=False):
    data = {
        'id': p.id, 'identifier': p.identifier, 'dex': p.species_id, 'name': p.display_name,
        'types': [{'identifier': t.identifier, 'name': t.name, 'color': t.color} for t in p.types],
        'sprite': p.sprite, 'artwork': p.artwork, 'url': p.get_absolute_url(),
    }
    if full:
        data.update({
            'genus': p.species.genus, 'height_m': p.height_m, 'weight_kg': p.weight_kg,
            'stats': {s['key']: s['value'] for s in p.stats}, 'total': p.total,
            'abilities': [{'name': pa.ability.name, 'hidden': pa.is_hidden}
                          for pa in p.pokemon_abilities.select_related('ability')],
            'flavor_text': p.species.flavor_text,
        })
    return data


def api_pokemon_search(request):
    """GET /api/pokemon/?q=glu  → max. 15 Treffer (für Autovervollständigung)."""
    q = request.GET.get('q', '')
    qs = Pokemon.objects.with_relations()
    qs = search_pokemon(qs, q) if q else qs.filter(is_default=True)
    limit = request.GET.get('limit', '')
    limit = min(max(int(limit), 1), 100) if limit.isdecimal() else 15
    return JsonResponse({'results': [_pokemon_json(p) for p in qs.order_by('species_id', 'order')[:limit]]})


def api_pokemon_detail(request, identifier):
    p = get_object_or_404(Pokemon.objects.with_relations(), identifier=identifier)
    return JsonResponse(_pokemon_json(p, full=True))
