# BM-Routencheck — Projektplan

Stand: 2026-07-21

## 1. Status

Die drei Tools `bm-bahn`, `bm-auto` und `bm-rad` sind fertig und abgenommen
(gemeinsamer Kern in `bmtools/routelib/`, Bedienung siehe
[README](README.md), Technik siehe [DEVELOPER.md](DEVELOPER.md)). Seit dem
FM-Umbau (2026-07-15) werten sie neben Brandmeister-DMR auch analoge
FM-Relais aus (`--modus`, Default beide; Quelle: relaislisten.darc.de);
je Lauf entstehen HTML-Bericht, interaktive Karte, CSV, Codeplug-Dateien
(AnyTone, CHIRP) und auf Wunsch ein PDF-Bericht.

Seit dem GUI-Umbau (2026-07-18 bis 2026-07-21, Branch
`feature/gui-umbau`) ist die grafische Oberfläche das Hauptprodukt: ein
Single-Window Workspace auf pywebview-Basis (der Aufruf ohne
Routen-Argumente öffnet auf dem Desktop das Fenster, `--gui`/`--terminal`
erzwingen), ein PDF-Export (`--pdf` bzw. GUI-Knopf, `bericht.pdf`), ein
eigenes Programmicon (Navi-Karten-Motiv, Master
`packaging/icon/icon.svg`) und eine plattformgerechte Auslieferung:
macOS `BM-Routencheck.app` (signiert, notarisiert, Ticket angeheftet),
Windows eine windowed `BM-Routencheck.exe` (AttachConsole-Shim für die
Terminal-Ausgabe), Linux das Binary `bmtools` mit gebündeltem
Qt/WebEngine-Backend. Die Terminal-Bedienung bleibt auf allen Plattformen
vollwertig erhalten. Alle Meilensteine sind abgenommen (Grundstufe
G0–G5, Workspace U0–U9, GUI-first-Auslieferung A1–A9) und über die
Beta-Releases v0.2.0-beta.1 bis beta.6 interaktiv gegengetestet
(abgeschlossen 2026-07-21); veröffentlicht als Featureversion **0.2.0**
(2026-07-21). Frühere Releases: v0.1.1 und v0.1.2 (beide 2026-07-17 —
Fortschrittsbalken mit ETA, Cache-leeren-Funktion, Trennung von README
und DEVELOPER.md).

Dieses Dokument hält nur noch fest, was für die Weiterarbeit gebraucht
wird: offene Punkte, verbindliche Festlegungen und die Eigenheiten der
externen Datenquellen. Die Abnahmeprotokolle der erledigten Meilensteine
sind in der Git-Historie nachlesbar — M0–M6 und R0–R5 in der dieses
Dokuments, FM-Umbau F0–F3 in der von `FM-UMBAU.md` (mit F4 aufgelöst),
GUI-Umbau G0–G5 und U0–U9 samt Konzept und Nutzerfestlegungen in der von
`GUI-UMBAU.md` (mit U9 aufgelöst).

## 2. Offene Punkte

- [ ] **M5 — AnyTone AT-D890UV (ruht):** Der Codeplug-Export in
      `bmtools/routelib/codeplug/anytone.py` nutzt das D878UV-Spaltenlayout
      als Arbeitsannahme; das CSV-Layout des D890UV ist nicht gesichert
      dokumentiert. Wartet auf einen Beispiel-Export (Channel/TalkGroups/
      Zone-CSV) aus der Nutzer-CPS — kein Blindformat. Danach Header/Defaults
      anpassen und Importtest in der CPS.
- [ ] **FM-Umbau, letzte Abnahme:** Import von `anytone/` mit analogen
      Kanälen in der AnyTone-CPS prüfen (A-Analog-Kanal mit korrektem
      CTCSS; CC/Slot/DMR-MODE tragen benigne Werte 1/1/0 und sollten
      ignoriert werden). Der CHIRP-Import ist bereits programmatisch
      gegen den Upstream-Treiber verifiziert (F3, 2026-07-15).
- [ ] Google-Link mit per Maus verschobener Route (Drag-Via) an einem echten
      Link verifizieren — Heuristik ist implementiert und unit-getestet,
      ein echter Beispiel-Link steht noch aus.

### Ideen (unverbindlich, kein Auftrag)

Nichts davon ist zugesagt — die Liste hält nur fest, worüber gesprochen
wurde, damit §2 ausschließlich echte Verpflichtungen führt:

- Lastheard-Monitor via MQTT/WebSocket.
- TG-Aktivitätsstatistik.

## 3. Verbindliche Festlegungen

Projektprinzipien:

| Prinzip | Bedeutung |
|---|---|
| Keyless | Nur Dienste ohne API-Key/Anmeldung; keine Credentials im Tool verarbeiten (bewusste Entscheidung, z. B. kein Komoot-Login) |
| Kein Try&Error | Jede Erweiterung endet mit einem konkreten, abgenommenen Testlauf |
| CLI durchgängig Deutsch | Kommandos `bm-bahn`/`bm-auto`/`bm-rad`, deutsche Flags; englische Originale bleiben als stille Aliasse gültig (Skript-Kompatibilität); argparse-Standardtexte via `ui.argparse_deutsch()` |
| GUI | Single-Window Workspace (pywebview, Material-Anmutung, durchgängig Deutsch); auf dem Desktop öffnet der Aufruf ohne Routen-Argumente das Fenster, `--gui`/`--terminal` erzwingen; Terminal-Modus bleibt vollwertig (kein schleichender Rückbau von questionary/rich); Frontend-Assets (Leaflet, Material Symbols) lokal gebündelt, keine CDN-Zugriffe; PDF nur auf Knopfdruck bzw. `--pdf`, kein Automatik-Export (Festlegungen 2026-07-19; Plan-Historie: `GUI-UMBAU.md` in Git); GUI-first-Auslieferung (2026-07-21): macOS nur `BM-Routencheck.app` im ZIP, Windows eine windowed Exe, App-Name „BM-Routencheck" |
| Auslieferungsplattformen | Gebaut werden Windows x64, Linux x64 und macOS **Apple Silicon (arm64)**. Für Intel-Macs gibt es bewusst kein Binary: kein Testgerät vorhanden, und ein ungetestetes Asset auszuliefern verstößt gegen „Kein Try&Error". Intel-Nutzer nehmen die Installation aus dem Quellcode (README) — dort ist es dokumentiert (Festlegung 2026-07-21) |
| Assistenten-Reihenfolge | Die Modus-Frage (DMR/FM/beide) ist in allen Tools die **letzte** Frage — nach kompletter Streckenwahl inkl. Geocoding-/Verbindungs-Rückfragen und Bestätigungen, nie mittendrin (Nutzerwunsch 2026-07-15) |
| Schlanke Abhängigkeiten | Bewusst kein shapely/geopandas — segmentweise Haversine-Distanz reicht |
| Konsistenz der Ausgaben | Karte, Bericht und CSV zeigen exakt dieselben Relais; Grenzbereichs-Relais sind vollwertige, markierte Einträge (graue Marker, Badge, CSV-Spalte `erreichbarkeit`) |
| Ausgabeort | **Fenster-Start schreibt nie relativ zum Arbeitsverzeichnis** — das bestimmt dort der Starter, nicht das Programm. Ziel ist auf allen Systemen `Dokumente/bm-routencheck-ergebnisse/` (`bmtools/ausgabe.py`); Terminal-Start behält `./out`, dort hat der Nutzer sein Arbeitsverzeichnis selbst gewählt. Gemeldete Pfade sind immer absolut (Beta-Befund 2026-07-26: Tester fand seine Ergebnisse nicht, sie lagen unter `~/out/`) |
| Öffnen scheitert hörbar | `system_oeffnen` verschluckt keinen Fehlschlag: absoluter Pfad hinaus, Ausweichkette, sonst `OeffnenFehler` mit den versuchten Kommandos. Die Oberfläche nennt den Grund und legt den Pfad in die Zwischenablage. Ein Knopf, der lautlos nichts tut, ist nicht diagnostizierbar (Beta-Befund 2026-07-26, Mint 22.3) |
| Abdeckung ist Geometrie, nie Feldstärke | Alle Abdeckungsaussagen beruhen ausschließlich auf Sichtlinie und Gelände (4/3-Erdradius). **Sendeleistung und Antennendiagramm sind dem Tool nicht bekannt** — keine Darstellung darf als Feldstärke oder Reichweitenprognose lesbar sein. Die Abstandsstufen des Einzelrelais-Sichtfelds (`FELD_STUFEN_KM`, dunkel = nah) sind deshalb in der Legende ausdrücklich als Abstand ausgewiesen (Festlegung 2026-07-26) |
| Karte GUI ↔ karte.html | Beide Karten zeigen dasselbe und werden aus denselben Helfern in `routelib/mapview.py` gespeist (`karten_daten` ↔ `write_map`); Legenden-Wortlaut und -Farben stehen einmal in Python (`_legende_infos`, `_feld_legende`), nie doppelt in JS. Auch die Bedienung ist gleich: Marker-Klick zeigt nur dessen Sichtfeld, Zweitklick/`Esc`/Legendenknopf führen zurück |
| Fortschrittsanzeige | Lange Pipeline-Schritte (FM-Stützpunkte, Erreichbarkeit inkl. Höhenkacheln, Karten-Sichtfelder) zeigen `ui.fortschritt()` (rich-Balken mit X/Y, Prozent); die ETA-Spalte blendet erst ab > 10 s geschätzter Restzeit ein und bleibt danach bis zum Abschluss stehen (Nutzerwunsch 2026-07-17) |
| UI-freie Bibliotheksschichten | `bm_api`/`fm_api`/`routelib` importieren nichts aus `ui.py`; Fortschritt wird über optionale `(fertig, gesamt)`-Callbacks nach außen gereicht, die Pipeline hängt daran die Balken |
| Doku-Trennung | `README.md` richtet sich an Endnutzer (Download, Bedienung, Ausgaben); Technik (Architektur, QS, Cache-Interna, Release-Prozess) steht in `DEVELOPER.md` — beide verweisen aufeinander (Nutzerfestlegung 2026-07-17) |

Fachliche Regeln (dürfen bei Änderungen nicht regressieren):

| Regel | Festlegung |
|---|---|
| Relais-Auswahl | Rechnerische Erreichbarkeit von der Strecke (Sichtkontakt zu ≥ 1 Streckenpunkt im Geländemodell) statt festem Korridor; `--korridor` nur als optionales Abstands-Limit; kein implizites Distanz-Limit |
| Frequenz-Sicht | Alle Ausgaben aus Sicht des Funkgeräts (RX = Relais-Ausgabe) — gilt für DMR und FM |
| Modus | `--modus {dmr,fm,beide}`, Default `beide` (Festlegung 2026-07-15; ändert die Ausgaben alter Aufrufe bewusst). Reines DMR sieht aus wie vor dem Umbau: Modus-/CTCSS-Spalten erscheinen nur, wenn FM dabei ist |
| Bandfilter | Nur 2-m- und 70-cm-Relais sind relevant (Festlegung 2026-07-15, Dualband-Funkgeräte) — 10-m-/6-m-/23-cm-Einträge beider Quellen werden in der Pipeline aussortiert |
| FM-Regeln | **CTCSS ist der dauerhaft mitgesendete Pilotton (unhörbarer Subaudioton, 67–254 Hz) — viele Relais öffnen NUR damit.** Ein angegebener Ton wird deshalb immer als Encode gesetzt (Codeplug UND Bericht); Decode default offen (`--ctcss-decode` setzt den Relais-Ton). **Nicht zu verwechseln mit dem 1750-Hz-Tonruf** — das ist ein kurzer hörbarer Rufton zum Auftasten klassischer Relais (eigene Gerätetaste, kein Kanalfeld im Codeplug). Die DL3EL-Quelle führt **kein Tonruf-Feld** (geprüft 2026-07-15: CSV-Spalten und Webansicht vollständig gesichtet) — Bericht („Öffnen mit"-Spalte) und Karten-Popup weisen deshalb je Relais ehrlich aus: „CTCSS (wird gesendet)" bei gelistetem Ton, sonst „Träger oder 1750-Hz-Tonruf". Ablage stets aus rx−tx berechnen, nie annehmen (NL-70cm nutzt +1,6 MHz); Bandbreite Codeplug default 12,5 kHz, `--bandbreite 25` global (kein Raster in den Daten). TG9/Slot-0/Colorcode-Regeln gelten NICHT für FM |
| FM-IDs | Synthetisch negativ (CRC32-Hash über Call+QRG, stabil über Läufe) — kollidieren nie mit den 6-stellig positiven BM-IDs; bleiben ein Internum (CSV-Spalte `dmr_id` bleibt bei FM leer) |
| Marker-Farben | DMR blau, FM **orange** (kein Grün — Farbwelt ohne Rot/Grün, CVD-sicher, s. `ui.py`), Grenzbereich grau |
| TG9 Lokal | Wird immer ergänzt (TS2, bei Simplex TS1) — die API listet sie nie |
| Slot 0 | = „keine Slot-Angabe": bei Simplex-Repeatern (RX=TX) Anzeige „1 (Simplex)", Codeplug Slot 1 + DMR MODE 0. Auf Duplex-Relais ist Slot 0 eine Sysop-Miskonfiguration und wird komplett verworfen |
| Relais ohne TGs | Bleiben in allen Ausgaben sichtbar (vollständiges Lagebild), mit TG9 als Minimum |
| Geländemodell | Sichtlinienprüfung mit 4/3-Erdradius, dreistufig Sicht / Grenzbereich (≤ 30 m Hindernis) / Schatten, Schatten-Lücken ≥ 5 km; Antennenhöhe mobil 2,0 m; `--ohne-gelaende` = Horizontmodell-Fallback (auch bei Downloadfehler) |
| Cache-TTLs | Geräteliste 1 Tag, Profile 12 h („ändern sich am ehesten"), TG-Namen 7 Tage, Höhenkacheln unbegrenzt; `--aktualisieren` erzwingt frische Daten; kompletter manueller Reset über `bmtools/cache_admin.py` (Menüpunkt „Cache leeren“ bzw. `bmtools cache --leeren`) |
| Motorola | Kein automatischer Import — Eingabe manuell anhand des HTML-Berichts (Kanaltabellen sind dafür ausgelegt) |
| HTML-Ausgaben | Vollständiges HTML5 mit `<meta charset="utf-8">` + Viewport (sonst Zeichensalat auf Mobilgeräten); Tabellen in scrollenden Wrappern |
| Kartenkacheln | `tile.openstreetmap.de` (FOSSGIS), nicht `tile.openstreetmap.org`: Die OSMF-Server verlangen einen Referer, den eine per file:// geöffnete karte.html nie sendet („Access Blocked"); kein JS-Workaround möglich. Carto-CDN als umschaltbare Ausweich-Ebene |

## 4. Eigenheiten der Datenquellen

Alles Folgende ist verifiziert (Daten in Klammern) und beim Weiterbau zu
beachten:

**Brandmeister-API** (`api.brandmeister.network/v2`, keyless, nur lesend):

- `/device` listet nur Geräte, die in den letzten 24 h online waren;
  dauerhaft offline Relais fehlen (akzeptiert).
- Die Geräteliste mischt Hotspots und Repeater. Filterregel: 6-stellige
  DMR-ID = Repeater, plus Plausibilität RX ≠ TX (validiert: 2.834 Repeater
  aus ~32.600 Geräten).
- `/device/{id}/profile` nur einzeln pro Gerät → Disk-Cache ist Pflicht,
  moderate Request-Rate.
- `timedSubscriptions`: ein Datensatz pro Wochentag (`data` mit
  Wochentags-Flags, `start`/`stop` in Tagessekunden, `startDate`/`endDate`
  als Unix-Gültigkeitszeitraum). Zeiten sind **Lokalzeit** (verifiziert
  2026-07-11 am Frankenrundspruch; offizielle Doku existiert nicht).
- MQTT/Live-Events werden von den Routen-Tools nicht benötigt (relevant
  erst für Lastheard-Monitor o. Ä.).

**DL3EL-Relaisliste** (`relaislisten.darc.de/cgi-bin/relais.pl`, keyless
CGI, Hobby-Projekt ohne SLA — analoge FM-Relais; alles verifiziert
2026-07-15, FM-Umbau F0):

- **Nur Umkreissuche, kein Volldump:** zurück kommen die `maxgateways`
  nächsten Relais um einen Punkt, nach Entfernung sortiert. Der Client
  rastert die Route deshalb alle 50 km (plus Ziel) und fragt je Stützpunkt
  mit `maxgateways=200` ab — Dichte-Check Ruhrgebiet: Eintrag Nr. 100 liegt
  dort schon bei 75 km, Nr. 200 bei 129 km; 100 wäre zu knapp für die
  60-km-Coverage-BBox plus halbe Schrittweite.
- **`type` ist Mehrfachauswahl; unsere Kombination: `type=DL3EL&type=fr`.**
  Die DL3EL-Basisliste allein ist unvollständig (um Nürnberg fehlten fünf
  echte FM-Relais, die nur in der `fr`-Liste stehen); Echolink/IRLP (`el`/
  `il`) liefern fast nur Dubletten ohne Input-QRG und bleiben draußen.
- Die Listen überlappen sich, der Server dedupliziert **nicht** →
  Client-Dedupe über (Rufzeichen, Ausgabefrequenz gerundet); bei Dubletten
  ersetzt ein Eintrag **mit** CTCSS einen tonlosen (DB0THM trägt den Ton
  nur im `fr`-Eintrag), bei widersprüchlichen Tönen gewinnt der erste
  (DB0CJ: 71,9 vs. 100,0 Hz — Quelldaten uneins).
- **Schmutzige Formate:** ISO-8859-1, Zeilen enden auf `<br>`,
  HTML-Entities auch ohne Schluss-Semikolon (`F&#252rth`), Dezimalkomma.
  Entities **vor** dem Spalten-Split dekodieren — `&deg;` enthält selbst
  ein `;`. CSV-Koordinaten sind nur bogenminutengenau; die dezimalen
  Koordinaten liefert ein zweiter GPX-Abruf derselben Query (HTML-Präambel
  und `<br>`-Präfixe → Regex statt XML-Parser), gemergt über (Call, QRG).
- Einzelne Zeilen sind unbrauchbar und werden verworfen (Input leer,
  `#WERT!`, `Simplex`, `0,0000`; auch mal eine deutsche Ausgabe-QRG `00`) —
  um Nürnberg 0/100, um Aachen 7/300. Auslandsdaten (`dxcc=all`,
  Festlegung 2026-07-15) sind brauchbar: Koordinaten und CTCSS vorhanden,
  aber **Ablagen abweichend** (NL-70cm +1,6 MHz).
- Keine Antennenhöhe in den Daten → `DEFAULT_AGL_M = 15 m` greift; die
  Abdeckungsschätzung ist für FM konservativer als für BM.
- Inaktive Relais unterdrückt der Default (kein `showall=all`) — Analogie
  zur BM-24h-Regel. Cache: Rohantworten 24 h, Key = auf 0,1° gerasteter
  Stützpunkt (abgefragt wird der Rasterpunkt selbst, damit ähnliche Routen
  Treffer teilen); Drosselung 1 s Grundpause. Negative Koordinaten
  (`South`/`West`-Formularwörter) live verifiziert.
- **Während der Server seinen Cache neu aufbaut, antwortet er mit HTTP 200
  und „Cacheupdate is running, please come again in 30s" statt Daten**
  (beobachtet 2026-07-15: die Antwort wurde 24 h gecacht, halbe Route ohne
  FM-Relais). Der Client erkennt den Marker, wartet 30 s und versucht neu;
  Antworten ohne parsebare Relais werden nie gecacht (die Liste ist
  weltweit, `maxgateways` nächste Relais gibt es immer), vergiftete
  Alt-Einträge werden beim Lesen verworfen und neu geholt.
- DL3ELs eigene CHIRP-Ausgabe (`printas=chirp`) dient als Referenz für die
  Feldkonventionen unseres `chirp.csv` (Fixture
  `tests/fixtures/dl3el_nuernberg.chirp`); sie liefert keine Koordinaten
  und schreibt bei Simplex-Einträgen uneinheitliche Duplex-/Offset-Reste.

**Transitous** (`api.transitous.org`, MOTIS, keyless, Community ohne SLA):

- `maxTransfers=0` liefert fälschlich leere Ergebnisse (verifiziert
  2026-07-11) → `--direkt` wird clientseitig gefiltert.
- API-Zeiten sind UTC → Anzeige in Systemzeitzone umrechnen.
- Bei `directModes` (Fallback-Routing) `maxDirectTime=86400` setzen, sonst
  filtert das Default-Limit lange Abschnitte weg.
- Geocoding: `/geocode` ohne `type=STOP` ist hausnummerngenau (Entscheid
  gegen Photon, 2026-07-13).

**Google-Maps-Links:**

- Der Link enthält keine Routen-Geometrie, nur Wegpunkte — das Tool routet
  selbst (OSRM). Die exakte Google-Route gäbe es nur über die Directions
  API (Key + Abrechnung) — bewusst nicht.
- Der `data=`-Blob ist reverse-engineered (`!1d<lon>!2d<lat>` je Wegpunkt,
  `!3e0`=Auto/`!3e1`=Rad/`!3e2`=Fuß/`!3e3`=ÖPNV) und kann sich ändern →
  Parser defensiv, Fallback auf Pfad-Wegpunkte + Geocoding.
- Kurzlinks (`maps.app.goo.gl`): ein einziger 302 ohne Consent-Wall
  (verifiziert); scheitert die Expansion, klare Fehlermeldung („vollständige
  URL aus der Adresszeile kopieren").
- ÖPNV-Links → Fehlermeldung mit Verweis auf `bm-bahn`.

**Komoot** (`api.komoot.de/v007`, inoffiziell, reverse-engineered):

- Tour-Geometrie via `/tours/<id>` + `/tours/<id>/coordinates`; bei
  privaten Touren `?share_token=…` (aus dem „Mit Link teilen"-Link) an
  beide Calls anhängen, sonst 403.
- URL-Formen: `…/tour/<id>` und `…/smarttour/e<id>/…` (`e`-Präfix
  abschneiden).
- Fallback-Stufen, falls sich die API ändert: (a) Koordinaten-JSON steckt
  im HTML der Tour-Seite, (b) GPX-Export aus der App als garantierter Weg
  (`--gpx`). Der API-Endpunkt `tours/<id>.gpx` verlangt Login (403 auch mit
  share_token).

**OSRM** (`routing.openstreetmap.de`, FOSSGIS, keyless, ohne SLA):

- Profile `routed-car`/`routed-bike`, Polyline-Präzision 5, Via-Punkte ok.
- Fallback-Kette: OSRM → Transitous `directModes` → Luftlinie mit Warnung.

**Höhendaten** (AWS Terrain Tiles, Terrarium-Format):

- Zoom 11 ≈ 50 m Raster, Disk-Cache unbegrenzt (Gelände ändert sich nicht).
