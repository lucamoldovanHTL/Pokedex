from django.urls import path

from . import views

app_name = 'pokedex'

urlpatterns = [
    path('', views.home, name='home'),
    path('pokedex/', views.pokemon_list, name='list'),
    path('pokedex/<slug:identifier>/', views.pokemon_detail, name='detail'),
    path('typen/', views.type_chart, name='types'),
    path('kampf/', views.battle, name='battle'),
    path('api/pokemon/', views.api_pokemon_search, name='api_search'),
    path('api/pokemon/<slug:identifier>/', views.api_pokemon_detail, name='api_detail'),
]
