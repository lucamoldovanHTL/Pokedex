from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'Pokédex Verwaltung'
admin.site.site_title = 'Pokédex Admin'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('trainer/', include('trainer.urls')),
    path('arena/', include('arena.urls')),
    path('', include('pokedex.urls')),
]
