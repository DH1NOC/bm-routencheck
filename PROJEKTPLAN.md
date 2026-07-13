# BrandmeisterTools — Projektplan

Stand: 2026-07-13

## 1. Ziel

Sammlung von Python-Tools rund um das Brandmeister-Netzwerk (DMR & Tetra).
Gemeinsame Basis: ein wiederverwendbarer Brandmeister-API-Client.

**Tool 1 — `bm-rail`:** Findet alle DMR-Relais entlang einer Bahnstrecke
(z. B. ICE Koblenz–Nürnberg) und liefert pro Relais: Rufzeichen, RX/TX-Frequenz,
Colorcode, Standort, Entfernung zur Strecke sowie die Talkgroups in TS1/TS2 —
statisch, zeitgeschaltet und per Cluster.

**Tool 2/3 — `bm-car` / `bm-bike`:** Dieselbe Auswertung für Auto- und
Radrouten; Eingabe per Google-Maps-Link, Komoot-Tour-Link, GPX-Datei oder
Start/Ziel-Text (Plan und Verifikation: Abschnitt 7; fertig seit 2026-07-13).

## 2. Verifizierte Datenlage (getestet am 2026-07-11)

| Bedarf | Quelle | Status |
|---|---|---|
| Alle Relais mit Position, RX/TX, CC, Rufzeichen | `GET api.brandmeister.network/v2/device` (~32.600 Geräte, ohne Auth) | ✅ bestätigt |
| Statische TGs pro Timeslot | `GET /v2/device/{id}/profile` → `staticSubscriptions` | ✅ bestätigt |
| Zeitgeschaltete TGs | `profile` → `timedSubscriptions` | ✅ Feld vorhanden; Semantik (Zeitfenster im Payload?) an einem Relais mit aktiver Zeitschaltung verifizieren |
| Cluster-TGs (z. B. TG8-Regionalcluster) | `profile` → `clusters` (inkl. `extTalkgroup`) | ✅ bestätigt |
| Streckengeometrie | **Transitous** (`api.transitous.org`, MOTIS) — Geocode + Plan mit Leg-Polylines | ✅ bestätigt; transport.rest war dauerhaft 503 und wurde ersetzt |

**Bekannte Einschränkungen (klare Ansagen):**

1. `/v2/device` listet nur Geräte, die in den **letzten 24 h online** waren.
   Dauerhaft offline Relais fehlen — für den Anwendungsfall akzeptabel.
2. Die Geräteliste enthält **Hotspots und Repeater gemischt**. Filterregel:
   6-stellige DMR-ID = Repeater; zusätzlich Plausibilität RX ≠ TX. Wird in M1 validiert.
3. Profile-Abfragen nur **einzeln pro Gerät** → bei ~60 Relais ~60 Requests.
   Lösung: Disk-Cache mit TTL + moderate Request-Rate.
4. **Motorola:** Kein automatischer Import — Entscheidung vom 2026-07-11:
   Eingabe erfolgt manuell durch den Nutzer. Deliverable ist ein sauberer,
   Copy&Paste-tauglicher **HTML-Bericht** mit allen Kanal-/TG-Daten.
   **AnyTone AT-D890UV:** CPS-CSV-Spaltenlayout des neuen Geräts ist nicht
   gesichert dokumentiert; wird in M5 recherchiert, sonst Beispiel-Export
   aus der Nutzer-CPS als Vorlage nötig. Kein Blindformat.
5. `transport.rest` ist eine Community-API ohne SLA. Fallback ist eingeplant
   (manuelle Bahnhofsliste mit Interpolation).
6. MQTT wird für Tool 1 **nicht** benötigt (nur Live-Events; relevant für spätere Tools).

## 3. Getroffene Entscheidungen

| Thema | Entscheidung |
|---|---|
| Interface | Python-CLI, z. B. `bm-rail --from Koblenz --to Nürnberg --corridor 15` |
| Routenquelle | Verbindungsabfrage via Transitous/MOTIS (echte Fahrt-Polyline); Fallback: manuelle Bahnhofsliste (`--stations`/`--straight-line`) |
| Verbindungsfilter | Zuggattung (`--modes alle/fern/nah` → MOTIS transitModes), Abfahrts-/Ankunftszeit (`--time`/`--arrive`), nur direkt (`--direct`, clientseitig gefiltert: `maxTransfers=0` liefert bei Transitous fälschlich leer, verifiziert 2026-07-11). Interaktiv: Auswahl unter bis zu 5 Verbindungen je Abschnitt. API-Zeiten sind UTC → Anzeige in Systemzeitzone |
| Relais-Auswahl | **Rechnerische Erreichbarkeit von der Strecke** (Sichtkontakt zu ≥ 1 Streckenpunkt im Geländemodell) statt festem Korridor — Nutzerentscheidung 2026-07-12. `--corridor` nur noch als optionales Abstands-Limit; Suchraum 60 km um die Strecke. **Konsistenz-Zusage (Nutzeranforderung 2026-07-13):** Karte, Bericht und CSV zeigen exakt dieselben Relais — auch Grenzbereichs-Relais (nur Beugung, nie Sicht) sind vollwertige, markierte Einträge (graue Marker, Badge, CSV-Spalte `erreichbarkeit`), und das frühere implizite 60-km-Limit ist weg (DB0NU stand mit 64 km Abstand und 460 m Antenne nur in Tooltips) |
| Output | Konsolentabelle + CSV, HTML-Karte (folium/Leaflet), HTML-Bericht, Codeplug-Export |
| Codeplug | AnyTone CPS-CSV (AT-D890UV); Motorola: manuelle Eingabe anhand HTML-Bericht (s. Einschränkung 4) |
| TG9 Lokal | Wird immer als Standard-Eintrag ergänzt (TS2, bei Simplex TS1) — die API listet sie nie, sie ist auf jedem Relais implizit verfügbar (Entscheidung 2026-07-11) |
| Slot 0 | = „keine Slot-Angabe": Normalfall bei Simplex-Repeatern (RX=TX, z. B. DB0RUF 2 m) → Anzeige „1 (Simplex)", Codeplug Slot 1 + DMR MODE 0. Auf **Duplex-Relais ist Slot 0 eine Sysop-Miskonfiguration** (Nutzerentscheidung 2026-07-13, Beispiel DB0TU TG 26231) und **wird komplett verworfen** — taucht in keiner Ausgabe auf |
| Relais ohne TGs | Bleiben in allen Ausgaben sichtbar (vollständiges Lagebild), mit TG9 als Minimum |
| Abdeckungsschätzung | Standard: **Geländemodell** — Sichtlinienprüfung gegen SRTM-Höhendaten (Terrarium-Kacheln, AWS Open Data, Zoom 11 ≈ 50 m Raster, Disk-Cache) mit 4/3-Erdradius, dreistufig Sicht/Grenzbereich(≤30 m Hindernis)/Schatten, inkl. Schatten-Lücken ≥ 5 km. `--no-terrain` = Horizontmodell-Fallback (auch bei Downloadfehler). Alle Online-Relais der Umgebung, nicht nur Korridor-Treffer. Validiert: Mittelrheintal 63 % Schatten, Flachland Nürnberg–Berlin 25 % (inkl. realer Tunnelstrecken) |
| Sprache/Tooling | Python 3.14 (vorhandene venv), `pip` + `pyproject.toml`, ein Repo für alle Tools |
| CLI-Sprache | **Durchgängig Deutsch** (Nutzerwunsch 2026-07-13, „keine Mischung"): Kommandos `bm-bahn`/`bm-auto`/`bm-rad` bzw. `bmtools bahn/auto/rad`, deutsche Flags (`--von`, `--nach`, `--zuggattung`, `--luftlinie`, `--aktualisieren`, `--oeffnen`, `--ausgabe`, …), argparse-Standardtexte übersetzt (ui.argparse_deutsch). Englische Kommandos/Flags bleiben als stille Aliasse gültig (Skript-Kompatibilität) |
| Cache-TTLs | Geräteliste **1 Tag** (vorher 30 min), Profile bewusst bei **12 h** („ändern sich am ehesten", Nutzerentscheidung 2026-07-13), TG-Namen 7 Tage, Höhenkacheln unbegrenzt. `--refresh` (alle Tools) erzwingt frische Daten. Warmer Cache: kompletter Lauf < 1 s |
| HTML-Bericht | jinja2-Template (Autoescaping, war schon folium-Dependency) statt String-Konkatenation; vollständiges HTML5-Dokument mit `<meta charset="utf-8">` und Viewport. Grund: Ohne charset-Angabe riet Samsung Internet die Kodierung falsch → Zeichensalat bei Umlauten/Symbolen (gemeldet 2026-07-13); Viewport + scrollende Tabellen-Wrapper für Smartphone-Lesbarkeit |
| Kartenkacheln | `tile.openstreetmap.de` (FOSSGIS) statt `tile.openstreetmap.org`: Die OSMF-Server verlangen einen Referer (osm.wiki/Blocked), den eine verschickte, per file:// geöffnete karte.html nie sendet — Empfänger sahen „Access Blocked" (gemeldet 2026-07-13). Kein JS-Workaround möglich (Referer = forbidden header; Leaflets `referrerPolicy` wirkt nur auf gehosteten Seiten). Carto-CDN als umschaltbare Ausweich-Ebene |

## 4. Architektur

```
BrandmeisterTools/
├── pyproject.toml            # CLI-Entrypoints: bmtools (Dispatcher), bm-rail
├── bmtools/
│   ├── cli.py                # Dach-Kommando: Menü + Subcommand-Dispatch
│   ├── bm_api/               # Gemeinsamer BM-Client (alle Tools nutzen ihn)
│   │   ├── client.py         # HTTP, Retry, Rate-Limit
│   │   ├── models.py         # Device, Profile, TalkgroupSub (dataclasses)
│   │   └── cache.py          # Disk-Cache mit TTL
│   ├── routelib/             # transport-agnostischer Kern (seit R1, 2026-07-13)
│   │   ├── model.py          # Route, Waypoint (=Station), decode_polyline
│   │   ├── corridor.py       # Distanz Punkt→Polyline (segmentweise, lokal projiziert)
│   │   ├── coverage.py       # Erreichbarkeit/Abdeckung (Gelände- + Horizontmodell)
│   │   ├── terrain.py        # SRTM-Höhenkacheln (Terrarium, Disk-Cache)
│   │   ├── viewshed_raster.py# Sichtfeld-Rasterisierung (Prozess-Pool-tauglich)
│   │   ├── report.py         # Tabelle (rich) + CSV
│   │   ├── report_html.py    # HTML-Bericht (Copy&Paste für manuelle CPS-Eingabe)
│   │   ├── mapview.py        # folium-HTML-Karte (Texte/Icons parametrisiert)
│   │   └── codeplug/         # anytone.py (AT-D890UV)
│   ├── rail/                 # Tool 1: nur noch Bahn-Spezifisches
│   │   ├── cli.py            # Argument-Parsing, Ablaufsteuerung
│   │   └── route.py          # Transitous-Verbindungssuche + Fallback-Interpolation
│   └── road/                 # Tool 2/3 (geplant, s. Abschnitt 7)
└── tests/
```

Abhängigkeiten: `httpx`, `rich`, `folium`, `platformdirs` (Cache-Pfad).
Bewusst **kein** shapely/geopandas — segmentweise Haversine-Distanz reicht und
hält das Tool schlank.

### Datenfluss `bm-rail`

1. **Route:** Journey Koblenz→Nürnberg von transport.rest holen, Polyline dekodieren.
2. **Vorfilter:** Alle Devices laden, auf Bounding-Box der Route + Puffer reduzieren,
   Hotspots ausfiltern.
3. **Korridor:** Distanz jedes Relais zur Polyline berechnen, ≤ Korridor behalten,
   nach Streckenkilometer sortieren.
4. **Anreicherung:** Pro Treffer `profile` abrufen (gecacht) → TS1/TS2-TGs mit
   Kennzeichnung `statisch` / `zeitgeschaltet` / `cluster`.
5. **Ausgabe:** Tabelle, CSV, HTML-Karte, Codeplug-Dateien.

## 5. Meilensteine

| # | Inhalt | Status (2026-07-11) |
|---|---|---|
| M0 | Projektgerüst | ✅ `bm-rail` als CLI-Entrypoint, Paketstruktur steht |
| M1 | BM-API-Client + Repeater-Filter + Cache | ✅ 2.834 Repeater aus 32.663 Geräten getrennt, Stichproben plausibel |
| M2 | Routenermittlung + Korridorfilter | ✅ ICE 27 Koblenz–Nürnberg (354 km, 6.118 Punkte), 16 Relais im 15-km-Korridor |
| M3 | TG-Anreicherung + Tabelle/CSV | ✅ inkl. Zeitschaltung („Fr 18:00–19:30", je Wochentag ein API-Datensatz, wird gebündelt) und Cluster-Auflösung |
| M4 | HTML-Karte + HTML-Bericht | ✅ karte.html (folium) + bericht.html mit fertigen Kanaltabellen und TG-Namen |
| M5 | Codeplug-Export AnyTone | ⚠️ implementiert im **D878UV-Format (Arbeitsannahme)**; wird angepasst, sobald Beispiel-Export aus der D890UV-CPS vorliegt. Importtest steht aus. |
| M6 | Abdeckungsschätzung mit Geländemodell | ✅ SRTM-Sichtlinienmodell, Abnahme: Mittelrheintal als Schatten erkannt (63 %), Flachlandwerte stabil |

Reihenfolge strikt sequenziell; jedes M endet mit einem konkreten Testlauf, kein Try&Error.

## 6. Offene Punkte

- [x] Semantik `timedSubscriptions` geklärt: `data` mit Wochentags-Flags, `start`/`stop` in Tagessekunden, `startDate`/`endDate` als Unix-Gültigkeitszeitraum. Ein Datensatz pro Wochentag.
- [x] transport.rest dauerhaft 503 → ersetzt durch Transitous (api.transitous.org)
- [ ] AnyTone AT-D890UV: Beispiel-Export (Channel/TalkGroups/Zone-CSV) aus der Nutzer-CPS einpflegen, Header/Defaults in `bmtools/rail/codeplug/anytone.py` anpassen, Importtest (M5)
- [x] Zeitzone der Zeitschaltungen = **Lokalzeit** (verifiziert 2026-07-11 am Frankenrundspruch, Fr 19:30: DK0WUE-Zeitfenster-Lücke endet exakt 19:30; UTC-Lesart ergäbe sinnlose Zeiten). Offizielle Doku existiert nicht (Seite leer).
- [ ] Spätere Tools konkretisieren (Ideen: Lastheard-Monitor via MQTT/WebSocket, TG-Aktivitätsstatistik)
- [ ] Google-Link mit per Maus verschobener Route (Drag-Via) an einem echten
      Link verifizieren — Heuristik ist implementiert und unit-getestet,
      ein echter Beispiel-Link steht noch aus
- [ ] Komoot-API-Geometrie gegen einen echten GPX-Export aus der Nutzer-CPS
      der Komoot-App vergleichen (Kreuzvalidierung Komoot-Lauf vs. Lauf mit
      selbst erzeugtem GPX war identisch; ein Original-Export fehlt noch)

---

## 7. Umsetzungsplan: Tool 2/3 — `bm-car` & `bm-bike` (Stand: 2026-07-12, Plan)

### 7.1 Ziel

Auto- und Rad-Variante von `bm-rail`: Der Nutzer kopiert den Link einer
Google-Maps-Route (Auto oder Rad) — oder bei `bm-bike` einer **Komoot-Tour** —
fügt ihn ins Tool ein, und erhält dieselben Ausgaben wie bei `bm-rail` —
erreichbare Relais, Abdeckung im Geländemodell, Bericht, Karte, CSV,
AnyTone-Codeplug. Alternativ Start/Ziel/Via per Texteingabe oder eine
GPX-Datei (`--gpx`, deckt Komoot-Export und andere Portale ab).

### 7.2 Datenlage (Stand 2026-07-12)

| Bedarf | Quelle | Status |
|---|---|---|
| Straßenrouting Auto + Rad, keyless, Via-Punkte | FOSSGIS-OSRM `routing.openstreetmap.de/routed-car\|routed-bike/route/v1/...` → Polyline (Präzision 5), Distanz, Dauer | ✅ getestet 2026-07-12: Auto Koblenz→Nürnberg 342 km; Rad-Langstrecke Feucht→Bendorf 448 km; Auto mit Via-Punkt (3 Wegpunkte → 2 Legs) ok |
| Alternative/Fallback-Router | Transitous `plan?directModes=CAR` (gleiche API wie bm-rail) | ✅ getestet 2026-07-12 (CAR); BIKE und Via-Punkte ungetestet |
| Google-Link: Wegpunkte + Verkehrsmittel | Lang-URL: Pfadsegmente `/dir/<wp1>/<wp2>/@…` + `data=`-Blob (`!1d<lon>!2d<lat>` je Wegpunkt, `!3e0`=Auto/`!3e1`=Rad/`!3e2`=Fuß/`!3e3`=ÖPNV) | ✅ verifiziert 2026-07-12 an echten Nutzer-Links (Auto + Rad, Feucht→Bendorf): Koordinaten und Modus exakt wie angenommen |
| Google-Link: offizielles Format (`?api=1&origin=…`) | dokumentierte Maps-URLs-API | Optional: echte Teilen-Links nutzen das Lang-Format (verifiziert); Parser nimmt `api=1` trotzdem mit (trivial) |
| Kurzlink-Expansion | `maps.app.goo.gl/…` per HTTP-Redirect auflösen | ✅ verifiziert 2026-07-12: ein einziger 302 mit Ziel-URL im Location-Header, keine Consent-Wall (curl ohne Cookies, bmtools-User-Agent) |
| Geocoding freier Ortsnamen (ohne Link) | Transitous `/geocode` ohne `type=STOP`, alternativ Photon (photon.komoot.io, keyless) | ⚠️ Auswahl in M-R0 |
| Komoot-Tour: Geometrie | URL-Formen `…/tour/<id>` und `…/smarttour/e<id>/…` (`e`-Präfix abschneiden) → `api.komoot.de/v007/tours/<id>` (Name, Sportart, Distanz, Status) + `…/coordinates` (lat/lng/alt je Punkt); bei privaten Touren `?share_token=…` aus dem Teilen-Link an beide Calls anhängen | ✅ verifiziert 2026-07-12/13 an echten Nutzer-Links, keyless: öffentliche Smarttour („Höhlen- und Schluchtensteig", 12,3 km, 462 Punkte, hike) **und** private Tour mit share_token („Von Kühnhofen nach Feucht-Moosbach", 27,6 km, 635 Punkte, touringbicycle; ohne Token 403). Zusätzlich steckt das komplette Koordinaten-Array im HTML der Tour-Seite (Fallback) |
| GPX-Import (Fallback für alles) | lokale Datei, Parsing per stdlib `xml.etree` (`<trkpt lat lon>`, Fallback `<rtept>`) | ✅ kein API-Risiko; Komoot bietet GPX-Export in jeder Tour an (App/Web mit Login — der API-Endpunkt `tours/<id>.gpx` liefert auch mit share_token 403, verifiziert 2026-07-13) |

**Klare Ansagen (Grenzen des Ansatzes):**

1. **Der Google-Link enthält keine Routen-Geometrie**, nur Wegpunkte
   (Start, Ziel, Vias inkl. per Drag gesetzter Punkte). Die Route wird von
   Google beim Öffnen jeweils neu berechnet. Das Tool routet daher selbst
   (OSRM auf OSM-Daten) zwischen den Wegpunkten des Links. Ergebnis kann von
   Googles Verlauf abweichen (anderes Kartenmaterial/Gewichtung); übernommene
   Drag-Via-Punkte ziehen die Route auf Googles Verlauf. Die exakte
   Google-Route gäbe es nur über die Google Directions API (API-Key +
   Abrechnung) — bewusst nicht (Projektprinzip: keyless).
2. Der `data=`-Blob ist **nicht dokumentiert** (reverse-engineered) und kann
   sich ändern. Parser defensiv: schlägt die Blob-Auswertung fehl, Fallback
   auf die Pfad-Wegpunkte + Geocoding. Für Funkschatten-Bewertung reicht das.
3. Kurzlink-Expansion braucht einen Request an Google; scheitert sie
   (Consent-Wall), klare Fehlermeldung: „Bitte Route im Browser öffnen und
   die vollständige URL aus der Adresszeile kopieren."
4. ÖPNV-Links (`!3e3` / `travelmode=transit`) → Fehlermeldung mit Verweis
   auf `bm-rail`.
5. FOSSGIS-OSRM ist Community-Infrastruktur ohne SLA (wie Transitous).
   Fallback-Kette: OSRM → Transitous `directModes` → Luftlinie (mit Warnung).
6. Antennenhöhe: `MOBILE_HEIGHT_M = 2.0` bleibt für Auto (Dach-/Magnetfuß)
   und Rad (Handfunke) unverändert — die Abweichung ist gegenüber der
   SRTM-Rasterauflösung (~50 m) vernachlässigbar.
7. **Komoot ist der bessere Fall als Google:** Ein Komoot-Link zeigt auf eine
   **gespeicherte Tour mit echter Geometrie** — kein Nachrouten nötig, die
   Strecke ist exakt die geplante, inkl. Höhen je Punkt. Für **öffentliche
   Touren keyless verifiziert** (2026-07-12, s. 7.2); private fremde Touren
   liefern 403. Die API ist inoffiziell (v007, reverse-engineered) und kann
   sich ändern → Parser defensiv, zwei Fallback-Stufen: (a) Koordinaten-JSON
   aus dem HTML der Tour-Seite (dort eingebettet, verifiziert), (b) **GPX-
   Export der Tour als garantierter Weg** (jede Komoot-Tour hat einen
   Export-Button): `bm-bike --gpx tour.gpx`. Keine Login-/Passwort-Abfrage
   im Tool — bewusste Entscheidung, keine Credentials verarbeiten.
8. Private Komoot-Tour ohne share_token → klare Fehlermeldung: „Tour in
   Komoot auf ‚Mit Link teilen' stellen (Link enthält dann share_token)
   oder GPX exportieren und mit --gpx übergeben."

### 7.3 Architektur

Die Pipeline ab „Route steht" ist bereits transport-agnostisch (arbeitet nur
auf `Route.points`/`stations`). Rail-spezifisch sind nur Routenermittlung
(Transitous-Verbindungssuche) und Formulierungen („Bahnstrecke").

```
bmtools/
├── routelib/                 # NEU: gemeinsamer Kern (aus rail/ verschoben)
│   ├── model.py              # Route, Waypoint (= bisheriges Station), decode_polyline
│   ├── corridor.py, coverage.py, terrain.py, viewshed_raster.py
│   ├── mapview.py, report.py, report_html.py   # Texte parametrisiert
│   └── codeplug/anytone.py                     # (route_kind: "Bahnstrecke"/"Autoroute"/"Radroute")
├── rail/                     # behält route.py (Transitous) + cli.py
└── road/                     # NEU: gemeinsame Implementierung Auto/Rad
    ├── gmaps_link.py         # Kurzlink-Expansion, Lang-URL/api=1-Parser, Modus-Erkennung
    ├── komoot.py             # Tour-Link-Parser (id + share_token) + Geometrie-Abruf
    ├── gpx.py                # GPX-Import (stdlib xml.etree, kein neues Paket)
    ├── routing.py            # OSRM-Client (car/bike), Fallbacks
    └── cli.py                # ein Ablauf, Profil als Parameter
```

CLI: Entrypoints `bm-car` und `bm-bike` (gleiche `main()` mit Profil-Parameter),
im Dispatcher als `bmtools car` / `bmtools bike` registriert. Widerspricht das
Verkehrsmittel im Link dem aufgerufenen Tool (Rad-Link in `bm-car`), wird
nachgefragt (interaktiv) bzw. der Link gewinnt mit Warnung (nicht-interaktiv).

Interaktiver Assistent: erste Frage „Routen-Link einfügen (Google Maps oder
Komoot; leer = manuelle Eingabe)" — die Quelle wird an der Domain erkannt.
Google-Link: erkannte Wegpunkte + Verkehrsmittel anzeigen, bestätigen, dann
OSRM-Routing. Komoot-Link: Tour-Geometrie direkt laden (kein Routing), Name +
Länge der Tour zur Bestätigung anzeigen; Sportart der Tour (Rad/MTB/Wandern)
nur als Hinweis. Ohne Link: Start/Ziel/Via als Text mit Kandidaten-Auswahl
(wie `bm-rail`). Zusätzlich `--gpx DATEI` als dritter Eingabeweg. Ausgaben nach `out/<start>-<ziel>/` wie gehabt; `--corridor`,
`--no-terrain`, `--open`, `--out` identisch.

### 7.4 Meilensteine (sequenziell, je mit konkretem Testlauf)

| # | Inhalt | Abnahme |
|---|---|---|
| R0 | Datenlage verifizieren — **erledigt bis auf Restpunkte** (2026-07-12/13, echte Nutzer-Links): Google Kurzlink-Expansion ✅, data-Blob Auto+Rad ✅, Komoot öffentlich ✅ **und privat mit share_token ✅**, OSRM Via + Rad-Langstrecke ✅. **Rest (nicht blockierend, in R2 miterledigen):** Geocoder festlegen (Transitous vs. Photon); Google-Link mit Drag-Via prüfen; Komoot-Geometrie gegen GPX-Referenz-Export vergleichen | Entscheidungstabelle in 7.2 aktualisiert; alle ⚠️ aufgelöst |
| R1 | Refactor `bmtools/routelib/` (Verschieben + Texte parametrisieren), `rail` importiert daraus | ✅ 2026-07-13. Abnahme: Luftlinien-Lauf Koblenz→Nürnberg vor/nach Refactor — relais.csv, anytone/ und bericht.html (ohne Zeitstempel) byte-identisch, karte.html identisch bis auf folium-Zufalls-IDs. `rail/` enthält nur noch cli.py + route.py; Karte-Texte/Icons parametrisiert (`route_label`, `waypoint_icon`) |
| R2 | `gmaps_link.py`, `komoot.py` und `gpx.py` mit Unit-Tests (echte URLs/Dateien aus R0 als Fixtures, inkl. Fehlerfälle: ÖPNV-Link, kaputter Blob, Consent-Wall, private Tour ohne share_token, leeres/kaputtes GPX) | ✅ 2026-07-13: 24 Tests grün (offline, httpx-MockTransport) + Live-Smoke-Test aller vier echten Links (Google Auto/Rad expandiert+geparst, Komoot Smarttour+privat abgerufen). ⚠️ GPX-Referenzvergleich offen: braucht einen Nutzer-Export aus der Komoot-App (API-`.gpx` verlangt Login) |
| R3 | `routing.py`: OSRM-Route über alle Wegpunkte, Fallback-Kette OSRM → Transitous (`maxDirectTime=86400`, sonst filtert das Default-Limit lange Abschnitte) → Luftlinie mit Warnung, `Route`-Objekt (Komoot/GPX umgehen das Routing via `route_from_track`) | Implementiert 2026-07-13, 6 neue Tests (30 gesamt grün). Live-Lauf der echten Links: Auto 358 km/3:28 h (5.001 Punkte), Rad 448 km/16:24 h (14.956 Punkte), beide Komoot-Touren als Track. ✅ Abnahme 2026-07-13: Nutzer hat Verlauf und Distanzen gegen Google verglichen — passt |
| R4 | `road/cli.py`: Assistent + Flags (`--gpx`), volle Pipeline (Erreichbarkeit, Bericht, Karte, CSV, AnyTone), Dispatcher + Entrypoints; Pipeline nach `routelib/pipeline.py` extrahiert (rail-Regression erneut bestanden, nur `last_seen` frischer); Geocoder-Entscheid: Transitous ohne type-Filter (hausnummerngenau verifiziert) | ✅ 2026-07-13, drei komplette Läufe: `bm-car` Google-Kurzlink (358 km, 22 Relais, Schatten 19 %), `bm-bike` Komoot-Link (27,6 km, 5 Relais), `bm-bike --gpx` — Komoot- und GPX-Lauf byte-identisch (Kreuzvalidierung der Eingabewege) |
| R5 | README + Projektplan aktualisieren | ✅ 2026-07-13: README-Abschnitt bm-car/bm-bike mit Link-Workflow und klaren Ansagen (keine Geometrie im Google-Link, Komoot-share_token, GPX als garantierter Weg, ÖPNV → bm-rail) |
