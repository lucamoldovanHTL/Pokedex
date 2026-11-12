# Pokédex – Django-Webanwendung

Eine Pokédex-Webanwendung mit eigener Datenbank, Trainerkonten, Favoriten, Team-Builder und Kampf-Simulator.
Aufbauend auf **A20** (Pokémon-Datenbank mit Django-ORM) und **A23** (Django-Projekt „HTL Events“).

## Features

- **Pokédex**: alle 898 Arten bzw. 1092 Pokémon inklusive Formen (Mega, Alola, Galar …), mit Suche nach Name oder Nummer, Filtern nach Typ, 2. Typ, Generation und Legendär/Mysteriös sowie Sortierung nach jedem Statuswert
- **Detailseite**: Artwork, Pokédex-Eintrag, Basiswerte, Steckbrief, Fähigkeiten, Schwächen/Resistenzen, Entwicklungsreihe mit Bedingungen, Formen und Attacken (Level, TM, Zucht, Lehrer)
- **Typen-Tabelle**: komplette 18×18-Effektivitätsmatrix
- **Kampf-Simulator**: zwei Pokémon im Vergleich (Level 50, beste STAB-Attacke, Typ-Effektivität, Initiative)
- **Trainerkonto**: Registrierung, Login, Favoriten
- **Team-Builder**: Teams mit bis zu 6 Pokémon (inklusive Spitznamen), defensive Typ-Analyse, offensive Abdeckung, öffentliche Community-Teams
- **Online-Arena**: Trainer kämpfen live mit ihren Teams gegeneinander (ein Pokémon gleichzeitig, Attacke oder Wechsel pro Runde), per Warteschlange oder gezielter Herausforderung; die Attacken (max. 4 pro Pokémon) legt man vorher auf der Team-Seite fest
- **Rangliste**: Elo-Wertung aller Arena-Kämpfe unter `/arena/rangliste/`
- **JSON-API**: `/api/pokemon/?q=…` und `/api/pokemon/<name>/`
- **Admin-Bereich** unter `/admin/`
- Alle Texte auf **Deutsch** (Fallback Englisch), responsives Bootstrap-5-Design

## Architektur

| Entscheidung | Umsetzung |
|---|---|
| Datenquelle | Eigene DB, importiert aus dem CSV-Export von A20 (`data/csv/`), keine Laufzeit-Abhängigkeit von externen APIs |
| Datenmodell | Normalisierte Django-Models mit echten Fremdschlüsseln (statt `managed=False` wie in A20) |
| Datenbank | Lokal SQLite, am Server PostgreSQL, umschaltbar über `DATABASE_URL` |
| Deployment | Docker Compose: PostgreSQL + Gunicorn + Caddy (automatisches HTTPS) |
| Bilder | Offizielle Artworks von [PokéAPI/sprites](https://github.com/PokeAPI/sprites) (per URL eingebunden) |

```
Pokemon_tdot/
├── config/              # Django-Einstellungen (settings, urls, wsgi)
├── pokedex/             # Pokédex-App
│   ├── models.py        # Generation, Type, Ability, Move, Species, Pokemon, …
│   ├── typechart.py     # Typ-Effektivität, Team-Analyse, Kampfsimulation
│   ├── views.py         # Seiten + JSON-API
│   └── management/commands/import_pokedex.py
├── arena/               # Online-Kämpfe, Rangliste (engine.py = Kampfregeln)
├── trainer/             # Konten, Favoriten, Teams
│   └── management/commands/load_demo.py
├── templates/           # HTML-Templates (Bootstrap 5)
├── static/              # CSS, JS (Autovervollständigung), Favicon
├── data/csv/            # Pokédex-Rohdaten (veekun-Export aus A20)
├── docker/              # entrypoint.sh, Caddyfile
├── Dockerfile
└── docker-compose.yml
```

### Arena

Die Arena (`arena/`) kommt ohne WebSockets aus: der Browser fragt alle 1,5 Sekunden den Kampfzustand ab und schickt Aktionen per POST. Der Zustand liegt als JSON in `Battle.state`, die Regeln stehen in `arena/engine.py` (Level 50, nur Schadensattacken, Typ-Effektivität, STAB, Volltreffer, 60 Sekunden Bedenkzeit pro Runde).

`python manage.py setup_boss_team` legt für jeden Superuser das private Team „Teichfreunde“ an (`Team.is_boss`). Es sieht harmlos aus, kann in der Arena aber nicht besiegt werden; das Flag wirkt nur bei Superusern und lässt sich im Admin-Bereich ein- und ausschalten.

## Lokal starten (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py import_pokedex      # ca. 10 Sekunden
python manage.py load_demo           # optional: Demo-Trainer
python manage.py createsuperuser     # optional: Admin-Konto
python manage.py runserver
```

Dann im Browser öffnen: **http://127.0.0.1:8000**

Unter Mac/Linux lautet die Aktivierung `source .venv/bin/activate`.

### Demo-Zugangsdaten (nach `load_demo`)

| Benutzer | Passwort |
|---|---|
| `ash` | `demo1234` |
| `misty` | `demo1234` |

### Tests

```powershell
python manage.py test
```

## Deployment auf einen externen Server

Voraussetzung: ein Linux-Server (z. B. Ubuntu-VPS) mit Docker und einer Domain, deren DNS-A-Eintrag auf den Server zeigt.

```bash
# 1. Docker installieren (einmalig)
curl -fsSL https://get.docker.com | sh

# 2. Projekt auf den Server bringen
git clone <repo-url> pokedex && cd pokedex     # oder per scp/rsync kopieren

# 3. Konfiguration anlegen und ausfüllen
cp .env.example .env
nano .env        # DOMAIN, DJANGO_SECRET_KEY, Passwörter setzen

# 4. Starten
docker compose up -d --build
```

Beim ersten Start werden automatisch die Migrationen ausgeführt, der Pokédex in PostgreSQL importiert und (falls in `.env` gesetzt) das Admin-Konto angelegt.
Caddy holt sich selbst ein HTTPS-Zertifikat.

Einen sicheren Secret Key erzeugst du mit:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Nützliche Befehle:

```bash
docker compose logs -f web                              # Logs ansehen
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py import_pokedex # Pokédex neu importieren
git pull && docker compose up -d --build                # Update einspielen
docker compose exec db pg_dump -U pokedex pokedex > backup.sql   # Backup
```

> Achtung: `import_pokedex` löscht und erstellt alle Pokédex-Tabellen neu. Dabei gehen auch Favoriten und Teammitglieder verloren, weil sie auf Pokémon verweisen.

## Daten & Rechtliches

- Pokédex-Daten: [veekun/pokedex](https://github.com/veekun/pokedex) (CSV-Export, Stand Gen. 8)
- Bilder: [PokéAPI/sprites](https://github.com/PokeAPI/sprites)
- Pokémon und alle zugehörigen Namen sind Marken von Nintendo, Game Freak und The Pokémon Company. Dies ist ein nicht-kommerzielles Schulprojekt.
