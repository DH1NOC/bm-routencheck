# GUI-Umbau — Single-Window Workspace + PDF-Export

Stand: 2026-07-19 · Branch: `feature/gui-umbau`

Dieses Dokument ersetzt den Plan vom 2026-07-18 vollständig. Die erste
Ausbaustufe (Meilensteine G0–G5, siehe Git-Historie) ist abgenommen und
bildet das technische Fundament; ihre Assistenten-Optik (Tabs, Formular-
Wizard, Emojis, Ansichts-Umschalter) wird durch das hier beschriebene
Workspace-Konzept abgelöst.

## Ziel

BM-Routencheck wird in der GUI zum professionellen **Single-Window
Workspace** nach Google Material Design (Desktop-adaptiert): links ein
immer sichtbares Control Panel mit allen Routing-Parametern, rechts eine
dynamische Main View mit Kennzahlen, Karte und Relais-Tabelle. Kein
Wizard, kein Bildschirmwechsel — Parameter ändern und direkt neu
berechnen. Zusätzlich bekommt das Projekt einen **PDF-Export**, der
Bericht und Karte sauber druckbar aufbereitet (GUI-Button und
Terminal-Flag).

Der Terminal-Modus bleibt vollwertig und unverändert erhalten; die
Pipeline bleibt die eine Quelle der Wahrheit (keine Duplizierung).

## Festlegungen (Nutzerentscheidungen 2026-07-19)

| Punkt | Entscheidung |
|---|---|
| Karte | **Native Leaflet-Einbindung** im App-Frontend (Leaflet lokal gebündelt, Daten über die Bridge). Ermöglicht Tabelle↔Karte-Interaktion und einheitliches Styling. Die Folium-Karte (`karte.html`) bleibt als Datei-Export für den Browser erhalten. |
| Bericht | **Bleibt als Datei:** Das In-App-DataGrid wird direkt aus den Ergebnisdaten gespeist; `bericht.html` wird weiterhin bei jedem Lauf erzeugt und über »Bericht öffnen« im Browser angezeigt. |
| Log-Konsole | **Ja, wie im Konzeptbild:** Während der Berechnung obere Hälfte Fortschritts-Karte, untere Hälfte scrollende Log-Konsole mit den Pipeline-Meldungen. |
| Control Panel | **Felder wechseln je Modus:** Der Segmented Button (Bahn/Auto/Rad) schaltet den Feldsatz um; alle bisherigen Eingabewege (Bahn: bahn.de-Link oder Bahnhöfe+Zuggattung+Zeit+Optionen; Auto/Rad: Link, GPX oder Orte) bleiben erhalten. |
| PDF-Technik | **reportlab + eigenes Kartenbild:** reines Python-Paket (pip, cross-platform, keine Systembibliotheken). Kartenbild wird aus OSM-Kacheln + Route + Abdeckungs-Overlay + Markern per Pillow komponiert (numpy/Pillow sind schon Abhängigkeiten). |
| PDF-Inhalt | **Deckblatt + Karte + Tabelle** (DIN A4): Seite 1 mit Titel, Route, Datum, Kennzahlen und Übersichtskarte; danach Relais-Tabelle mit sauberen Seitenumbrüchen und Talkgroup-Details je DMR-Relais; Fußzeile mit Seitenzahl und Datenstand. |
| PDF-Auslöser | **Auf Knopfdruck:** Button in der Top-Bar; Ablage im Ausgabeordner des Laufs. Im Terminal gleichwertig per Flag `--pdf`. Kein Automatik-Export bei jedem Lauf. |
| Theme | **System folgen + Umschalter:** Start mit OS-Theme (`prefers-color-scheme`); über das Zahnrad in der Statusleiste fest auf Hell/Dunkel stellbar (wird gemerkt). |
| Icons | **Google Material Symbols (Outlined)**, lokal gebündelt als Teilmenge (kein CDN — Keyless/offlinefähig). Emojis werden restlos aus der GUI entfernt. |

Frühere Festlegungen, die weiter gelten (2026-07-18): pywebview als
Fenstertechnik, automatische Startlogik (`--gui`/`--terminal`,
Desktop-Erkennung), alles in einem Binary (kein App-Bundle/PyInstaller,
nur das pip-Paket), GUI durchgängig Deutsch. Bestehende
Projektprinzipien (PROJEKTPLAN.md §3) gelten weiter: Keyless, Kein
Try&Error (jeder Meilenstein endet mit abgenommenem Testlauf),
Konsistenz der Ausgaben.

## Basis aus der ersten Ausbaustufe (bleibt bestehen)

- **Startlogik** (G1): Desktop-Erkennung, `--gui`/`--terminal` in allen
  vier Kommandos.
- **Pipeline-Entkopplung** (G2): `Melder`-Protocol
  (`routelib/melden.py`), Terminal-Ausgaben byte-identisch.
- **Bridge + Hintergrund-Lauf** (G4): `bmtools/gui/` mit
  `bridge.py`/`lauf.py`/`melder.py`, Pipeline im Thread, sofortiges
  Abbrechen, interaktive Rückfragen als Dialoge, Ereignis-Drossel.
- Das Frontend (`static/`: index.html, app.js, stil.css) wird dagegen
  weitgehend neu geschrieben.

---

## 1. App-Architektur: Der Single-Window Workspace

Split-Pane: statisches **Control Panel** links, dynamische **Main View**
rechts, **Statusleiste** unten.

### 1.1 Control Panel (linke Seitenleiste, ca. 300–350 px)

Immer sichtbar; Werte ändern und direkt neu berechnen, ohne »zurück«.

- **Modus-Wahl (Segmented Button):** Material Icons `train` (Bahn),
  `directions_car` (Auto), `pedal_bike` (Rad). Der Modus schaltet den
  Feldsatz darunter um:
  - *Bahn:* bahn.de-Verbindungslink **oder** Startbahnhof, Zwischenhalte,
    Zielbahnhof, Zuggattung, Abfahrtszeit, Optionen (nur
    Direktverbindungen, Ankunftszeit statt Abfahrt).
  - *Auto/Rad:* Start, Zwischenziele (optional), Ziel **oder**
    Routen-Link (Google Maps/Komoot) **oder** GPX-Import
    (Button `upload_file`).
  - Feld-Validierung wie bisher über dieselben Parser wie der
    Terminal-Assistent (Bridge `pruefe_feld`).
- **Relais-Filter:** Dropdown DMR (Brandmeister), Analoge FM-Relais,
  Beide — wie der bestehende `modus`-Parameter der Pipeline.
- **Aktion:** dominanter Button **»Berechnen«** (Icon `route`) am
  unteren Ende. Während eines Laufs wird er zum
  **»Abbrechen«**-Button (Icon `close`, Amber) — Abbruch wirkt sofort
  (G4-Verhalten).
- Darunter dezent das Zahnrad `settings` (siehe 1.4).

### 1.2 Main View (rechter Hauptbereich, flexibel skalierend)

**Leerzustand** (vor dem ersten Lauf): App-Titel und kurzer Hinweis,
was zu tun ist — keine leere Karte.

**Während der Berechnung** (Konzeptbild 1):

- Obere Hälfte: zentrierte Fortschritts-Karte — Titel
  »Routenberechnung läuft…«, unbestimmter Kreis-Spinner, darunter je
  Pipeline-Phase ein beschrifteter Fortschrittsbalken mit Prozent
  (Quelle: vorhandene `Melder`-Hooks; ETA-Regel wie im Terminal).
- Untere Hälfte: dunkle **Log-Konsole** (Monospace, auto-scrollend) mit
  den Pipeline-Meldungen, präfixiert `[SYSTEM]`/`[INFO]`/`[LOG]` —
  in beiden Themes dunkel (Konsolen-Charakter).

**Nach der Berechnung** (Konzeptbild 2):

- **Top-Bar (Key Metrics):** schmale Leiste mit Route
  (»Hamburg → Lindau«), Distanz, Dauer und Gesamt-Abdeckung als drei
  Prozentwerte mit Status-Icons (LoS `check_circle` grün, Grenzbereich
  `warning` amber, Schatten `cancel` rot). Rechtsbündig die Aktionen:
  **CSV Export** (`download`, Speichern-unter-Kopie von `relais.csv`),
  **PDF Export** (`picture_as_pdf`), **Bericht öffnen**
  (`open_in_browser`, öffnet Bericht und Karte im Browser wie bisher),
  **Ausgabeordner** (`folder_open`).
- **Split-View Karte & Daten** mit **anpassbarem Splitter** (Grip)
  dazwischen; Position wird gemerkt.
  - *Obere Hälfte — Leaflet-Karte:* Route als Polylinie,
    Abdeckungs-Overlay (vorhandenes Raster-PNG als ImageOverlay),
    Relais-Marker (blau = DMR, orange = FM, grau = nur
    Grenzbereich/Beugung), Legende, Zoom-Kontrollen, Layer-Umschalter
    (OSM / Carto-Ausweichkarte) — funktional gleichwertig zur
    Folium-Karte.
  - *Untere Hälfte — DataGrid:* Relais-Tabelle mit Spalten km,
    Rufzeichen, Standort, Abstand, Modus, RX/TX [MHz], Tone/CC, Status
    (Icon + Text). Suchfeld filtert live; Spalten klick-sortierbar;
    natives Scroll-Verhalten (Mausrad/Touchpad-Trägheit). DMR-Zeilen
    sind aufklappbar und zeigen **Talkgroup-Details** (TS, TG, Name).
  - *Interaktivität Tabelle↔Karte:* Klick auf eine Zeile zentriert und
    hebt den zugehörigen Marker hervor; Klick auf einen Marker scrollt
    zur Zeile und hebt sie hervor.

### 1.3 Statusleiste (untere Fensterkante)

- Links: »API-Status: Verbunden« und Link »Cache leeren…«.
- Mitte/rechts: aktueller Hintergrund-Schritt (»Lade Höhenkacheln…«)
  bzw. nach dem Lauf »Letzte Berechnung: HH:MM · Datenstand: TT.MM.JJJJ«.
- Ganz rechts: Zahnrad `settings`.

### 1.4 Einstellungen (Zahnrad)

Kleines Menü/Dialog: Theme (System/Hell/Dunkel, wird gemerkt),
Cache-Info + Cache leeren (vorhandene Bridge-Funktionen),
Ausgabeordner öffnen.

## 2. Iconographie & visuelle Sprache

- **Google Material Symbols (Outlined)** als lokal gebündelte Teilmenge
  (nur benötigte Glyphen; Apache-2.0-Lizenz wird beigelegt). Keine
  CDN-Zugriffe. Sämtliche Emojis entfallen.
- **Status-Farben:** Gute Sicht `#10B981` (Material Green),
  Grenzbereich `#F59E0B` (Material Amber), Funkschatten `#EF4444`
  (Material Red) — identisch in Tabelle, Top-Bar, Karte und PDF.
- **Typografie:** `system-ui`-Stack, konsistente Paddings und
  Komponenten (Buttons, Checkboxen, Textfelder mit Floating Label,
  Scrollbars) auf allen drei Plattformen — Custom Theme statt
  OS-Mimikry.
- **Dark & Light Mode:** vollständige Token-Paare (Flächen, Text,
  Linien, Hover `rgba(0,0,0,.04)` hell / `rgba(255,255,255,.06)`
  dunkel); Karte und Log-Konsole werden nicht invertiert.

## 3. Modal- und Dialog-Verhalten

- **Disambiguierung (Ortsauswahl):** mehrdeutige Orte öffnen einen
  zentrierten MDC-Dialog mit klickbarer Liste (Hover-Effekt); ein Klick
  wählt aus und schließt sofort. Die App friert nicht ein (Lauf im
  Hintergrund-Thread wartet auf die Antwort — Mechanik aus G4).
- Gleiches Muster für die **Bahn-Verbindungswahl** und Bestätigungen;
  die Assistenten-Reihenfolge-Regel (Modus-Frage zuletzt) gilt
  unverändert.
- Abbrechen im Dialog bricht den Lauf ab (wie bisher).

## 4. PDF-Export

Neues Modul `routelib/report_pdf.py` (+ `routelib/mapimage.py` für das
Kartenbild), Abhängigkeit `reportlab>=4.0`.

- **Kartenbild (`mapimage.py`):** komponiert per Pillow aus
  OSM-Kacheln (gecacht wie die Höhenkacheln, mit korrektem User-Agent),
  Routen-Polylinie, Abdeckungs-Overlay (vorhandenes Raster) und
  Relais-Markern in den Statusfarben; Maßstabsleiste und
  OSM-Attribution ins Bild gerendert.
- **PDF (`report_pdf.py`), DIN A4 Hochformat:**
  - Seite 1 (Deckblatt): Titel, Route, Modus, Datum/Datenstand,
    Kennzahlen (Distanz, Dauer, Abdeckung LoS/Grenzbereich/Schatten)
    und die Übersichtskarte.
  - Folgeseiten: Relais-Tabelle (km, Rufzeichen, Standort, Modus,
    RX/TX, Tone/CC, Status) mit wiederholtem Tabellenkopf und sauberen
    Seitenumbrüchen; unter jedem DMR-Relais die Talkgroup-Details.
  - Fußzeile: Seitenzahl, Erzeugungsdatum, Datenstand.
  - Gleiche Statusfarben und Begriffe wie GUI/Bericht.
- **Auslöser:** GUI-Button »PDF Export« in der Top-Bar (Ablage als
  `bericht.pdf` im Ausgabeordner, danach Hinweis + öffnen); Terminal:
  Flag `--pdf` bei `bm-bahn`/`bm-auto`/`bm-rad`/`bmtools` erzeugt das
  PDF zusätzlich zu den bisherigen Dateien. Kein Automatik-Export.

## 5. Architektur / Datenfluss

- **Bridge erweitert:** `lade_ergebnis()` liefert statt HTML-Schnipseln
  strukturierte Ergebnisdaten (Route-Koordinaten, Overlay-Bild als
  Datei/Daten-URI, Relais-Liste inkl. Talkgroups, Kennzahlen) als JSON
  an das Frontend; neue Methoden `export_csv()`, `export_pdf()`,
  `setze_theme()`.
- **Frontend neu:** `static/` wird zum Workspace umgebaut
  (Split-Pane-Layout, DataGrid, Leaflet lokal gebündelt in
  `static/vendor/leaflet/`). Kein Framework — weiterhin
  Vanilla-HTML/JS/CSS.
- **Pipeline unverändert:** `run_pipeline` erzeugt weiter
  `relais.csv`, `bericht.html`, `karte.html`, Codeplug-Dateien; die
  GUI erhält die Ergebnisdaten über den vorhandenen `ergebnis()`-Hook
  (Terminal: No-op). PDF ist nachgelagert und nutzt dieselben
  Ergebnisobjekte.

## Meilensteine (ein Commit je Schritt)

- [x] **U0 — Plan** *(abgenommen 2026-07-19)*: dieses Dokument
      (ersetzt den Plan vom 2026-07-18); `GUI-UMBAU.md` committet.
- [x] **U1 — Workspace-Grundgerüst** *(abgenommen 2026-07-20 nach vier
      Befunden: Selects nativ ohne Padding → appearance:none + eigener
      Chevron; Etikett-Chip stand dunkel auf hellerer Feldfläche →
      zweifarbiger Chip; Trennlinie vor dem Relais-Filter; Fenster
      780→860 hoch, Zahnrad vom Panel-Fuß in die Statusleiste)*:
      Split-Pane-Layout (Control Panel / Main View / Statusleiste),
      Theme-Token Hell/Dunkel inkl. System-Erkennung,
      Material-Symbols-Teilmenge gebündelt (Sprite via
      packaging/sprite_erzeugen.py, Quellen + Apache-2.0-Lizenz unter
      static/vendor/), Emojis entfernt. Control Panel mit Segmented
      Button und Feldwechsel je Modus, Validierung über die Bridge
      (neu: pruefe_eingaben); Leerzustand der Main View. Noch ohne
      Lauf.
- [ ] **U2 — Fortschrittsansicht:** Lauf aus dem Control Panel,
      Fortschritts-Karte (Spinner + Phasen-Balken) oben, Log-Konsole
      unten, Berechnen↔Abbrechen-Wechsel, Statusleisten-Schritt.
      *Abnahme:* je ein Bahn-, Auto- und Rad-Lauf mit sichtbarem
      Fortschritt und sofort wirksamem Abbruch.
- [ ] **U3 — Material-Dialoge:** Geocoding-Auswahl, Bahn-Verbindungswahl
      und Bestätigungen als zentrierte MDC-Dialoge mit klickbarer Liste
      (Ein-Klick-Auswahl). *Abnahme:* mehrdeutiger Ort (»Hamburg«) und
      Bahn-Verbindungswahl in der GUI.
- [ ] **U4 — Leaflet-Karte:** Leaflet lokal gebündelt; Route, Overlay,
      Marker, Legende, Layer-Umschalter aus den Bridge-Daten;
      funktional gleichwertig zur Folium-Karte. *Abnahme:*
      Sichtvergleich GUI-Karte gegen `karte.html` desselben Laufs.
- [ ] **U5 — DataGrid + Top-Bar + Splitter:** Kennzahlen-Top-Bar,
      sortier-/filterbare Relais-Tabelle mit Status-Icons und
      aufklappbaren Talkgroups, Tabelle↔Karte-Interaktion, ziehbarer
      Splitter (Position gemerkt), Aktionen CSV Export / Bericht öffnen /
      Ausgabeordner. *Abnahme:* Sichtprüfung + Stichproben-Abgleich
      Tabelle gegen `bericht.html`.
- [ ] **U6 — Einstellungen:** Zahnrad-Menü mit Theme-Umschalter
      (System/Hell/Dunkel, persistiert), Cache-Info/-Leeren,
      Ausgabeordner. *Abnahme:* Sichtprüfung, Persistenz nach Neustart.
- [ ] **U7 — Kartenbild-Renderer:** `routelib/mapimage.py`
      (Kacheln + Route + Overlay + Marker + Maßstab + Attribution,
      Kachel-Cache). *Abnahme:* Bildvergleich gegen die Leaflet-Ansicht
      desselben Laufs.
- [ ] **U8 — PDF-Export:** `routelib/report_pdf.py` (reportlab),
      Deckblatt + Karte + Tabelle + Talkgroups + Fußzeilen;
      GUI-Button und `--pdf`-Flag. *Abnahme:* PDF eines langen Laufs
      (Seitenumbrüche!) und eines kurzen Laufs, Sichtprüfung Druckbild.
- [ ] **U9 — QS + Doku:** `make qs` grün (Lint, mypy strict, Tests;
      GUI-Logik so weit wie sinnvoll unit-getestet, Webview-Rendering
      ausgenommen), README (GUI, PDF, `--pdf`), DEVELOPER.md (Bridge-
      Datenfluss, Leaflet-Bündelung, mapimage/report_pdf),
      PROJEKTPLAN.md nachgeführt. *Abnahme:* interaktiver Gegentest
      (Beta), danach Merge-Entscheidung.

## Risiken / offene Punkte

- **Kachel-Nachladen fürs PDF:** OSM-Kacheln für das Kartenbild kommen
  aus dem Netz (Keyless heißt ohne Schlüssel, nicht offline); höflicher
  Umgang (User-Agent, Cache, moderate Zoomstufe) ist Pflicht, sonst
  drohen 403er der Tile-Server.
- **DataGrid-Performance:** lange Routen liefern hunderte Relais;
  Sortieren/Filtern muss ohne Framework flott bleiben (einfaches
  virtuelles Rendern oder Batch-DOM, erst messen, dann optimieren).
- **Leaflet-Bündelung:** Version fixieren, Lizenz beilegen; Marker-
  Assets (PNG/SVG) gehören mit ins Paket — keine externen Requests
  außer Kartenkacheln.
- **reportlab-Schriften:** Standard-PDF-Schriften (Helvetica) decken
  Umlaute ab; kein Font-Embedding nötig, sonst wächst das Paket.
- **pywebview-Backends:** unverändert — Linux braucht GTK/WebKit2 oder
  QtWebEngine (README-Hinweis besteht).
- questionary/rich bleiben für den Terminal-Modus vollwertig erhalten —
  kein schleichender Rückbau.
