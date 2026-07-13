# BrandmeisterTools

Kommandozeilen-Tools, die ermitteln, welche DMR-Relais des
[Brandmeister-Netzwerks](https://brandmeister.network) entlang einer Route
erreichbar sind — per Bahn, Auto oder Fahrrad. Die Erreichbarkeit wird pro
Streckenpunkt über ein Sichtlinien-Geländemodell berechnet, nicht über einen
bloßen Entfernungsradius.

Drei Tools, ein gemeinsamer Kern:

| Kommando | Route aus |
|---|---|
| `bm-bahn` | Zugverbindung (Start-/Zielbahnhof, via [Transitous](https://transitous.org)) |
| `bm-auto` | Google-Maps-Link oder Start-/Zieladresse (OSRM-Routing) |
| `bm-rad` | Komoot-Tour, Google-Maps-Link, GPX-Datei oder Start/Ziel |

Jeder Lauf erzeugt in `out/<route>/` einen HTML-Bericht mit Kanaltabellen je
Relais (Rufzeichen, Frequenzen, Colorcode, Talkgroups in TS1/TS2), eine
interaktive Karte, eine CSV-Datei und einen AnyTone-Codeplug-Export.

Paketdefinition und Entry Points stehen in [`pyproject.toml`](pyproject.toml);
offene Punkte, verbindliche Festlegungen und die Eigenheiten der externen
Datenquellen in [`PROJEKTPLAN.md`](PROJEKTPLAN.md).

## Inhalt

- [Quick Start](#quick-start)
  - [Voraussetzungen](#voraussetzungen)
  - [Installation](#installation)
  - [Starten](#starten)
  - [Tests ausführen (Entwicklung)](#tests-ausführen-entwicklung)
- [Die Tools im Detail](#die-tools-im-detail)
  - [`bmtools` — gemeinsamer Einstieg](#bmtools--gemeinsamer-einstieg)
  - [`bm-bahn` — Relais entlang einer Bahnstrecke](#bm-bahn--relais-entlang-einer-bahnstrecke)
  - [`bm-auto` / `bm-rad` — Relais entlang einer Auto- oder Radroute](#bm-auto--bm-rad--relais-entlang-einer-auto--oder-radroute)
  - [Gemeinsame Parameter (alle Tools)](#gemeinsame-parameter-alle-tools)
- [Technische Highlights & Externe Technologien](#technische-highlights--externe-technologien)
- [Projektstruktur](#projektstruktur)

## Quick Start

### Voraussetzungen

- **Python ≥ 3.12**
- **Git**
- Keine API-Keys, keine `.env`-Datei — alle genutzten Dienste sind ohne
  Anmeldung lesbar.

Prüfen, ob eine passende Python-Version vorhanden ist:

```bash
python3 --version        # Windows: py --version
```

Zeigt der Befehl 3.12 oder neuer, weiter zu [Installation](#installation).
Andernfalls Python wie folgt installieren:

**macOS** — über [Homebrew](https://brew.sh/) oder den Installer von
[python.org](https://www.python.org/downloads/macos/):

```bash
brew install python
```

**Linux** — über den Paketmanager der Distribution:

```bash
# Debian/Ubuntu
sudo apt install python3 python3-venv python3-pip

# Fedora
sudo dnf install python3
```

Liefert die Distribution ein älteres Python als 3.12, den Installer von
[python.org](https://www.python.org/downloads/) verwenden.

**Windows** — über [winget](https://learn.microsoft.com/windows/package-manager/winget/)
oder den Installer von [python.org](https://www.python.org/downloads/windows/)
(dort die Option **„Add python.exe to PATH"** anhaken):

```powershell
winget install Python.Python.3.12
```

### Installation

```bash
git clone https://github.com/DH1NOC/BrandmeisterTools.git
cd BrandmeisterTools

# Virtuelle Umgebung anlegen
python3 -m venv .venv            # Windows: py -m venv .venv

# Virtuelle Umgebung aktivieren
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell
.venv\Scripts\activate.bat       # Windows cmd

# Paket samt Abhängigkeiten installieren (editierbar)
pip install -e .
```

Die Aktivierung gilt pro Terminal-Sitzung; nach dem Öffnen eines neuen
Terminals im Projektordner erneut aktivieren.

### Starten

Der einfachste Weg ist der interaktive Modus — ohne Argumente starten, alle
Eingaben werden abgefragt (Auswahllisten mit ↑/↓ navigieren, Enter bestätigt):

```bash
bmtools            # Menü aller Tools
bm-bahn            # direkt: Relais entlang einer Bahnstrecke
```

Für Skripte und Wiederholläufe gibt es Flags — alle Parameter sind unter
[Die Tools im Detail](#die-tools-im-detail) dokumentiert:

```bash
bm-bahn --von "Koblenz Hbf" --nach "Nürnberg Hbf" --oeffnen
bm-auto "https://maps.app.goo.gl/…"
bm-rad  --gpx tour.gpx
```

Ergebnis pro Lauf in `out/<start>-<ziel>/`:

| Datei | Inhalt |
|---|---|
| `bericht.html` | Bericht mit fertigen Kanaltabellen je Relais (für manuelle CPS-Eingabe) |
| `relais.csv` | Alle Daten maschinenlesbar (Semikolon-getrennt) |
| `karte.html` | Interaktive Karte: Strecke + erreichbare Relais |
| `anytone/*.CSV` | Channel/TalkGroups/Zone für den AnyTone-CPS-Import |

Der AnyTone-Export nutzt derzeit das D878UV-Spaltenlayout (siehe
[`PROJEKTPLAN.md`](PROJEKTPLAN.md), M5).

Alle API-Antworten und Höhenkacheln landen in einem lokalen Disk-Cache;
Wiederholläufe brauchen dadurch nur Sekunden. `--aktualisieren` erzwingt
frische Brandmeister-Daten.

### Tests ausführen (Entwicklung)

```bash
pip install -e ".[dev]"
pytest
```

## Die Tools im Detail

Alle Tools folgen demselben Muster: **Ohne Argumente startet ein
interaktiver Assistent**, der alle Angaben abfragt — mit Argumenten laufen
sie nicht-interaktiv durch (skriptfähig). Jedes Tool zeigt mit `--help`
seine vollständige Optionsliste samt Beispielen. Für jedes deutsche Flag
existiert das englische Original als Alias (`--von` = `--from`,
`--zeit` = `--time`, …).

### `bmtools` — gemeinsamer Einstieg

```bash
bmtools                  # Menü aller Tools (Pfeiltasten + Enter)
bmtools bahn [OPTIONEN]  # Tool direkt starten, Optionen werden durchgereicht
bmtools auto [OPTIONEN]
bmtools rad  [OPTIONEN]
```

`bmtools bahn --von Koblenz --nach Nürnberg` ist identisch zu
`bm-bahn --von Koblenz --nach Nürnberg`. Die englischen Subcommand-Namen
`rail`, `car`, `bike` funktionieren ebenfalls.

### `bm-bahn` — Relais entlang einer Bahnstrecke

Sucht über [Transitous](https://transitous.org) eine reale Zugverbindung
zwischen Start- und Zielbahnhof und wertet deren Streckengeometrie aus.
Die Zuggattung beeinflusst die Route real: Hamburg–München fährt der
Fernverkehr z. B. via Erfurt oder via Würzburg, der Nahverkehr eine ganz
andere Kette — entsprechend ändern sich die gefundenen Relais.

**Streckenwahl** — entweder `--von`/`--nach` oder `--bahnhoefe`:

| Parameter | Bedeutung |
|---|---|
| `--von BAHNHOF --nach BAHNHOF` | Start- und Zielbahnhof, z. B. `"Koblenz Hbf"` |
| `--via BAHNHOF` | Zwischenhalt zu `--von`/`--nach`; mehrfach angebbar (`--via Mainz --via Würzburg`) |
| `--bahnhoefe "A, B, C"` | Alternativ: kommagetrennte Bahnhofsliste statt `--von`/`--nach` |

**Verbindungsauswahl:**

| Parameter | Bedeutung |
|---|---|
| `--zuggattung {alle,fern,nah}` | `fern` = ICE/IC/EC und Nachtzüge, `nah` = RE/RB/S-Bahn (Default: `alle`) |
| `--zeit ZEIT` | Abfahrtszeit; Formate `"2026-07-14 08:00"`, `"14.07.2026 08:00"` oder `"08:00"` (= heute). Default: jetzt |
| `--ankunft` | `--zeit` als Ankunfts- statt Abfahrtszeit interpretieren |
| `--direkt` | Nur Direktverbindungen (ohne Umstieg) |
| `--luftlinie` | Keine Verbindungssuche; Luftlinie zwischen den Bahnhöfen auswerten |

Interaktiv wird bei mehrdeutigen Bahnhofsnamen immer nachgefragt
(„Koblenz" ist z. B. auch exakt der Name eines Schweizer Bahnhofs) und
unter mehreren gefundenen Verbindungen ausgewählt. Nicht-interaktiv nimmt
das Tool jeweils den ersten Treffer bzw. die erste passende Verbindung.

```bash
bm-bahn --von "Koblenz Hbf" --nach "Nürnberg Hbf" --oeffnen
bm-bahn --von Hamburg --nach München --zuggattung fern --direkt
bm-bahn --von Koblenz --nach Nürnberg --zeit "2026-07-14 17:30" --ankunft
bm-bahn --bahnhoefe "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --luftlinie
```

### `bm-auto` / `bm-rad` — Relais entlang einer Auto- oder Radroute

Gleiche Auswertung und gleiche Ausgaben wie `bm-bahn`, aber für Straße und
Rad. Die Route kommt aus genau einer der drei Quellen — Link, GPX-Datei
oder Start/Ziel:

| Parameter | Bedeutung |
|---|---|
| `LINK` (Positionsargument) | Google-Maps-Routenlink (auch Kurzlink vom Teilen-Button) oder Komoot-Tour-Link |
| `--gpx DATEI` | GPX-Datei, z. B. ein Komoot-Export — funktioniert immer |
| `--von ORT --nach ORT` | Start/Ziel als Ort oder Adresse (hausnummerngenau, Geocoding via Transitous) |
| `--via ORT` | Zwischenpunkt zu `--von`/`--nach`; mehrfach angebbar |

Was bei den Link-Quellen zu wissen ist:

- **Ein Google-Maps-Link enthält keine Routen-Geometrie**, nur die
  Wegpunkte. Das Tool routet daher selbst (OSRM auf
  OpenStreetMap-Daten) — der Verlauf kann von Googles Vorschlag leicht
  abweichen. Per Maus verschobene Routenpunkte stehen als Via-Punkte im
  Link und werden übernommen.
- **Ein Komoot-Link ist der bessere Fall:** Er zeigt auf eine gespeicherte
  Tour, deren exakte Geometrie übernommen wird — kein Nachrouten. Private
  Touren brauchen den „Mit Link teilen"-Link (enthält den nötigen
  `share_token`); klappt der Abruf nicht, ist der GPX-Export der Tour der
  garantierte Weg (`--gpx`).
- ÖPNV-Links lehnt das Tool ab und verweist auf `bm-bahn`.
- Widerspricht das Verkehrsmittel im Link dem Tool (Rad-Link in
  `bm-auto`), wird interaktiv nachgefragt; in Skripten gewinnt der Link.

```bash
bm-auto "https://maps.app.goo.gl/…"
bm-rad  "https://www.komoot.com/tour/…?share_token=…"
bm-rad  --gpx tour.gpx
bm-auto --von "Winkelhaider Str. 4a, Feucht" --nach "Bendorf" --oeffnen
```

### Gemeinsame Parameter (alle Tools)

| Parameter | Bedeutung |
|---|---|
| `--korridor KM` | Optionales Limit: maximaler Abstand zur Strecke in km. Ohne Angabe zählt allein die rechnerische Erreichbarkeit — auch weit entfernte, aber sichtbare Relais werden aufgenommen |
| `--ohne-gelaende` | Abdeckungsschätzung ohne Geländemodell; spart den Höhenkachel-Download, ist aber ungenauer |
| `--aktualisieren` | Brandmeister-Daten frisch laden statt aus dem Cache (Geräteliste hält sonst 1 Tag, Talkgroup-Profile 12 h) |
| `--oeffnen` | Bericht und Karte nach dem Lauf im Browser öffnen (interaktiv automatisch aktiv) |
| `--ausgabe ORDNER` | Ausgabeverzeichnis (Default: `out/<start>-<ziel>`) |

Frequenzangaben in allen Ausgaben sind aus Sicht des Funkgeräts
(RX = Relais-Ausgabe). TG9 „Lokal" wird immer ergänzt, auch wenn die API
sie nicht listet.

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

- [Brandmeister-API v2](https://api.brandmeister.network/v2/) — Relaisliste,
  Frequenzen, Talkgroup-Profile
- [Transitous](https://transitous.org) — Bahnverbindungen inklusive
  Streckengeometrie
- [OSRM auf FOSSGIS-Servern](https://routing.openstreetmap.de) — Auto- und
  Radrouting auf OpenStreetMap-Daten
- [Komoot-API](https://www.komoot.com) — exakte Geometrie gespeicherter Touren
- [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) —
  Höhendaten (Terrarium-Format) für das Sichtlinien-Modell

## Projektstruktur

```text
BrandmeisterTools/
├── bmtools/              # Python-Paket mit allen Tools
│   ├── bm_api/           # Brandmeister-API-Client (HTTP, Disk-Cache, Datenmodelle)
│   ├── routelib/         # Gemeinsamer Kern: Geländemodell/Erreichbarkeit,
│   │                     #   Bericht, Karte, CSV, Codeplug-Export, Pipeline
│   ├── rail/             # bm-bahn (Bahnverbindungen via Transitous)
│   ├── road/             # bm-auto / bm-rad (Maps-/Komoot-Link, GPX, OSRM, Geocoding)
│   ├── cli.py            # bmtools-Einstieg: Menü und Subcommand-Dispatcher
│   └── ui.py             # Gemeinsames CLI-Erscheinungsbild (Banner, Farben)
├── tests/                # pytest-Suite (Link-Parser, GPX, Komoot, Routing)
├── out/                  # Generierte Berichte/Karten/CSV je Route (nicht versioniert)
├── pyproject.toml        # Paketdefinition, Abhängigkeiten, Entry Points
├── PROJEKTPLAN.md        # Offene Punkte, Festlegungen, API-Eigenheiten
└── README.md
```

- **`bmtools/bm_api/`** — wiederverwendbarer, gecachter Client für die
  Brandmeister-API; unabhängig von den Routen-Tools nutzbar.
- **`bmtools/routelib/`** — die gesamte Auswertung von der Routen-Geometrie
  bis zu den Ausgabedateien; die Tools in `rail/` und `road/` liefern nur die
  Route an diese Pipeline.
