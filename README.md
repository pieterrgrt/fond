# Fond

Een persoonlijke kookcursus als webapp. Geen receptenverzameling, maar een
opbouwende cursus met de keukenbrigade als leerpad: van **Commis** via
**Chef de partie** en **Sous-chef** naar **Chef**. Meal prep en lunch zonder brood
lopen als rode draad door de cursus. Boodschappen gaan uit van de Aldi Süd.

- **Cursusoverzicht** met niveaus, modules, voortgang en de volgende les
- **Lessen** met theorie, techniek, recept, opdracht en *proeven* (reflectie)
- **Kookmodus** op het volle scherm: grote tekst, timers, scherm blijft aan
- **Porties schalen** (×1 tot ×6), met slimme afronding
- **Boodschappenlijst** per les of per week, op volgorde van je route door de winkel
- **Logboek** van alles wat je hebt gekookt
- **PWA**: installeerbaar op je beginscherm, lessen werken offline

Gebouwd met Python (FastAPI), server-rendered HTML met een beetje HTMX, en SQLite.
Geen externe diensten, geen trackers, geen Google: lettertypen en scripts staan in de repo.

---

## Lokaal draaien

Nodig: [uv](https://docs.astral.sh/uv/) (installeert zelf de juiste Python).

```sh
uv sync                       # afhankelijkheden installeren
uv run fond hash-wachtwoord   # kies een wachtwoord; zet de twee regels in .env
uv run uvicorn fond.main:create_app --factory --reload --port 8098
```

Open <http://localhost:8098>. Lokaal hoeft `FOND_SECURE_COOKIES` niet aan (de
standaard is uit); op de server staat hij aan, want daar is alles HTTPS.

Je gegevens (database en foto's) komen in `data/`. Die map staat niet in git.

### Tests en controles

```sh
uv run pytest           # alle tests
uv run ruff check .     # stijl en veelgemaakte fouten
uv run ruff format .    # opmaak
uv run fond check       # valideer de lesinhoud
```

---

## Deployen op de server

De app draait als één container en luistert alleen op `127.0.0.1:8098`, net als
je andere apps. nginx op de server heeft het TLS-certificaat en stuurt het
verkeer daarheen.

```
internet ─▶ :443 SNI-router ─▶ 127.0.0.1:8444 nginx (TLS) ─▶ 127.0.0.1:8098 Fond
```

### Eenmalig

1. **DNS**: een A-record (en eventueel AAAA) voor `fond.regoort.me` naar je server.
2. **Code ophalen**:
   ```sh
   git clone git@github.com:pieterrgrt/fond.git ~/fond && cd ~/fond
   ```
3. **Instellingen**:
   ```sh
   cp .env.example .env
   docker compose build
   docker compose run --rm fond fond hash-wachtwoord   # plak de uitvoer in .env
   ```
4. **Datamap** (de container draait als gebruiker 1000, niet als root):
   ```sh
   mkdir -p data && sudo chown 1000:1000 data
   ```
5. **Starten**:
   ```sh
   docker compose up -d
   curl -s 127.0.0.1:8098/gezond     # {"status":"ok"}
   ```
6. **Certificaat**: vraag het aan zoals voor je andere subdomeinen (bv. certbot).
7. **Nginx**: zet [`deploy/nginx/fond.regoort.me.conf`](deploy/nginx/fond.regoort.me.conf)
   in `/etc/nginx/sites-available/` en link het in `sites-enabled/`. Neem de
   `listen`- en `ssl_`-regels over uit een serverblok dat al werkt. Dan:
   ```sh
   nginx -t && systemctl reload nginx
   ```
8. **SNI-router**: als die per domein routeert, voeg `fond.regoort.me` toe met als
   doel `127.0.0.1:8444` (zoals je andere sites).
9. **Installeren op je telefoon**: open <https://fond.regoort.me> in Safari, log in,
    en kies *Deel → Zet op beginscherm*.

### Bijwerken

```sh
cd ~/fond && git pull
docker compose up -d --build      # na codewijzigingen
docker compose restart            # na alleen nieuwe of gewijzigde lessen
```

De lessen (`content/`) worden vanuit je checkout in de container gekoppeld, dus
voor nieuwe lessen hoeft de image niet opnieuw gebouwd te worden. Bij het
opstarten wordt alle inhoud gevalideerd: zit er een fout in, dan start de app niet
en staat de melding in `docker compose logs fond`. Controleer daarom eerst met
`uv run fond check` (lokaal) of `docker compose run --rm fond fond check`.

Databasewijzigingen (migraties) worden bij het opstarten automatisch toegepast.

### Back-ups

```sh
docker compose exec fond fond backup    # kopie in data/backups/, laatste 14 bewaard
```

Zet dat in een dagelijkse cronjob op de server, en neem de hele map `data/`
(database, back-ups en foto's) mee in je eigen server-back-up:

```cron
15 3 * * * cd /home/<jij>/fond && docker compose exec -T fond fond backup >/dev/null
```

---

## Lessen toevoegen of wijzigen

Alle inhoud staat in `content/`. Je voortgang staat los daarvan in de database,
gekoppeld aan het `id` van de les. Je kunt bestanden dus hernoemen zonder je
geschiedenis kwijt te raken, maar verander het `id` niet.

```
content/
  cursus.yaml          niveaus en modules (met `vereist` en `zelftoets`)
  winkel.yaml          de looproute door de Aldi (volgorde = volgorde op je lijst)
  ingredienten.yaml    ingrediënten: Nederlandse en Duitse naam, afdeling, verpakking
  technieken.yaml      technieken en termen (ook de woordenlijst)
  commis/
    01-mise-en-place.md
    02-het-koksmes.md
    ...
```

Een les is een Markdown-bestand met YAML-frontmatter tussen `---`-regels. De
kleinste geldige les:

```markdown
---
id: mijn-les                 # uniek, kleine letters en streepjes, nooit meer wijzigen
titel: Mijn les
module: warmte               # een module-id uit cursus.yaml
volgorde: 4                  # plek binnen de module
duur: 60                     # minuten
samenvatting: Eén of twee zinnen.
vereist: [bakken]            # lessen die eerst af moeten (optioneel)
technieken: [sauteren]       # wat deze les aanleert (uit technieken.yaml)
herhaalt: [mise-en-place]    # eerder aangeleerde technieken die terugkomen
recept:
  naam: Naam van het gerecht
  porties: 3
  tijd_actief: 30
  tijd_totaal: 45
  eiwit_per_portie: 30       # grove schatting (optioneel)
  ingredienten:
    - {item: ui, hoeveelheid: 1, eenheid: stuk, notitie: fijngesneden}
    - {item: raapzaadolie, hoeveelheid: 1, eenheid: el, schaal: beperkt}
    - {item: zout}           # zonder hoeveelheid = naar smaak
  stappen:
    - tekst: Wat je doet.
    - tekst: Iets met een timer.
      timer: 10m             # of 45s, 1u30m
      timer_label: Sudderen
  meal_prep:                 # optioneel
    koelkast_dagen: 3
    vriezer_maanden: 2
    opwarmen: Hoe je het opwarmt.
opdracht:
  - Een punt voor de checklist.
kaarten:                     # optioneel, voor de Anki-export
  - {voor: Vraag?, achter: Antwoord.}
---

## Theorie

Het waarom. Link naar een term met [[sauteren]] of [[sauteren|andere tekst]].

## Techniek

Wat je oefent.

## Opdracht

Optionele toelichting bij de checklist.

## Proeven

Waar je op let bij het reflecteren.
```

**Schaalregels** per ingrediënt: `lineair` (standaard, ×3 porties is ×3),
`beperkt` (×3 porties is ×2: olie, zout, specerijen) en `vast` (schaalt niet mee).

**Let op bij YAML**: staat er in een tekst tussen `{ }` een komma of een dubbele
punt, zet de tekst dan tussen aanhalingstekens: `notitie: "in blokjes; apart bewaren"`.
`uv run fond check` vertelt precies welk bestand en welk veld niet klopt.

Een nieuw ingrediënt voeg je toe aan `ingredienten.yaml`. Geef een
`verpakking` op, met dezelfde eenheid als in je recepten, dan rekent de
boodschappenlijst uit hoeveel je moet kopen.

---

## Hoe het in elkaar zit (en waarom)

| Onderdeel | Keuze | Waarom |
| --- | --- | --- |
| Webframework | FastAPI + Jinja2 | Python, expliciet: je ziet hoe een verzoek door de app loopt. Licht genoeg voor een CX23. |
| Interactie | HTMX + een beetje eigen JS | Server-rendered pagina's. Alleen de kookmodus (timers, Wake Lock) en offline werken vragen JavaScript. |
| Database | SQLite (WAL) + Alembic | Eén gebruiker: een bestand volstaat. Alembic past het schema aan zonder data te verliezen. |
| Inhoud | Markdown + YAML in git | Lessen zijn data, geen code. Pydantic valideert alles bij het opstarten. |
| Inloggen | Argon2-hash in `.env`, ondertekende cookie | Basic auth werkt slecht in een geïnstalleerde PWA op iOS. Pogingen zijn beperkt per IP en in totaal. |
| Offline | Service worker | Pagina's: eerst netwerk, dan de bewaarde kopie. Statische bestanden met versie-hash uit de cache. |
| Beveiliging | CSP zonder inline scripts | Alleen code van de eigen server kan draaien. Foto's verliezen hun EXIF (GPS). |

Code-indeling (`src/fond/`):

- `content/` — het inhoudsformaat (`models.py`) en de lader met validatie (`loader.py`)
- `voortgang.py` — wanneer gaat een les of module open
- `schalen.py` — porties schalen en hoeveelheden weergeven
- `boodschappen.py` — lijsten samenvoegen en sorteren op de looproute
- `herhaling.py` — welke technieken toe zijn aan herhaling
- `db.py`, `migrations/` — de database
- `auth.py` — inloggen
- `web/routes.py` — alle pagina's; `templates/` en `static/` — HTML, CSS en JS

De kernlogica (schalen, ontgrendelen, lijsten, herhaling) is los van web en database
geschreven en heeft eigen tests in `tests/`.

## Lettertypen

[Fraunces](https://github.com/undercasetype/Fraunces) en
[Atkinson Hyperlegible](https://www.brailleinstitute.org/freefont/), beide onder de
SIL Open Font License; zie `src/fond/static/fonts/`.
