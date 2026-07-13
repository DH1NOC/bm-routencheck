# BrandmeisterTools

Python-Tools rund um das Brandmeister-DMR-Netzwerk.

## bm-rail — DMR-Relais entlang einer Bahnstrecke

Findet alle Brandmeister-Relais im Korridor einer Bahnverbindung und liefert
Rufzeichen, Frequenzen, Colorcode und die Talkgroups in TS1/TS2 — statisch,
zeitgeschaltet (mit Zeitfenster, Lokalzeit) und Cluster.

```bash
# Installation (einmalig, in der venv)
pip install -e .

# Gemeinsamer Einstieg für alle Tools (Menü bzw. Subcommands):
bmtools            # Menü
bmtools rail       # = bm-rail; Argumente werden durchgereicht

# Am einfachsten: ohne Argumente starten -> interaktiver Assistent.
# Auswahllisten (Zuggattung, mehrdeutige Bahnhöfe, Verbindungen) werden
# mit den Pfeiltasten (↑/↓, alternativ j/k) navigiert und mit Enter
# bestätigt; am Ende öffnen sich Bericht + Karte im Browser.
bm-rail

# Oder direkt mit Flags (für Skripte/Wiederholläufe):
bm-rail --from "Koblenz Hbf" --to "Nürnberg Hbf" --open
bm-rail --from Hamburg --to München --modes fern --direct
bm-rail --from Koblenz --to Nürnberg --time "2026-07-14 08:00"
bm-rail --from Koblenz --to Nürnberg --time "2026-07-14 17:30" --arrive
bm-rail --stations "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --straight-line
```

Die Zuggattung beeinflusst die Route real: Hamburg–München fährt der
Fernverkehr z. B. via Berlin–Erfurt oder via Würzburg, der Nahverkehr eine
ganz andere Kette — entsprechend ändern sich die gefundenen Relais.
Im nicht-interaktiven Modus wird die erste passende Verbindung genommen.

Im PyCharm-Terminal ist die venv aktiv, dort genügt `bm-rail`; außerhalb:
`.venv/bin/bm-rail`.

Ausgaben in `out/<start>-<ziel>/`:

| Datei | Inhalt |
|---|---|
| `bericht.html` | Bericht mit fertigen Kanaltabellen je Relais (für manuelle CPS-Eingabe, z. B. Motorola) |
| `relais.csv` | Alle Daten maschinenlesbar (Semikolon-getrennt) |
| `karte.html` | Interaktive Karte: Strecke + Relais |
| `anytone/*.CSV` | Channel/TalkGroups/Zone für AnyTone-CPS-Import |

Frequenzangaben in den Ausgaben sind aus Sicht des Funkgeräts
(RX = Relais-Ausgabe). TG9 „Lokal" wird immer ergänzt, auch wenn die API sie
nicht listet.

Aufgenommen wird jedes Relais, das von mindestens einem Streckenpunkt aus
**rechnerisch erreichbar** ist (Sichtlinien-Geländemodell) — egal wie weit es
von der Trasse entfernt steht. `--corridor KM` begrenzt optional zusätzlich
den maximalen Streckenabstand.

**Hinweis:** Der AnyTone-Export nutzt derzeit das D878UV-Spaltenlayout als
Arbeitsannahme; die Anpassung auf das AT-D890UV steht aus (siehe
`PROJEKTPLAN.md`, M5).

Datenquellen: [Brandmeister-API](https://api.brandmeister.network/v2/) (ohne
Key, nur Lesezugriff, Antworten werden lokal gecacht) und
[Transitous](https://transitous.org) für die Streckengeometrie.

## bm-car & bm-bike — DMR-Relais entlang einer Auto- oder Radroute

Gleiche Auswertung und gleiche Ausgaben wie bm-rail, aber für Straße und
Rad. Der einfachste Weg: Route in Google Maps oder Komoot planen, Link
kopieren, ins Tool einfügen.

```bash
# Interaktiver Assistent (fragt nach Link oder Start/Ziel):
bm-car
bm-bike

# Google-Maps-Link (Kurzlink vom Teilen-Button genügt):
bm-car "https://maps.app.goo.gl/…"

# Komoot-Tour (bei privaten Touren den „Mit Link teilen“-Link nehmen,
# er enthält den nötigen share_token):
bm-bike "https://www.komoot.com/tour/…?share_token=…"

# GPX-Datei (z. B. Komoot-Export — funktioniert immer):
bm-bike --gpx tour.gpx

# Oder klassisch mit Orts-/Adressangaben (hausnummerngenau):
bm-car --from "Winkelhaider Str. 4a, Feucht" --to "Bendorf" --open
```

Was dabei zu wissen ist (klare Ansagen):

- **Ein Google-Maps-Link enthält keine Routen-Geometrie**, nur die
  Wegpunkte. Das Tool routet daher selbst (OSRM auf OpenStreetMap-Daten,
  [FOSSGIS-Server](https://routing.openstreetmap.de)) — der Verlauf kann
  von Googles Vorschlag leicht abweichen. Per Maus verschobene
  Routenpunkte stehen als Via-Punkte im Link und werden übernommen.
- **Ein Komoot-Link ist der bessere Fall:** Er zeigt auf eine
  gespeicherte Tour, deren exakte Geometrie übernommen wird — kein
  Nachrouten. Private Touren brauchen den Teilen-Link; klappt der Abruf
  nicht, ist der GPX-Export der Tour der garantierte Weg (`--gpx`).
- ÖPNV-Links lehnt das Tool ab und verweist auf `bm-rail`.
- Widerspricht das Verkehrsmittel im Link dem Tool (Rad-Link in
  `bm-car`), wird interaktiv nachgefragt; in Skripten gewinnt der Link.

Ausgaben wie bei bm-rail in `out/<route>/`: `bericht.html`, `relais.csv`,
`karte.html`, `anytone/*.CSV`.

## Projektstruktur

- `bmtools/bm_api/` — wiederverwendbarer Brandmeister-API-Client (Cache, Modelle)
- `bmtools/routelib/` — gemeinsamer Kern: Erreichbarkeit (Geländemodell),
  Berichte, Karte, Codeplug-Export, Pipeline
- `bmtools/rail/` — bm-rail (Bahnverbindungen via Transitous)
- `bmtools/road/` — bm-car/bm-bike (Google-Maps-/Komoot-Link, GPX,
  OSRM-Routing, Geocoding)
- `PROJEKTPLAN.md` — Plan, Entscheidungen, offene Punkte
