# BM-Routencheck — Entwickler-README

Technische Dokumentation für alle, die am Code arbeiten. Die Bedienung und
die fertigen Downloads beschreibt die [README](README.md); offene Punkte,
verbindliche Festlegungen und die Eigenheiten der externen Datenquellen
stehen in [`PROJEKTPLAN.md`](PROJEKTPLAN.md).

## Inhalt

- [Entwicklungsumgebung](#entwicklungsumgebung)
- [Qualitätssicherung](#qualitätssicherung)
- [Projektstruktur](#projektstruktur)
- [Grafische Oberfläche (pywebview)](#grafische-oberfläche-pywebview)
- [Technische Highlights & Externe Technologien](#technische-highlights--externe-technologien)
- [Ausgabeort und Öffnen im System](#ausgabeort-und-öffnen-im-system)
- [Disk-Cache](#disk-cache)
- [Selbst-Updater](#selbst-updater)
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
  Annotationszwang) sind als Overrides dokumentiert. **`mypy` ohne
  Argument aufrufen**, nicht `mypy bmtools`: `pyproject.toml` setzt
  `packages = ["bmtools", "tests"]`, die Tests werden also mitgeprüft.
  Ein `mypy bmtools` vor dem Commit sieht grün aus und lässt die CI
  trotzdem auflaufen (Befund 2026-07-26: abgebrochener Release-Lauf).
- **pytest + coverage** — getestet wird die Kernlogik (Parser, Geometrie,
  Abdeckungsschätzung, Berichte inkl. PDF, Codeplug, API-Clients mit
  gemockten HTTP-Antworten) sowie die GUI-Logik (Bridge-Validierung,
  GuiMelder-Ereignisse, Ergebnisdaten). Interaktive CLIs, Karten- und
  Webview-Rendering sind bewusst ausgenommen; die Untergrenze
  (`fail_under`) sichert das erreichte Niveau ab, ohne
  Statistik-Kosmetik zu belohnen.

## Projektstruktur

```text
bm-routencheck/
├── bmtools/              # Python-Paket mit allen Tools
│   ├── bm_api/           # Brandmeister-API-Client (HTTP, Disk-Cache, Datenmodelle)
│   ├── fm_api/           # DL3EL-Client für analoge FM-Relais (Umkreissuche,
│   │                     #   defensiver CSV/GPX-Parser, Disk-Cache)
│   ├── routelib/         # Gemeinsamer Kern: Geländemodell/Erreichbarkeit,
│   │                     #   Bericht, Karte, Kartenbild, PDF, CSV,
│   │                     #   Codeplug-Export, Pipeline
│   ├── rail/             # bm-bahn (Bahnverbindungen via Transitous)
│   ├── road/             # bm-auto / bm-rad (Maps-/Komoot-Link, GPX, OSRM, Geocoding)
│   ├── gui/              # Programmfenster (pywebview): Bridge, GuiMelder,
│   │                     #   Hintergrund-Lauf, static/-Frontend mit Leaflet
│   ├── update/           # Selbst-Updater: signiertes Manifest prüfen,
│   │                     #   Artefakt laden, Programm ersetzen (UI-frei)
│   ├── cli.py            # bmtools-Einstieg: Menü, Subcommand-Dispatcher, Cache-Befehl
│   ├── version.py        # Eigene Programmversion — Grundlage jeder Update-Entscheidung
│   ├── ausgabe.py        # Wohin die Ergebnisse gehen — EINE Entscheidungsstelle
│   ├── cache_admin.py    # Cache-Bereiche auflisten/leeren (UI-frei)
│   └── ui.py             # Gemeinsames CLI-Erscheinungsbild (Banner, Farben,
│                         #   Fortschrittsbalken mit ETA ab 10 s Restzeit)
├── tests/                # pytest-Suite (Parser, Geometrie, Berichte, Clients)
├── packaging/            # PyInstaller-Einstieg, macOS-Entitlements,
│                         #   Material-Symbols-Sprite-Generator,
│                         #   schluessel_erzeugen.py + manifest_signieren.py
├── out/                  # Ergebnisse von TERMINAL-Läufen (nicht versioniert);
│                         #   das Fenster schreibt nach Dokumente/, s. ausgabe.py
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

## Grafische Oberfläche (pywebview)

`bmtools/gui/` enthält das Programmfenster: ein Single-Window Workspace
(Control Panel links, Karte + DataGrid rechts) als pywebview-Fenster über
einem Vanilla-HTML/JS/CSS-Frontend — kein Framework, kein CDN. Konzept,
Nutzerfestlegungen und Abnahmeprotokolle sind in der Git-Historie von
`GUI-UMBAU.md` nachlesbar (Plan mit dem Abschluss aufgelöst). Die
Pipeline bleibt die eine Quelle der Wahrheit; der Terminal-Modus ist
vollwertig und unverändert.

**Start** (`gui/__init__.py`): `desktop_verfuegbar()` erkennt grob, ob
ein Fenster möglich ist (SSH zählt als Terminal; Linux braucht
`DISPLAY`/`WAYLAND_DISPLAY`). Alle vier Kommandos rufen
`start_oder_none()` — ohne Routen-Argumente öffnet sich auf dem Desktop
das Fenster, `--gui`/`--terminal` erzwingen das jeweilige Verhalten.
Scheitert der Start (z. B. Linux ohne GTK/WebKit2 bzw. QtWebEngine),
fällt das Tool mit Hinweis ins Terminal zurück; pywebview wird erst beim
tatsächlichen Fensterstart importiert (`fenster.py`).

**Bridge-Datenfluss** (`gui/bridge.py`): Die `Bridge` ist die pywebview
`js_api` — das Frontend ruft ihre Methoden direkt auf
(Feld-/Formularvalidierung über dieselben Parser wie der
Terminal-Assistent, `start_lauf`, `abbrechen`, Dialog-`antwort`,
`export_csv`/`export_pdf`, Cache-Info/-Leeren, `setze_einstellung`).
In Gegenrichtung schickt die Bridge Ereignisse threadsicher per
`evaluate_js` ans Frontend. Ein Lauf (`gui/lauf.py`) läuft im
Hintergrund-Thread und nutzt dieselben Routenaufbau-Funktionen wie die
CLIs; Abbrechen wirkt sofort (das Ende wird direkt aus dem Bridge-Thread
gemeldet, der Arbeiter stirbt an seinem nächsten Kontrollpunkt).
GUI-Einstellungen (Theme, Splitter-Position) liegen als `gui.json` im
platformdirs-Konfigurationsordner (`gui/einstellungen.py`) —
localStorage ist in WKWebView für file:// nicht neustartfest.

**GuiMelder** (`gui/melder.py`): implementiert das `Melder`-Protocol aus
`routelib/melden.py` — dieselben Hooks, an die im Terminal der
`TerminalMelder` die rich-Ausgaben hängt: Texte, Fortschrittsbalken mit
ETA, Grob-Phasen (`schritt`), interaktive Rückfragen (werden zu Dialogen,
der Pipeline-Thread wartet auf die Antwort) und `ergebnis_daten` — das
strukturierte Ergebnis-Payload `{karte, kennzahlen, relais}` aus
`mapview.karten_daten()` und `report.relais_daten()`. Dieses eine
Payload speist die Leaflet-Ansicht, das DataGrid, die Kennzahlen-Top-Bar
und das PDF-Kartenbild — Folium-Karte, Bericht und CSV entstehen
unverändert aus denselben Ergebnisobjekten. Eine Ereignis-Drossel hält
die Event-Rate webview-verträglich.

**Frontend-Bündelung** (`gui/static/`): Leaflet 1.9.4 liegt lokal unter
`static/vendor/leaflet/` (BSD-Lizenz beigelegt), die Material Symbols
als Teilmenge unter `static/vendor/material-symbols/` (Apache-2.0;
Sprite erzeugt `packaging/sprite_erzeugen.py`). Einzige externe Zugriffe
des Fensters sind die Kartenkacheln (OSM/FOSSGIS, Carto als
Ausweich-Ebene).

**Kartenbild & PDF** (`routelib/mapimage.py`, `routelib/report_pdf.py`):
`mapimage.py` komponiert per Pillow ein statisches Kartenbild aus dem
`karten_daten`-Payload — OSM-Kachel-Mosaik (eigener User-Agent, Zoom
max. 13, Disk-Cache `osm-kacheln`), Abdeckungs-Overlay, Statussegmente,
Marker, Maßstabsleiste, Attribution. `report_pdf.py` (reportlab) baut
daraus `bericht.pdf` (DIN A4): Deckblatt mit Kennzahlen und
Übersichtskarte, Relais-Tabelle mit wiederholtem Kopf und
Talkgroup-Details, Fußzeile mit Seitenzahl und Datenstand — Statusfarben
und Begriffe identisch zu GUI und Bericht. Auslöser sind ausschließlich
das `--pdf`-Flag bzw. der PDF-Export-Knopf (kein Automatik-Export).

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
  Geländemodell: Höhenraster dekodieren und Sichtlinien berechnen;
  Pillow rendert zudem das Kartenbild für das PDF
- [pywebview](https://pywebview.flowrl.com/) — natives Fenster um das
  HTML/JS-Frontend der GUI (WKWebView/WebView2/GTK-WebKit) mit
  [Leaflet](https://leafletjs.com/) (lokal gebündelt) für die Karte
- [reportlab](https://www.reportlab.com/opensource/) — PDF-Erzeugung
  (`bericht.pdf`)
- [platformdirs](https://platformdirs.readthedocs.io/) — plattformgerechter
  Ablageort für Disk-Cache und GUI-Einstellungen

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

### Einzelrelais-Sichtfelder

`render_relay()` liefert jedes Sichtfeld auf seine belegte Pixel-Bbox
zugeschnitten zurück (das volle Raster wären bei `HEATMAP_MAX_PX` 3,2 MB
je Relais durch die Prozesspool-Pipe). `_coverage_raster()` addiert die
Zuschnitte in die Summenkarte **und** legt jeden einzeln als eigenes
PNG-Overlay ab — indexgleich mit `results` und damit mit den Markern.
Der Aufwand ist reine Kodierung, gerechnet wurde ohnehin je Relais.

Drei Stellen, an denen es leicht subtil falsch wird:

- **Zuschnitt erst nach `MaxFilter(3)`.** Der Filter weitet die
  gezeichneten Sichtläufe um ein Pixel; vorher zugeschnitten fehlte der
  Rand.
- **Bounds kantenbasiert** (`/w`, `/h` — nicht `/(w-1)`). Leaflet zieht
  die *Bildkanten* auf die Bounds, nicht die Pixelmitten. Nur so deckt
  ein Zuschnitt exakt dieselbe Fläche ab wie die zugehörigen Pixel der
  Summenkarte, sonst springen die Ansichten beim Umschalten
  gegeneinander.
- **Abstände per Haversine über die inverse Mercator-Zeile**, nicht über
  einen festen km/Pixel-Faktor: die Rasterzeilen liegen in Mercator-Y,
  auf einem Raster über die ganze Republik unterscheiden sich Nord- und
  Südrand deutlich in km/Pixel.

Abgesichert ist das durch `test_einzelfelder_ergeben_zusammen_die_summenkarte`:
die Einzelfelder werden über ihre Geo-Bounds zurück ins globale Raster
einsortiert und müssen die Summenkarte reproduzieren — prüft Zuschnitt,
Bounds-Rückrechnung und Rampenstufen in einem Zug. Bewusst nur binär
(Sicht / Grenzbereich / nichts), weil ein Pixel genau auf einer
Abstandsgrenze beim Rückrechnen in die Nachbarstufe kippen darf.

Die Abstufung ist **Abstand, nicht Feldstärke** (`FELD_STUFEN_KM`) — ERP
und Antennendiagramm sind unbekannt. Die Legende sagt das ausdrücklich;
Wortlaut und Farben stehen einmal in `_feld_legende()`, GUI-Karte und
`karte.html` lesen beide von dort.

**Escape ist gestaffelt.** Der Marker-Klick öffnet zugleich das Popup —
also genau auf dem üblichen Weg in die Einzelansicht. Ein einzelnes
`Esc` schließt deshalb erst das Popup, erst das nächste kehrt zur
Summenkarte zurück; ohne Staffelung verschwände beides auf einmal. Zwei
Feinheiten, die dabei zählen: das Popup wird **selbst** geschlossen
(Leaflets eigener `Esc`-Handler hängt am Kartencontainer und greift nur
mit dessen Fokus — bloßes Aussteigen könnte `Esc` dauerhaft wirkungslos
machen), und der Popup-Zustand kommt aus `popupopen`/`popupclose`, nicht
aus dem DOM: `.leaflet-popup` bleibt nach dem Schließen noch rund 400 ms
zum Ausblenden stehen.

**Fallstrick bei `karte.html`:** folium erzeugt sein eigenes JavaScript
erst beim Rendern und hängt es *hinter* die vorher manuell an
`get_root().script` angefügten Kinder. Das Einzelfeld-Skript steht im
fertigen Dokument also **vor** den Variablen, die es benutzt (gemessen:
Skript bei Zeichen 4196, Marker-Definitionen ab 91012). Es hängt deshalb
an `DOMContentLoaded` — sofort ausgeführt fände es `map`, `ImageOverlay`
und alle Marker als `undefined` vor. `test_karte_html_verdrahtet_die_einzelfelder`
prüft beides: dass jede referenzierte JS-Variable auch definiert ist,
und dass verzögert wird.

## Ausgabeort und Öffnen im System

Zwei Fehler beim Linux-Beta-Test am 2026-07-26 (Mint 22.3) hatten
dieselbe Wurzel: Pfade, die vom Arbeitsverzeichnis abhingen.

**Ausgabeort** (`bmtools/ausgabe.py`). `out_dir = Path("out") / …` ist
relativ zum CWD — und beim Doppelklick bestimmt den der Starter. Beim
Tester war es `$HOME`, die Ergebnisse lagen in `~/out/…`, gesucht wurden
sie im selbst angelegten Programmordner. Der Wächter in
`packaging/entry.py` griff nicht: Er wich nur aus, wenn das CWD *nicht
beschreibbar* war, und ein Home-Verzeichnis ist beschreibbar. Seitdem
holt der Fenster-Start seinen Ordner aus `fenster_ausgabeordner()`
(`Dokumente/bm-routencheck-ergebnisse`), der Terminal-Start bleibt bei
`./out`. `run_pipeline` macht `out_dir` außerdem sofort absolut — der
gemeldete Pfad ist damit der, den der Nutzer suchen kann, und der
Ausgabeordner geht absolut an den Dateimanager.

**Die Entscheidung fällt an genau einer Stelle**, und das ist teuer
erkauft: Der erste Anlauf setzte den festen Ordner je `out_dir`-Stelle
einzeln und übersah dabei den Bahn-Modus. Der baut sein `out_dir`
nämlich nicht in der GUI, sondern erst tief in `rail/cli._pipeline` —
`gui/lauf._bahn` reicht nur an `rail_cli._run`/`_run_link` weiter. Nur
Auto und Rad (`_strasse`) waren repariert, Bahn schrieb weiter relativ
(Befund 2026-07-26, Windows: Ausgabe im `out/` neben der Exe im
Download-Ordner).

Seitdem gilt: `_namespace()` in `gui/lauf.py` legt den festen Ordner in
`args.ausgabe_basis` — **einmal**, und beide Wege bekommen denselben
Namespace. Alle `out_dir`-Stellen fragen `ausgabe_basis(args)`
(`bmtools/ausgabe.py`), das per `getattr` auf `./out` zurückfällt, wenn
das Feld fehlt. `test_nur_ausgabe_py_kennt_den_out_ordner` hält fest,
dass `Path("out")` nirgendwo sonst im Paket steht;
`test_bahn_im_fenster_schreibt_in_den_festen_ordner` fährt den
Bahn-Weg komplett durch bis `run_pipeline`. Ein reiner Quelltext-Test
hätte den Fehler nicht gefunden — `gui/lauf.py` sah ja richtig aus.

**Öffnen** (`routelib/oeffnen.py`). Der Ordner-Knopf tat unter Linux gar
nichts, und zwar völlig lautlos: `check=False`, stderr nach
`/dev/null`, und der `webbrowser`-Ausweg hing an `except OSError`, das
nur ein *fehlendes* `xdg-open` fängt — bei einem Exit-Code ≠ 0, also im
tatsächlichen Fall, lief er nie an. (Für ein Verzeichnis wäre er
ohnehin falsch: das gibt eine Browser-Dateiliste, keinen
Dateimanager.) Drei Änderungen, jede auch für sich begründet:

1. **Absoluter Pfad.** Ein relativer wird vom Zielprogramm gegen dessen
   eigenes CWD aufgelöst. Auf Cinnamon läuft Nemo schon (es zeichnet den
   Desktop), der neue Aufruf reicht das Argument per DBus an die
   laufende Instanz weiter — und die sitzt woanders.
2. **Ausweichkette** `xdg-open` → `gio open` → `nemo`/`nautilus`/
   `dolphin`/`thunar`/`pcmanfm`, mit Prüfung des Exit-Codes. Nicht
   installierte Öffner werden per `shutil.which` übersprungen.
3. **Umgebung säubern** (`kind_umgebung()`). Das Linux-Binary ist
   `--onefile` mit gebündeltem Qt; PyInstaller zeigt `LD_LIBRARY_PATH`
   dann auf sein Entpackverzeichnis und sichert das Original in
   `LD_LIBRARY_PATH_ORIG`. Ein von uns gestarteter Dateimanager erbt das
   und zieht unsere gebündelten Qt-/glib-Bibliotheken statt der
   System-Version — er stirbt lautlos. Der Originalwert gehört also
   zurück ins Kind.

Scheitert alles, gibt es einen `OeffnenFehler` mit allen versuchten
Kommandos samt Code. Die Oberfläche zeigt ihn in der Statusleiste und
legt den absoluten Pfad in die Zwischenablage. Das ist die eigentliche
Lehre aus dem Befund: Ein Knopf, der lautlos nichts tut, lässt sich aus
der Ferne nicht diagnostizieren — der Betreuer konnte den Fehler auf
seinem eigenen Mint nicht nachstellen.

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
| OSM-Kartenkacheln (Kartenbild/PDF) | `bmtools/osm-kacheln` | unbegrenzt |

`bmtools/cache_admin.py` listet und leert diese Bereiche (Menüpunkt
»Cache leeren« bzw. `bmtools cache --leeren`); es bildet die Pfade mit
denselben `user_cache_dir`-Aufrufen wie die Clients, damit sie auf jeder
Plattform übereinstimmen.

## Selbst-Updater

`bmtools/update/` ersetzt das ausgelieferte Programm durch eine neuere
Fassung. Die Anforderung des Nutzers war ausdrücklich, **MITM
auszuschließen** — HTTPS allein leistet das nicht, wer eine eigene
Root-CA im System hat (Firmen-Proxy, untergeschobenes Zertifikat), sieht
und ändert alles. Belastbar ist nur eine Signatur.

### Signiert wird ein Manifest, nicht das einzelne Artefakt

`manifest.json` nennt Version und je Plattform Dateiname + SHA256,
daneben liegt `manifest.json.sig` (Ed25519). **Warum nicht die Artefakte
selbst signieren?** Dann bliebe *Replay* offen: Wer die API-Antwort
fälschen kann, liefert eine ältere, echt signierte Version aus — die
Signatur wäre gültig, die Version käme aber aus der gefälschten JSON.
Nur wenn die Version selbst aus dem signierten Manifest stammt, greift
die Downgrade-Sperre.

Die Reihenfolge ist der eigentliche Schutz und darf nicht umgestellt
werden:

1. GitHub-API abfragen — **nur ein Hinweis, wo ein Manifest liegen könnte**
2. Manifest + Signatur laden, gegen die **einkompilierten** Schlüssel prüfen
3. ab hier zählt **ausschließlich** der Manifest-Inhalt
4. Version aus dem Manifest gegen die laufende, `≤` ablehnen
5. Artefakt laden, SHA256 gegen das Manifest — erst dann auspacken
6. erst dann tauschen

Punkt 3 gilt auch für die **Kanalfrage**: Ob ein Angebot eine Beta ist,
beantwortet `ist_vorabversion()` aus der Versionsnummer im Manifest, nicht
aus dem `prerelease`-Flag der GitHub-Antwort. Die ist unbeglaubigt — wer
sie fälschen kann, schöbe einem Nutzer mit abgeschaltetem Beta-Kanal
sonst eine echte, signierte Vorabversion unter. Kein Downgrade, aber die
Kanalwahl gehört dem Nutzer, nicht dem Netzweg
(`test_beta_erkennung_kommt_aus_dem_manifest`).

### Module

| Modul | Aufgabe |
|---|---|
| `schluessel.py` | Die beiden öffentlichen Ed25519-Schlüssel (HAUPT, RESERVE) — absichtlich im Klartext, sie prüfen nur |
| `manifest.py` | Aufbau, Serialisierung und Prüfung des Manifests; `pruefe_manifest()` ist die Grenze zwischen unbeglaubigt und beglaubigt |
| `pruefen.py` | Release-Abfrage, Versionsvergleich (PEP 440), Artefaktauswahl, Beta-Filter — rein und ohne Seiteneffekte |
| `ziel.py` | Plattformkennung, das zu ersetzende Programm, Schreibrechtsprüfung |
| `laden.py` | Herunterladen, SHA256, Auspacken (mit Zip-Slip-Schutz) |
| `tausch.py` | Das Ersetzen je Plattform — die Naht, an der die Tests ansetzen |
| `ablauf.py` | Verbindet alles zu dem, was GUI und Terminal aufrufen |
| `terminal.py` | Hintergrundprüfung + `bmtools --update` |
| `changelog.py` | Release-Notes für den »Was ist neu«-Dialog nach einem Update — reine Anzeige-Daten, bewusst OHNE Signaturprüfung (die GUI rendert sie nur als escapten Text; Marker `changelog_stand` in gui.json, ein Versuch pro Update) |

**Zwei Schlüsselplätze von Anfang an.** Ein ausgeliefertes Binary
akzeptiert nur Schlüssel, die es kennt — ohne zweiten Platz wäre bei
Verlust oder Kompromittierung des Hauptschlüssels *jeder* Client
dauerhaft von Updates abgeschnitten. Nachrüsten geht nicht, deshalb war
das vor dem ersten Release zu entscheiden. RESERVE wird im Normalbetrieb
nie benutzt; sein privates Gegenstück liegt **nur offline**, nie bei
GitHub. Neue Paare erzeugt `packaging/schluessel_erzeugen.py`.

**Bewusst akzeptiertes Restrisiko:** Wer Schreibrechte auf das Repo hat,
kann gültig signieren. Gegen MITM schützt das Verfahren vollständig,
gegen ein übernommenes GitHub-Konto nicht (Nutzerentscheidung
2026-07-27; die Alternative wäre lokales Signieren als manueller Schritt
je Release). **Kein Zertifikats-Pinning** — GitHub rotiert seine CAs, das
wäre nur eine zusätzliche Bruchstelle.

**Zweites akzeptiertes Restrisiko: kein Widerruf, kein Ablaufdatum.**
Ein signiertes Manifest bleibt für immer gültig. Wer die
Release-Antworten kontrolliert, kann Clients eine ältere, echt
signierte Version dauerhaft als „neueste" vorsetzen, solange sie neuer
als die installierte ist — und so das Ausrollen eines Sicherheitsfixes
verzögern (Freeze-Angriff). Ein Downgrade bleibt ausgeschlossen.
Frische ließe sich nur mit Ablaufdaten im Manifest und regelmäßigem
Neusignieren erzwingen (TUF-Territorium) — für die Größe dieses
Projekts bewusst nicht gebaut. Der Rettungsweg bei Kompromittierung des
Hauptschlüssels ist der RESERVE-Schlüssel: Ein mit ihm signiertes
Release wird von allen Clients angenommen und kompiliert neue
Schlüssel ein.

### Fallstricke, die im Quellbaum unsichtbar sind

- **Version im gefrorenen Binary.** `bmtools/version.py` liest im
  Checkout `pyproject.toml` und erst sonst die Paket-Metadaten:
  `importlib.metadata` liefert im venv die Version des letzten
  `pip install` — hier 0.1.2, während pyproject auf 0.3.0 stand. Im
  PyInstaller-Binary sind die Metadaten überhaupt nur da, wenn
  `--copy-metadata bm-routencheck` sie mitnimmt; ohne sie meldet
  `eigene_version()` `0+unbekannt`, und `version_bekannt()` sorgt dafür,
  dass der Updater dann **schweigt** statt auf einer erfundenen Version zu
  entscheiden. Weil das im Quellbaum grün aussieht und nur im Artefakt
  kaputt ist (dieselbe Fehlerklasse wie `mypy bmtools` statt `mypy`),
  prüft der Rauchtest in `release.yml` auf allen drei Plattformen
  `--version` gegen die tatsächlich gebaute Version.
- **Zwei Schreibweisen derselben Version.** Intern und beim Vergleichen
  gilt die normalisierte PEP-440-Form `0.4.0b1` — so steht sie in den
  Paket-Metadaten und im Manifest. Angezeigt wird über
  `version_anzeige()` aber `0.4.0-beta.1`, also die Form aus Tag,
  Releases-Seite und Dateinamen: Wer beides nebeneinander sieht, hält es
  sonst für zwei Stände und meldet einen Fehler, der keiner ist
  (Nutzerentscheidung 2026-07-27). Die Umschrift ist exakt die Umkehrung
  der Rechnung in `release.yml` (`VERSION="${VERSION}b$N"`), und der
  Rauchtest dort vergleicht deshalb gegen `label`, nicht gegen
  `version`. `test_anzeige_ist_die_umkehrung_der_workflow_rechnung`
  hält beide Seiten zusammen. **Nie zum Vergleichen benutzen** —
  `ist_neuer()` und `ist_vorabversion()` arbeiten weiter auf der
  PEP-440-Form.
- **Der Arbeitsordner liegt neben dem Ziel**, nicht im System-Temp:
  `os.replace()` kann keine Dateisystemgrenzen überschreiten (`EXDEV`),
  und `/tmp` ist oft tmpfs.
- **Die alte Fassung wird nur zur Seite geschoben** (`<name>.vorher`).
  Dass `beim_start_aufraeumen()` in `packaging/entry.py` überhaupt läuft,
  *ist* der Beweis für den gelungenen Start — eine eigene
  Fehlstart-Erkennung wäre nur eine weitere Fehlerquelle.
- **Linux/macOS** tauschen mit `os.replace()`: Der Prozess hält das alte
  Inode, der Name zeigt danach auf die neue Datei. Auf macOS ist das Ziel
  das `.app`-Bundle (nicht das Binary darin), und davor läuft
  `codesign --verify --deep --strict` — ein selbst geladenes Archiv trägt
  kein Quarantäne-Attribut, Gatekeeper prüft also nicht für uns mit.
  Dazu der **Team-Anker** (Härtung 2026-07-27): `--verify` allein nimmt
  jede intakte Signatur an, auch ad-hoc — das neue Bundle muss vom
  selben Apple-Team stammen wie das laufende (`_team_id()`; Referenz ist
  das laufende Bundle, kein einkompiliertes Team).
- **zipfile zerstört Symlinks.** `extractall` macht aus einem Symlink
  eine reguläre Datei mit dem Linkziel als Inhalt — das `.app`-Bundle
  enthält Symlinks, codesign hätte danach jedes Update abgelehnt.
  `_zip_auspacken()` in `laden.py` packt deshalb selbst aus: Symlinks
  bleiben Symlinks, Linkziele werden gegen Ausbruch geprüft, Dateirechte
  bleiben erhalten. Und: ditto legt neben das Bundle AppleDouble-DATEIEN
  wie `._BM-Routencheck.app` — die Bundle-Suche nimmt nur echte Ordner
  (Befunde des ditto-Probelaufs 2026-07-27).
- **macOS-Neustart über einen sh-Helfer.** `open` auf das eigene Bundle
  startet NICHTS, solange die alte Instanz lebt: LaunchServices sieht
  die Bundle-ID als laufend und aktiviert sie nur. Zusammen mit einem
  `destroy()` mitten im eigenen Bridge-Aufruf fror das Fenster bei
  »Neustart …« ein (Beta-Befund 2026-07-27). Deshalb wartet ein
  abgekoppelter Helfer auf unser Prozessende und ruft `open` erst
  danach; `destroy()` läuft nachgelagert, nie synchron im Bridge-Aufruf.
- **Onefile-Neustart erbt den Bootloader-Zustand.** Der
  PyInstaller-Bootloader hinterlegt `_MEI…`/`_PYI…`-Variablen für seinen
  eigenen Kindprozess. Erbt die neu gestartete Fassung sie, hängt ihr
  Bootloader am Auspack-Ordner des sterbenden Prozesses: Version
  »unbekannt« (Updater bliebe fortan stumm), Absturz beim Start
  („Failed to load Python DLL") oder gar kein Start — alle drei
  Ausgänge beobachtet (Beta-Befunde 2026-07-27, Linux und Windows).
  Deshalb `_saubere_umgebung()` bei jedem Neustart-Weg und auch unter
  Linux das Warten auf das Prozessende. macOS war nie betroffen:
  `open` startet über launchd, ohne unsere Umgebung.
- **Windows:** Die laufende `.exe` ist gesperrt. Eine Batch-Datei wartet
  auf unser Prozessende, tauscht, startet neu und löscht sich selbst —
  daher gibt `ersetze()` dort `False` zurück („Tausch beim Beenden").
  Das Muster „unsigniertes Programm lädt eine Exe und führt sie aus" kann
  Virenscanner-Heuristiken auslösen.
- **Plattformnamen sind ein Vertrag** zwischen `release.yml` und
  `ziel.py`; weichen sie ab, findet der Client sein Artefakt nie.
  `test_plattformnamen_decken_sich_mit_dem_workflow` liest dazu die
  Workflow-Datei.
- **Kein Elevation-Dialog.** Fehlt das Schreibrecht am enthaltenden
  Ordner, scheitert `durchfuehren()` früh — *bevor* 240 MB geladen sind —
  mit dem Verweis auf die Releases-Seite.

## Releases

Releases werden manuell über GitHub Actions gebaut:
**Actions → Release → „Run workflow"**, dort Branch und Versionssprung wählen.

- **Branch bestimmt die Art:** `main` erzeugt einen regulären Release
  (Version wird in `pyproject.toml` committet und getaggt, z. B. `v0.3.0`);
  jeder andere Branch erzeugt eine **Beta** (nur Tag, z. B. `v0.3.0-beta.1`,
  auf GitHub als Pre-Release markiert — die Versionsnummer im Branch bleibt
  unverändert).
- **Versionssprung:** `major` erhöht die Featureversion (`0.2.0 → 0.3.0`),
  `minor` den Patch (`0.2.0 → 0.2.1`). Achtung, die Vokabel weicht von
  Semver ab: `major` meint hier die **mittlere** Stelle. Die erste
  Stelle erhöht `release.yml` nirgends — ein Sprung auf `1.0.0` braucht
  erst eine dritte Sprung-Option im Workflow.
- **Signiertes Update-Manifest (Pflicht, seit 0.4.0):** Der Release-Job
  ruft `packaging/manifest_signieren.py` und legt `manifest.json` +
  `manifest.json.sig` zu den Assets — daraus entscheiden die
  ausgelieferten Clients über Updates (siehe
  [Selbst-Updater](#selbst-updater)). Dafür muss das Repository-Secret
  **`UPDATE_SIGN_KEY`** gesetzt sein (privater HAUPT-Schlüssel,
  base64, aus `packaging/schluessel_erzeugen.py`). **Fehlt es, bricht
  der Workflow mit Fehler ab** — und zwar absichtlich: Ein Release ohne
  Manifest würde den Clients nie angeboten, sie blieben stumm auf der
  alten Version stehen. Ein halb veröffentlichtes Release ist leichter zu
  reparieren als eine Nutzerschaft, die nichts mehr bekommt.
  Der **RESERVE**-Privatschlüssel gehört ausschließlich offline und nie
  zu GitHub. Das Skript prüft seine eigene Signatur anschließend auf dem
  öffentlichen Weg gegen `bmtools/update/schluessel.py` und bricht ab,
  wenn sie nicht angenommen würde — ein falsch hinterlegtes Secret fällt
  so beim Bauen auf und nicht erst beim Nutzer, dessen Update sonst
  stumm ausbliebe.
- **pip-audit (Pflicht, je Plattform):** Vor jedem Build prüft
  `pip-audit` die installierte Umgebung gegen die bekannten
  CVE-Datenbanken — also genau die Pakete, die ins Binary gebündelt auf
  den Rechnern der Nutzer landen (Linux inklusive PyQt6/WebEngine).
  Eine bekannte Lücke bricht den Release ab. In der Push-QS läuft das
  bewusst nicht: Eine frisch gemeldete CVE ohne verfügbaren Fix würde
  sonst jeden Commit blockieren; beim manuellen Release ist der Stopp
  dagegen erwünscht. Lokal nachstellbar mit
  `.venv/bin/pip install pip-audit && .venv/bin/pip-audit --skip-editable`.
- **Rauchtest prüft die Version:** Jeder Build ruft `--version` und
  vergleicht mit der gebauten Version; `--copy-metadata bm-routencheck`
  im PyInstaller-Aufruf ist die Voraussetzung dafür. Schlägt das fehl,
  bricht der Build ab — ein Binary, das seine Version nicht kennt, könnte
  keine Downgrade-Sperre halten.
- **Assets** (GUI-first, Nutzerfestlegung 2026-07-21): Quell-ZIP sowie
  eigenständige PyInstaller-Builds — Windows (x64) als windowed
  `BM-Routencheck.exe` (Exe-Icon; Terminal-Ausgabe über den
  AttachConsole-Shim in `packaging/entry.py`), macOS (Apple Silicon) als
  `BM-Routencheck.app` (onedir-Bundle, Icon aus `icon.icns`) im ZIP mit
  LIESMICH.txt, Linux (x64) als `bmtools` im `.tar.gz` — mit gebündeltem
  Qt/WebEngine-Backend fürs Fenster (deshalb deutlich größer; ohne
  Bundle könnte das PyInstaller-Binary nie eine GUI öffnen, Beta-Befund
  2026-07-21). Kein installiertes Python nötig. Bewusst keine Installer-Pakete
  (.pkg/MSI; allenfalls wäre ein DMG zulässig — Nutzerfestlegung
  2026-07-17).
- **Plattformen:** Windows x64, Linux x64, macOS arm64 (Apple Silicon).
  Für Intel-Macs wird bewusst nichts gebaut — mangels Testgerät wäre das
  ein ungetestetes Asset; die README verweist diese Nutzer auf die
  Installation aus dem Quellcode.
- **Release-Notes:** `release.yml` legt den Release fest verdrahtet mit
  `--generate-notes` an — das ergibt die rohe Commit-Liste („A8-Fix 2",
  „GUI-Fix: …"), für einen Hauptrelease zu wenig. Ein handgeschriebener
  Text wird deshalb **nach** dem Workflow-Lauf drübergelegt:
  `gh release edit v0.3.0 --notes-file notes.md`. Der Aufruf ersetzt den
  ganzen Body, der automatische `**Full Changelog**`-Vergleichslink ist
  danach weg — wenn er bleiben soll, gehört er unten in die Datei.
  Für einen Hauptrelease gehört in die Notes nur, was Endanwender
  betrifft; Entwickler-Innereien stehen hier und im PROJEKTPLAN.
- **`main` ist nach dem Lauf voraus:** Der Workflow committet die neue
  Version selbst („Release 0.3.0") und pusht sie. Wer direkt danach
  lokal weiterarbeitet, braucht erst ein `git fetch` und setzt seinen
  Commit per Rebase darauf — sonst wird der Push abgelehnt.
- **Nachbereitung eines Releases:** Die Betas zur veröffentlichten
  Version aufräumen. **Erst nach dem regulären Release**, nie vorher:
  Die Beta-Nummerierung in `release.yml` zählt die vorhandenen Tags
  hoch, ein zu früh gelöschter Tag lässt die nächste Beta auf eine schon
  vergebene Nummer laufen (Befund 2026-07-17). Dasselbe gilt beim
  Nachschieben einer weiteren Beta: erst bauen, dann die alte löschen.

  ```bash
  gh release delete v0.3.0-beta.2 --yes --cleanup-tag   # Release + Tag
  git push origin --delete feature/…                    # Branch
  ```

  Dazu die **Build-Artefakte** der Beta-Läufe — die überleben das
  Löschen von Release und Tag und liegen je Lauf bei rund 300 MB
  (Linux-Bundle). Über die API je Lauf löschen:

  ```bash
  gh api repos/<owner>/<repo>/actions/artifacts --paginate \
    --jq '.artifacts[] | select(.expired==false and
          .workflow_run.head_branch=="feature/…") | .id' \
  | xargs -I{} gh api -X DELETE repos/<owner>/<repo>/actions/artifacts/{}
  ```
- **Gatekeeper/SmartScreen:** Die Endnutzer-Hinweise zu macOS-Start und
  Windows-Warnungen stehen in der [README](README.md#download--start);
  eine LIESMICH.txt (Doppelklick-Start, Terminal-Pfad ins Bundle) wird
  ins macOS-ZIP gepackt. Nach der Notarisierung wird das Ticket per
  `stapler` ans Bundle geheftet — die Gatekeeper-Prüfung beim Nutzer
  läuft offline und funktioniert direkt ab Veröffentlichung.

### macOS-Signierung und Notarisierung

Das macOS-Bundle wird automatisch signiert und notarisiert, wenn folgende
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

### Update-Signierung

| Secret | Inhalt |
| --- | --- |
| `UPDATE_SIGN_KEY` | Privater **HAUPT**-Ed25519-Schlüssel, base64 (Rohformat, 32 Byte) |

Einmalige Einrichtung — die öffentlichen Gegenstücke stehen bereits in
`bmtools/update/schluessel.py`:

```bash
.venv/bin/python packaging/schluessel_erzeugen.py
```

Das Skript gibt zwei Paare aus und speichert **nichts**. HAUPT/PRIVAT
kommt als `UPDATE_SIGN_KEY` unter Settings → Secrets and variables →
Actions und zusätzlich in den Passwortmanager; RESERVE/PRIVAT nur in den
Passwortmanager. Danach das Konsolenfenster schließen bzw. den
Shell-Verlauf leeren — die privaten Schlüssel standen dort im Klartext.

**Der private Schlüssel ist nicht ersetzbar.** Geht er verloren, kann
kein bereits ausgeliefertes Binary je wieder ein Update annehmen — die
Nutzer müssten von Hand neu herunterladen. Genau dafür existiert der
zweite Schlüsselplatz: Bei Verlust oder Verdacht auf Kompromittierung von
HAUPT wird ab dem nächsten Release mit RESERVE signiert
(`UPDATE_SIGN_KEY` auf den Reserve-Schlüssel umstellen), und im selben
Zug rücken in `schluessel.py` RESERVE nach HAUPT und ein frisch erzeugter
Schlüssel auf den freien Platz. Alte Clients akzeptieren beide, weil
beide seit dem ersten Release einkompiliert sind.

Ein lokaler Probelauf ohne GitHub, wenn am Manifestformat gearbeitet wird:

```bash
UPDATE_SIGN_KEY=<privat-base64> \
  .venv/bin/python packaging/manifest_signieren.py 0.4.0 /tmp/probe \
  "linux-x64=/pfad/zum/bmtools-0.4.0-linux-x64.tar.gz"
```
