from django.urls import path

from . import views

app_name = 'arena'

urlpatterns = [
    path('', views.lobby, name='lobby'),
    path('status/', views.lobby_status, name='lobby_status'),
    path('suchen/', views.queue_join, name='queue_join'),
    path('herausfordern/', views.challenge, name='challenge'),
    path('herausforderung/<int:pk>/annehmen/', views.challenge_accept, name='challenge_accept'),
    path('herausforderung/<int:pk>/ablehnen/', views.challenge_decline, name='challenge_decline'),
    path('rangliste/', views.leaderboard, name='leaderboard'),
    path('kampf/<int:pk>/', views.battle_page, name='battle'),
    path('kampf/<int:pk>/status/', views.battle_state, name='battle_state'),
    path('kampf/<int:pk>/aktion/', views.battle_action, name='battle_action'),
    path('kampf/<int:pk>/aufgeben/', views.battle_forfeit, name='battle_forfeit'),
]
