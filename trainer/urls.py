from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'trainer'

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('registrieren/', views.signup, name='signup'),
    path('', views.dashboard, name='dashboard'),
    path('favorit/<int:pokemon_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('teams/community/', views.community_teams, name='community'),
    path('teams/neu/', views.team_create, name='team_create'),
    path('teams/<int:pk>/', views.team_detail, name='team_detail'),
    path('teams/<int:pk>/bearbeiten/', views.team_update, name='team_update'),
    path('teams/<int:pk>/loeschen/', views.team_delete, name='team_delete'),
    path('teams/<int:pk>/hinzufuegen/', views.team_add, name='team_add'),
    path('teams/<int:pk>/entfernen/<int:member_id>/', views.team_remove, name='team_remove'),
    path('teams/<int:pk>/attacken/<int:member_id>/', views.member_moves, name='member_moves'),
]
