# BrandmeisterTools — Projektplan

Stand: 2026-07-13

## 1. Status

Die drei Tools `bm-bahn`, `bm-auto` und `bm-rad` sind fertig und abgenommen
(gemeinsamer Kern in `bmtools/routelib/`, Nutzung siehe [README](README.md)).
Dieses Dokument hält nur noch fest, was für die Weiterarbeit gebraucht wird:
offene Punkte, verbindliche Festlegungen und die Eigenheiten der externen
Datenquellen. Die Abnahmeprotokolle der erledigten Meilensteine (M0–M6,
R0–R5) sind in der Git-Historie dieses Dokuments nachlesbar.

## 2. Offene Punkte

- [ ] **M5 — AnyTone AT-D890UV (ruht):** Der Codeplug-Export in
      `bmtools/routelib/codeplug/anytone.py` nutzt das D878UV-Spaltenlayout
      als Arbeitsannahme; das CSV-Layout des D890UV ist nicht gesichert
      dokumentiert. Wartet auf einen Beispiel-Export (Channel/TalkGroups/
      Zone-CSV) aus der Nutzer-CPS — kein Blindformat. Danach Header/Defaults
      anpassen und Importtest in der CPS.
- [ ] Google-Link mit per Maus verschobener Route (Drag-Via) an einem echten
      Link verifizieren — Heuristik ist implementiert und unit-getestet,
      ein echter Beispiel-Link steht noch aus.
- [ ] Komoot-API-Geometrie gegen einen Original-GPX-Export aus der
      Komoot-App vergleichen (Kreuzvalidierung Komoot-Lauf vs. Lauf mit
      selbst erzeugtem GPX war byte-identisch; ein Original-Export fehlt
      noch — der API-Endpunkt `tours/<id>.gpx` liefert auch mit share_token
      403, verifiziert 2026-07-13).
- [ ] Spätere Tools konkretisieren (Ideen: Lastheard-Monitor via
      MQTT/WebSocket, TG-Aktivitätsstatistik).

## 3. Verbindliche Festlegungen

Projektprinzipien:

| Prinzip | Bedeutung |
|---|---|
| Keyless | Nur Dienste ohne API-Key/Anmeldung; keine Credentials im Tool verarbeiten (bewusste Entscheidung, z. B. kein Komoot-Login) |
| Kein Try&Error | Jede Erweiterung endet mit einem konkreten, abgenommenen Testlauf |
| CLI durchgängig Deutsch | Kommandos `bm-bahn`/`bm-auto`/`bm-rad`, deutsche Flags; englische Originale bleiben als stille Aliasse gültig (Skript-Kompatibilität); argparse-Standardtexte via `ui.argparse_deutsch()` |
| Schlanke Abhängigkeiten | Bewusst kein shapely/geopandas — segmentweise Haversine-Distanz reicht |
| Konsistenz der Ausgaben | Karte, Bericht und CSV zeigen exakt dieselben Relais; Grenzbereichs-Relais sind vollwertige, markierte Einträge (graue Marker, Badge, CSV-Spalte `erreichbarkeit`) |

Fachliche Regeln (dürfen bei Änderungen nicht regressieren):

| Regel | Festlegung |
|---|---|
| Relais-Auswahl | Rechnerische Erreichbarkeit von der Strecke (Sichtkontakt zu ≥ 1 Streckenpunkt im Geländemodell) statt festem Korridor; `--korridor` nur als optionales Abstands-Limit; kein implizites Distanz-Limit |
| Frequenz-Sicht | Alle Ausgaben aus Sicht des Funkgeräts (RX = Relais-Ausgabe) |
| TG9 Lokal | Wird immer ergänzt (TS2, bei Simplex TS1) — die API listet sie nie |
| Slot 0 | = „keine Slot-Angabe": bei Simplex-Repeatern (RX=TX) Anzeige „1 (Simplex)", Codeplug Slot 1 + DMR MODE 0. Auf Duplex-Relais ist Slot 0 eine Sysop-Miskonfiguration und wird komplett verworfen |
| Relais ohne TGs | Bleiben in allen Ausgaben sichtbar (vollständiges Lagebild), mit TG9 als Minimum |
| Geländemodell | Sichtlinienprüfung mit 4/3-Erdradius, dreistufig Sicht / Grenzbereich (≤ 30 m Hindernis) / Schatten, Schatten-Lücken ≥ 5 km; Antennenhöhe mobil 2,0 m; `--ohne-gelaende` = Horizontmodell-Fallback (auch bei Downloadfehler) |
| Cache-TTLs | Geräteliste 1 Tag, Profile 12 h („ändern sich am ehesten"), TG-Namen 7 Tage, Höhenkacheln unbegrenzt; `--aktualisieren` erzwingt frische Daten |
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
