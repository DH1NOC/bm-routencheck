# BM-Routencheck — Entwickler-README

Technische Dokumentation für alle, die am Code arbeiten. Die Bedienung und
die fertigen Downloads beschreibt die [README](README.md); offene Punkte,
verbindliche Festlegungen und die Eigenheiten der externen Datenquellen
stehen in [`PROJEKTPLAN.md`](PROJEKTPLAN.md).

## Inhalt

- [Entwicklungsumgebung](#entwicklungsumgebung)
- [Qualitätssicherung](#qualitätssicherung)
- [Projektstruktur](#projektstruktur)
- [Technische Highlights & Externe Technologien](#technische-highlights--externe-technologien)
- [Disk-Cache](#disk-cache)
- [Releases](#releases)

## Entwicklungsumgebung

Voraussetzungen: **Python ≥ 3.12** und **Git**.

```bash
git clone https://github.com/DH1NOC/bm-routencheck.git
cd bm-routencheck
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # Paket editierbar + Dev-Werkzeuge
```

Paketdefinition, Abhängigkeiten und Entry Points stehen in
[`pyproject.toml`](pyproject.toml). Die vier Kommandos (`bmtools`,
`bm-bahn`, `bm-auto`, `bm-rad`) sind dort als `project.scripts` registriert.

## Qualitätssicherung

```bash
make qs          # Lint (ruff) + Typprüfung (mypy strict) + Tests (pytest)
make abdeckung   # Tests mit HTML-Abdeckungsbericht (out/coverage/)
```

Dieselben Prüfungen laufen als GitHub-Actions-Workflow bei jedem Push
(`.github/workflows/qs.yml`). Konfiguriert ist alles in `pyproject.toml`:

- **ruff** — Lint inkl. Import-Sortierung, bugbear und Modernisierung;
  Ausnahmen (z. B. deutsche Typografie) sind dort begründet.
- **mypy strict** — der gesamte Quellcode ist streng typgeprüft; die
  wenigen Lockerungen (ungetypte Bibliotheken, Tests ohne
  Annotationszwang) sind als Overrides dokumentiert.
- **pytest + coverage** — getestet wird die Kernlogik (Parser, Geometrie,
  Abdeckungsschätzung, Berichte, Codeplug, API-Clients mit gemockten
  HTTP-Antworten). Interaktive CLIs und Karten-Rendering sind bewusst
  ausgenommen; die Untergrenze (`fail_under`) sichert das erreichte
  Niveau ab, ohne Statistik-Kosmetik zu belohnen.

## Projektstruktur

```text
bm-routencheck/
├── bmtools/              # Python-Paket mit allen Tools
│   ├── bm_api/           # Brandmeister-API-Client (HTTP, Disk-Cache, Datenmodelle)
│   ├── fm_api/           # DL3EL-Client für analoge FM-Relais (Umkreissuche,
│   │                     #   defensiver CSV/GPX-Parser, Disk-Cache)
│   ├── routelib/         # Gemeinsamer Kern: Geländemodell/Erreichbarkeit,
│   │                     #   Bericht, Karte, CSV, Codeplug-Export, Pipeline
│   ├── rail/             # bm-bahn (Bahnverbindungen via Transitous)
│   ├── road/             # bm-auto / bm-rad (Maps-/Komoot-Link, GPX, OSRM, Geocoding)
│   ├── cli.py            # bmtools-Einstieg: Menü, Subcommand-Dispatcher, Cache-Befehl
│   ├── cache_admin.py    # Cache-Bereiche auflisten/leeren (UI-frei)
│   └── ui.py             # Gemeinsames CLI-Erscheinungsbild (Banner, Farben,
│                         #   Fortschrittsbalken mit ETA ab 10 s Restzeit)
├── tests/                # pytest-Suite (Parser, Geometrie, Berichte, Clients)
├── packaging/            # PyInstaller-Einstieg + macOS-Entitlements für Releases
├── out/                  # Generierte Berichte/Karten/CSV je Route (nicht versioniert)
├── pyproject.toml        # Paketdefinition, Abhängigkeiten, Entry Points
├── PROJEKTPLAN.md        # Offene Punkte, Festlegungen, API-Eigenheiten
└── README.md             # Endnutzer-Dokumentation
```

- **`bmtools/bm_api/`** — wiederverwendbarer, gecachter Client für die
  Brandmeister-API; unabhängig von den Routen-Tools nutzbar.
- **`bmtools/fm_api/`** — Gegenstück für relaislisten.darc.de (DL3EL):
  Umkreisabfragen je Streckenraster, Parser für die „schmutzigen"
  CSV/GPX-Antworten, Dedupe über (Rufzeichen, Frequenz).
- **`bmtools/routelib/`** — die gesamte Auswertung von der Routen-Geometrie
  bis zu den Ausgabedateien; die Tools in `rail/` und `road/` liefern nur die
  Route an diese Pipeline.

Die Bibliotheksschichten (`bm_api`, `fm_api`, `routelib`) sind UI-frei;
Fortschritt wird über optionale `(fertig, gesamt)`-Callbacks gemeldet, an
die erst die Pipeline die rich-Fortschrittsbalken aus `ui.py` hängt.

## Technische Highlights & Externe Technologien

**Kernbibliotheken** (siehe [`pyproject.toml`](pyproject.toml)):

- [httpx](https://www.python-httpx.org/) — HTTP-Client für alle API-Zugriffe
- [Rich](https://rich.readthedocs.io/) und
  [Questionary](https://questionary.readthedocs.io/) — Terminal-Ausgabe und
  interaktive Auswahlmenüs
- [Folium](https://python-visualization.github.io/folium/) — erzeugt die
  interaktive Karte auf Basis von [Leaflet](https://leafletjs.com/) und
  [OpenStreetMap](https://www.openstreetmap.org/)
- [NumPy](https://numpy.org/) und [Pillow](https://python-pillow.org/) —
  Geländemodell: Höhenraster dekodieren und Sichtlinien berechnen
- [platformdirs](https://platformdirs.readthedocs.io/) — plattformgerechter
  Ablageort für den Disk-Cache

**Externe Dienste** (alle ohne API-Key nutzbar):

- [Brandmeister-API v2](https://api.brandmeister.network/v2/) — DMR-Relais,
  Frequenzen, Talkgroup-Profile
- [DL3EL-Relaisliste](https://relaislisten.darc.de) — analoge FM-Relais
  (Frequenzen, CTCSS) per Umkreissuche entlang der Route
- [Transitous](https://transitous.org) — Bahnverbindungen inklusive
  Streckengeometrie sowie Geocoding für `bm-auto`/`bm-rad`
- [OSRM auf FOSSGIS-Servern](https://routing.openstreetmap.de) — Auto- und
  Radrouting auf OpenStreetMap-Daten
- [Komoot-API](https://www.komoot.com) — exakte Geometrie gespeicherter Touren
- [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) —
  Höhendaten (Terrarium-Format) für das Sichtlinien-Modell

Die Erreichbarkeit wird pro Streckenpunkt über echte Höhenprofile mit
4/3-Erdradius berechnet (`routelib/coverage.py`, `routelib/terrain.py`);
die Karten-Sichtfelder entstehen als Radialstrahl-Viewsheds in einem
Prozesspool (`routelib/viewshed_raster.py`).

## Disk-Cache

Alle Caches liegen unter dem platformdirs-Cache-Verzeichnis des Nutzers
(macOS: `~/Library/Caches/bmtools`, Linux: `~/.cache/bmtools`, Windows:
`%LOCALAPPDATA%\bmtools`):

| Bereich | Namespace/Ordner | TTL |
|---|---|---|
| BM-Geräteliste | `bmtools/devices` | 1 Tag |
| BM-Talkgroup-Profile | `bmtools/profiles` | 12 h |
| BM-Sonstiges (TG-Namen) | `bmtools/misc` | 7 Tage |
| FM-Relaisliste (Rohantworten) | `bmtools/fm` | 1 Tag |
| Höhenkacheln | `bmtools/terrain/<zoom>` | unbegrenzt |

`bmtools/cache_admin.py` listet und leert diese Bereiche (Menüpunkt
»Cache leeren« bzw. `bmtools cache --leeren`); es bildet die Pfade mit
denselben `user_cache_dir`-Aufrufen wie die Clients, damit sie auf jeder
Plattform übereinstimmen.

## Releases

Releases werden manuell über GitHub Actions gebaut:
**Actions → Release → „Run workflow"**, dort Branch und Versionssprung wählen.

- **Branch bestimmt die Art:** `main` erzeugt einen regulären Release
  (Version wird in `pyproject.toml` committet und getaggt, z. B. `v0.2.0`);
  jeder andere Branch erzeugt eine **Beta** (nur Tag, z. B. `v0.2.0-beta.1`,
  auf GitHub als Pre-Release markiert — die Versionsnummer im Branch bleibt
  unverändert).
- **Versionssprung:** `major` erhöht die Featureversion (`0.1.0 → 0.2.0`),
  `minor` den Patch (`0.1.0 → 0.1.1`).
- **Assets:** Quell-ZIP sowie eigenständige PyInstaller-Binaries — Windows
  (x64) als nackte `.exe`, Linux (x64) als `.tar.gz`, macOS (Apple Silicon)
  als ZIP mit LIESMICH.txt. Die Binaries brauchen kein installiertes
  Python. Bewusst keine Installer-Pakete (.pkg/MSI; allenfalls wäre ein
  DMG zulässig — Nutzerfestlegung 2026-07-17).
- **Gatekeeper/SmartScreen:** Die Endnutzer-Hinweise zu macOS-Start und
  Windows-Warnungen stehen in der [README](README.md#download--start);
  eine LIESMICH.txt mit dem macOS-Hinweis wird ins ZIP gepackt. Der
  Release-Workflow veröffentlicht erst, wenn Apples Server das
  Notarisierungs-Ticket ausliefern — die Gatekeeper-Prüfung funktioniert
  also direkt ab Veröffentlichung.

### macOS-Signierung und Notarisierung

Das macOS-Binary wird automatisch signiert und notarisiert, wenn folgende
**Repository-Secrets** (Settings → Secrets and variables → Actions) gesetzt
sind — fehlen sie, wird mit Warnung unsigniert gebaut:

| Secret | Inhalt |
| --- | --- |
| `APPLE_CERT_P12` | „Developer ID Application"-Zertifikat als Base64 (`base64 -i zertifikat.p12 \| pbcopy`) |
| `APPLE_CERT_PASSWORD` | Passwort des `.p12`-Exports |
| `APPLE_ID` | Apple-ID (E-Mail) des Developer-Accounts |
| `APPLE_TEAM_ID` | Team-ID (developer.apple.com → Membership) |
| `APPLE_APP_PASSWORD` | App-spezifisches Passwort (account.apple.com → Anmeldung & Sicherheit) |

Das Zertifikat lässt sich am einfachsten in Xcode erstellen
(Settings → Accounts → Team → „Manage Certificates…" → „+" →
„Developer ID Application") und dort per Rechtsklick →
„Export Certificate…" als `.p12` mit Passwort exportieren.

### Windows-Signierung

Die `.exe` ist derzeit nicht code-signiert: Microsofts Signaturdienst
(Trusted Signing) steht Einzelentwicklern in Deutschland nicht offen,
klassische Zertifikate kosten laufend Geld. Daher die
SmartScreen-/Smart-App-Control-Hinweise in der README.
