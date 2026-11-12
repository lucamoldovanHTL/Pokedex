"""Arena: Lobby (Warteschlange + Herausforderungen), Online-Kampf per Polling und Rangliste.

Der Kampf läuft ohne WebSockets: der Browser fragt alle 1,5 Sekunden den Zustand ab
(battle_state) und schickt Aktionen per POST (battle_action). Der gesamte Kampfzustand
liegt als JSON in Battle.state; Änderungen passieren immer unter select_for_update.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from pokedex.typechart import load_chart
from trainer.models import Team

from . import engine
from .models import Battle, Rating

TURN_SECONDS = 60     # Bedenkzeit pro Runde
FRESH_SECONDS = 12    # so lange gilt ein wartender Spieler ohne Lebenszeichen noch als anwesend
STALE_SECONDS = 60    # danach werden offene Kämpfe abgebrochen


def _now():
    return timezone.now()


def _fresh():
    return _now() - timedelta(seconds=FRESH_SECONDS)


def _playable_teams(user):
    return Team.objects.filter(user=user).annotate(n=Count('members')).filter(n__gt=0)


def _current_battle(user):
    return (Battle.objects.filter(Q(player1=user) | Q(player2=user), status__in=[Battle.OPEN, Battle.ACTIVE])
            .order_by('-id').first())


def _posted_team(request):
    team_id = request.POST.get('team', '')
    team = _playable_teams(request.user).filter(pk=int(team_id)).first() if team_id.isdecimal() else None
    if not team:
        messages.error(request, 'Bitte wähle ein Team mit mindestens einem Pokémon.')
    return team


def _busy(request):
    """True (mit Meldung), wenn der Trainer schon in einem Kampf steckt."""
    if _current_battle(request.user):
        messages.warning(request, 'Du bist bereits in einem Kampf.')
        return True
    return False


# ------------------------------------------------------------------ Kampf-Verwaltung

def _start(battle, user, team):
    """Zweiter Spieler tritt bei. Liefert False, wenn der Kampf inzwischen vergeben/ungültig ist."""
    if not battle.team1 or not battle.team1.members.exists():
        Battle.objects.filter(pk=battle.pk, status=Battle.OPEN).update(status=Battle.CANCELLED)
        return False
    state = engine.new_state(battle.player1, battle.team1, user, team)
    return Battle.objects.filter(pk=battle.pk, status=Battle.OPEN, player2__isnull=True).update(
        player2=user, team2=team, status=Battle.ACTIVE, state=state,
        turn_deadline=_now() + timedelta(seconds=TURN_SECONDS)) == 1


def _finish(battle, winner_side, reason):
    """Beendet den Kampf und verrechnet die Elo-Punkte. Muss in einer Transaktion laufen."""
    users = [battle.player1, battle.player2]
    r1, _ = Rating.objects.select_for_update().get_or_create(user=users[0])
    r2, _ = Rating.objects.select_for_update().get_or_create(user=users[1])
    score = {0: 1, 1: 0, None: 0.5}[winner_side]
    delta = engine.elo_delta(r1.elo, r2.elo, score)
    r1.elo += delta
    r2.elo -= delta
    if winner_side is None:
        r1.draws += 1
        r2.draws += 1
    else:
        winner, loser = (r1, r2) if winner_side == 0 else (r2, r1)
        winner.wins += 1
        loser.losses += 1
    r1.save()
    r2.save()

    battle.status = Battle.FINISHED
    battle.reason = reason
    battle.winner = None if winner_side is None else users[winner_side]
    battle.elo_change1, battle.elo_change2 = delta, -delta
    battle.finished_at = _now()
    battle.turn_deadline = None
    state = battle.state
    if state:
        text = 'Unentschieden!' if winner_side is None else f'{users[winner_side].username} gewinnt den Kampf!'
        state['log'].append({'t': state['turn'], 'text': text, 'kind': 'end'})
        state['v'] += 1


def _after_turn(battle):
    lost = engine.loser(battle.state)
    if lost is not None:
        _finish(battle, 1 - lost, 'ko')
    else:
        battle.turn_deadline = _now() + timedelta(seconds=TURN_SECONDS)


def _check_timeout(pk):
    """Bedenkzeit abgelaufen: wer nicht gewählt hat, verliert (beide: Unentschieden)."""
    with transaction.atomic():
        battle = Battle.objects.select_for_update(of=('self',)).select_related('player1', 'player2').get(pk=pk)
        if battle.status != Battle.ACTIVE or not battle.turn_deadline or _now() <= battle.turn_deadline:
            return
        state = battle.state
        missing = [i for i in engine.needed(state) if state['actions'][i] is None]
        late = [i for i in missing if not state['sides'][i]['boss']]
        if len(late) == 2:
            _finish(battle, None, 'timeout')
        elif late:
            _finish(battle, 1 - late[0], 'timeout')
        else:
            chart = load_chart()[1]
            for i in missing:
                engine.submit(state, i, engine.default_action(state, i), chart)
            _after_turn(battle)
        battle.save()


def _payload(battle, user):
    """Zustand aus Sicht eines Spielers (ohne geheime Infos des Gegners)."""
    me = battle.side_of(user)
    data = {'id': battle.pk, 'status': battle.status}
    state = battle.state
    if battle.status == Battle.OPEN or not state:
        data['invited'] = battle.invited.username if battle.invited_id else None
        return data

    def public(mon):
        return {'name': mon['name'], 'species': mon['species'], 'art': mon['art'], 'sprite': mon['sprite'],
                'types': mon['types'], 'pct': -(-mon['hp'] * 100 // mon['max_hp']), 'fainted': mon['hp'] <= 0}

    mine, theirs = state['sides'][me], state['sides'][1 - me]
    my_mons = []
    for mon in mine['mons']:
        entry = public(mon)
        entry.update(hp=mon['hp'], max_hp=mon['max_hp'], moves=mon['moves'])
        my_mons.append(entry)
    is_active = battle.status == Battle.ACTIVE
    need = engine.needed(state) if is_active else []
    data.update({
        'v': state['v'], 'turn': state['turn'], 'log': state['log'],
        'you': {'name': mine['name'], 'team': mine['team'], 'active': mine['active'], 'mons': my_mons},
        'opp': {'name': theirs['name'], 'team': theirs['team'], 'active': theirs['active'],
                'mons': [public(m) for m in theirs['mons']]},
        'need_action': me in need and state['actions'][me] is None,
        'forced': is_active and engine.is_forced(state),
        'opp_ready': (1 - me) not in need or state['actions'][1 - me] is not None,
        'seconds_left': max(0, int((battle.turn_deadline - _now()).total_seconds()))
        if is_active and battle.turn_deadline else None,
    })
    if battle.status == Battle.FINISHED:
        rating = Rating.objects.filter(user=user).first()
        data['result'] = {
            'won': None if battle.winner_id is None else battle.winner_id == user.id,
            'reason': battle.reason_label,
            'elo_change': battle.elo_change1 if me == 0 else battle.elo_change2,
            'elo': rating.elo if rating else None,
        }
    return data


# ------------------------------------------------------------------ Seiten

@login_required
def lobby(request):
    Battle.objects.filter(status=Battle.OPEN, last_seen__lt=_now() - timedelta(seconds=STALE_SECONDS)) \
        .update(status=Battle.CANCELLED)
    current = _current_battle(request.user)
    if current and current.status == Battle.ACTIVE:
        _check_timeout(current.pk)
        current = _current_battle(request.user)
    invites = Battle.objects.filter(status=Battle.OPEN, invited=request.user, last_seen__gte=_fresh()) \
        .select_related('player1', 'team1')
    rating = Rating.objects.filter(user=request.user).first()
    history = (Battle.objects.filter(Q(player1=request.user) | Q(player2=request.user), status=Battle.FINISHED)
               .select_related('player1', 'player2', 'winner').order_by('-finished_at')[:8])
    return render(request, 'arena/lobby.html', {
        'teams': _playable_teams(request.user), 'current': current, 'invites': invites,
        'rating': rating, 'history': history,
        'waiting': Battle.objects.filter(status=Battle.OPEN, invited__isnull=True, last_seen__gte=_fresh())
                         .exclude(player1=request.user).count(),
        'top': Rating.objects.select_related('user')[:5],
        'preselect': request.GET.get('team', ''),
    })


@login_required
def lobby_status(request):
    current = _current_battle(request.user)
    return JsonResponse({
        'invites': Battle.objects.filter(status=Battle.OPEN, invited=request.user, last_seen__gte=_fresh()).count(),
        'battle': current.pk if current else None,
    })


@login_required
@require_POST
def queue_join(request):
    if _busy(request):
        return redirect('arena:lobby')
    team = _posted_team(request)
    if not team:
        return redirect('arena:lobby')
    candidates = (Battle.objects.filter(status=Battle.OPEN, invited__isnull=True, last_seen__gte=_fresh())
                  .exclude(player1=request.user).select_related('player1', 'team1').order_by('created_at'))
    for battle in candidates:
        if _start(battle, request.user, team):
            return redirect(battle)
    battle = Battle.objects.create(player1=request.user, team1=team)
    return redirect(battle)


@login_required
@require_POST
def challenge(request):
    if _busy(request):
        return redirect('arena:lobby')
    team = _posted_team(request)
    if not team:
        return redirect('arena:lobby')
    name = request.POST.get('opponent', '').strip()
    opponent = get_user_model().objects.filter(username__iexact=name, is_active=True).first()
    if not opponent or opponent == request.user:
        messages.error(request, f'Trainer „{name}“ nicht gefunden.' if name else 'Bitte einen Trainernamen eingeben.')
        return redirect('arena:lobby')
    battle = Battle.objects.create(player1=request.user, team1=team, invited=opponent)
    return redirect(battle)


@login_required
@require_POST
def challenge_accept(request, pk):
    battle = get_object_or_404(Battle.objects.select_related('player1', 'team1'), pk=pk, invited=request.user)
    if _busy(request):
        return redirect('arena:lobby')
    team = _posted_team(request)
    if not team:
        return redirect('arena:lobby')
    if battle.last_seen < _fresh() or not _start(battle, request.user, team):
        messages.error(request, 'Die Herausforderung ist nicht mehr aktuell.')
        return redirect('arena:lobby')
    return redirect(battle)


@login_required
@require_POST
def challenge_decline(request, pk):
    Battle.objects.filter(pk=pk, invited=request.user, status=Battle.OPEN).update(status=Battle.CANCELLED)
    return redirect('arena:lobby')


@login_required
def battle_page(request, pk):
    battle = get_object_or_404(Battle.objects.select_related('player1', 'player2', 'invited'), pk=pk)
    if battle.side_of(request.user) is None:
        raise Http404
    return render(request, 'arena/battle.html', {'battle': battle})


@login_required
def battle_state(request, pk):
    battle = get_object_or_404(Battle.objects.select_related('invited'), pk=pk)
    if battle.side_of(request.user) is None:
        raise Http404
    if battle.status == Battle.OPEN:
        Battle.objects.filter(pk=pk, status=Battle.OPEN).update(last_seen=_now())
    elif battle.status == Battle.ACTIVE and battle.turn_deadline and _now() > battle.turn_deadline:
        _check_timeout(pk)
        battle.refresh_from_db()
    return JsonResponse(_payload(battle, request.user))


@login_required
@require_POST
def battle_action(request, pk):
    with transaction.atomic():
        battle = get_object_or_404(Battle.objects.select_for_update(of=('self',)).select_related('player1', 'player2'), pk=pk)
        side = battle.side_of(request.user)
        if side is None:
            raise Http404
        action = None
        if battle.status == Battle.ACTIVE:
            try:
                index = int(request.POST.get('index', ''))
            except ValueError:
                index = -1
            action = engine.valid_action(battle.state, side, request.POST.get('type'), index)
        if action is None:
            return JsonResponse(_payload(battle, request.user), status=400)
        if engine.submit(battle.state, side, action, load_chart()[1]):
            _after_turn(battle)
        battle.save()
    return JsonResponse(_payload(battle, request.user))


@login_required
@require_POST
def battle_forfeit(request, pk):
    with transaction.atomic():
        battle = get_object_or_404(Battle.objects.select_for_update(of=('self',)).select_related('player1', 'player2'), pk=pk)
        side = battle.side_of(request.user)
        if side is None:
            raise Http404
        if battle.status == Battle.OPEN:
            battle.status = Battle.CANCELLED
            battle.save()
            return redirect('arena:lobby')
        if battle.status == Battle.ACTIVE:
            _finish(battle, 1 - side, 'forfeit')
            battle.save()
    return redirect(battle)


def leaderboard(request):
    ratings = list(Rating.objects.select_related('user')
                   .filter(Q(wins__gt=0) | Q(losses__gt=0) | Q(draws__gt=0))[:100])
    recent = (Battle.objects.filter(status=Battle.FINISHED)
              .select_related('player1', 'player2', 'winner').order_by('-finished_at')[:10])
    return render(request, 'arena/leaderboard.html', {'ratings': ratings, 'recent': recent})
