from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from arena import engine
from config.security import rate_limited
from pokedex.models import Pokemon
from pokedex.typechart import team_analysis

from .forms import SignupForm, TeamForm
from .models import MAX_TEAM_SIZE, Favorite, Team, TeamMember


def _redirect_back(request, fallback):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return redirect(nxt)
    return redirect(fallback)


def _members_qs():
    return TeamMember.objects.select_related('pokemon__species').prefetch_related('pokemon__pokemon_types__type')


def signup(request):
    if request.user.is_authenticated:
        return redirect('pokedex:home')
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if rate_limited(request, 'signup', limit=5, window=3600):
            messages.error(request, 'Von deinem Gerät wurden zu viele Konten erstellt. Bitte später erneut versuchen.')
            return render(request, 'registration/signup.html', {'form': form}, status=429)
        user = form.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, f'Willkommen, {user.username}! Dein Trainerkonto ist bereit.')
        return redirect('trainer:dashboard')
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def dashboard(request):
    favorites = (request.user.favorites.select_related('pokemon__species')
                 .prefetch_related('pokemon__pokemon_types__type'))
    teams = request.user.teams.prefetch_related(Prefetch('members', queryset=_members_qs()))
    return render(request, 'trainer/dashboard.html', {'favorites': favorites, 'teams': teams})


@login_required
@require_POST
def toggle_favorite(request, pokemon_id):
    pokemon = get_object_or_404(Pokemon.objects.select_related('species'), pk=pokemon_id)
    fav, created = Favorite.objects.get_or_create(user=request.user, pokemon=pokemon)
    if created:
        messages.success(request, f'{pokemon} zu deinen Favoriten hinzugefügt.')
    else:
        fav.delete()
        messages.info(request, f'{pokemon} aus deinen Favoriten entfernt.')
    return _redirect_back(request, pokemon.get_absolute_url())


# ------------------------------------------------------------------ Teams

def community_teams(request):
    teams = (Team.objects.filter(is_public=True).select_related('user')
             .prefetch_related(Prefetch('members', queryset=_members_qs()))
             .annotate(n=Count('members')).filter(n__gt=0)[:50])
    return render(request, 'trainer/community.html', {'teams': teams})


@login_required
def team_create(request):
    form = TeamForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        team = form.save(commit=False)
        team.user = request.user
        team.save()
        messages.success(request, f'Team „{team.name}“ erstellt. Füge jetzt Pokémon hinzu!')
        return redirect(team)
    return render(request, 'trainer/team_form.html', {'form': form})


def team_detail(request, pk):
    team = get_object_or_404(Team.objects.select_related('user'), pk=pk)
    is_owner = request.user == team.user
    if not is_owner and not team.is_public:
        raise Http404
    members = list(_members_qs().filter(team=team).prefetch_related('moves__type'))
    pokemon = [m.pokemon for m in members]
    return render(request, 'trainer/team_detail.html', {
        'team': team, 'members': members, 'is_owner': is_owner,
        'analysis': team_analysis(pokemon) if pokemon else None,
        'empty_slots': range(MAX_TEAM_SIZE - len(members)),
        'form': TeamForm(instance=team) if is_owner else None,
        'avg_total': round(sum(p.total for p in pokemon) / len(pokemon)) if pokemon else 0,
    })


def _own_team(request, pk):
    return get_object_or_404(Team, pk=pk, user=request.user)


@login_required
@require_POST
def team_update(request, pk):
    team = _own_team(request, pk)
    form = TeamForm(request.POST, instance=team)
    if form.is_valid():
        form.save()
        messages.success(request, 'Team gespeichert.')
    else:
        messages.error(request, 'Bitte Eingaben prüfen.')
    return redirect(team)


@login_required
@require_POST
def team_delete(request, pk):
    team = _own_team(request, pk)
    team.delete()
    messages.info(request, f'Team „{team.name}“ gelöscht.')
    return redirect('trainer:dashboard')


@login_required
@require_POST
def team_add(request, pk):
    team = _own_team(request, pk)
    ident = request.POST.get('pokemon', '').strip()
    pokemon = (Pokemon.objects.select_related('species').filter(identifier=ident).first()
               or Pokemon.objects.select_related('species')
               .filter(Q(species__name__iexact=ident), is_default=True).first())
    if not pokemon:
        messages.error(request, 'Pokémon nicht gefunden. Bitte aus der Vorschlagsliste wählen.')
        return _redirect_back(request, team.get_absolute_url())
    with transaction.atomic():
        used = set(team.members.select_for_update().values_list('slot', flat=True))
        free = [s for s in range(1, MAX_TEAM_SIZE + 1) if s not in used]
        if not free:
            messages.error(request, f'„{team.name}“ ist schon voll (max. {MAX_TEAM_SIZE} Pokémon).')
            return _redirect_back(request, team.get_absolute_url())
        TeamMember.objects.create(team=team, pokemon=pokemon, slot=free[0],
                                  nickname=request.POST.get('nickname', '')[:30])
        team.save(update_fields=['updated_at'])
    messages.success(request, f'{pokemon} zu „{team.name}“ hinzugefügt.')
    return _redirect_back(request, team.get_absolute_url())


@login_required
def member_moves(request, pk, member_id):
    """Attacken eines Teammitglieds für die Arena vorab festlegen (max. 4 aus allen erlernbaren)."""
    team = _own_team(request, pk)
    member = get_object_or_404(_members_qs(), pk=member_id, team=team)
    pool = engine.learnset(member.pokemon)
    if request.method == 'POST':
        allowed = {str(m.id): m for m in pool}
        chosen = [allowed[i] for i in dict.fromkeys(request.POST.getlist('moves')) if i in allowed]
        if len(chosen) > engine.MAX_MOVES:
            messages.error(request, f'Du kannst höchstens {engine.MAX_MOVES} Attacken wählen.')
            return redirect('trainer:member_moves', team.pk, member.pk)
        member.moves.set(chosen)
        messages.success(request, f'Attacken für {member} gespeichert.' if chosen
                         else f'{member} nutzt wieder die automatische Auswahl.')
        return redirect(team)
    chosen_ids = set(member.moves.values_list('id', flat=True))
    return render(request, 'trainer/member_moves.html', {
        'team': team, 'member': member, 'pool': pool, 'chosen_ids': chosen_ids,
        'auto': engine.auto_moves(member.pokemon, pool), 'max_moves': engine.MAX_MOVES,
    })


@login_required
@require_POST
def team_remove(request, pk, member_id):
    team = _own_team(request, pk)
    member = get_object_or_404(TeamMember, pk=member_id, team=team)
    member.delete()
    messages.info(request, f'{member} aus dem Team entfernt.')
    return redirect(team)
