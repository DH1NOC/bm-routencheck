# BrandmeisterTools

Python-Tools rund um das Brandmeister-DMR-Netzwerk.

## bm-bahn — DMR-Relais entlang einer Bahnstrecke

Findet alle Brandmeister-Relais im Korridor einer Bahnverbindung und liefert
Rufzeichen, Frequenzen, Colorcode und die Talkgroups in TS1/TS2 — statisch,
zeitgeschaltet (mit Zeitfenster, Lokalzeit) und Cluster.

```bash
# Installation (einmalig, in der venv)
pip install -e .

# Gemeinsamer Einstieg für alle Tools (Menü bzw. Subcommands):
bmtools            # Menü
bmtools bahn       # = bm-bahn; Argumente werden durchgereicht

# Am einfachsten: ohne Argumente starten -> interaktiver Assistent.
# Auswahllisten (Zuggattung, mehrdeutige Bahnhöfe, Verbindungen) werden
# mit den Pfeiltasten (↑/↓, alternativ j/k) navigiert und mit Enter
# bestätigt; am Ende öffnen sich Bericht + Karte im Browser.
bm-bahn

# Oder direkt mit Flags (für Skripte/Wiederholläufe):
bm-bahn --von "Koblenz Hbf" --nach "Nürnberg Hbf" --oeffnen
bm-bahn --von Hamburg --nach München --zuggattung fern --direkt
bm-bahn --von Koblenz --nach Nürnberg --zeit "2026-07-14 08:00"
bm-bahn --von Koblenz --nach Nürnberg --zeit "2026-07-14 17:30" --ankunft
bm-bahn --bahnhoefe "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --luftlinie
```

Die englischen Kommandos und Flags (`bm-rail`, `bmtools rail`, `--from`,
`--to`, …) bleiben als Aliasse gültig.

Die Zuggattung beeinflusst die Route real: Hamburg–München fährt der
Fernverkehr z. B. via Berlin–Erfurt oder via Würzburg, der Nahverkehr eine
ganz andere Kette — entsprechend ändern sich die gefundenen Relais.
Im nicht-interaktiven Modus wird die erste passende Verbindung genommen.

Im PyCharm-Terminal ist die venv aktiv, dort genügt `bm-bahn`; außerhalb:
`.venv/bin/bm-bahn`.

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
Key, nur Lesezugriff) und [Transitous](https://transitous.org) für die
Streckengeometrie.

**Caching:** Alle Brandmeister-Antworten liegen im lokalen Disk-Cache —
Geräteliste 1 Tag, Talkgroup-Profile 12 h (ändern sich am ehesten),
TG-Namen 7 Tage, Höhenkacheln unbegrenzt. Wiederholte Läufe (gleiche oder andere Strecke)
laufen damit in Sekunden und ohne API-Zugriffe. `--aktualisieren` (bei
allen Tools) erzwingt frische Brandmeister-Daten.

## bm-auto & bm-rad — DMR-Relais entlang einer Auto- oder Radroute

Gleiche Auswertung und gleiche Ausgaben wie bm-bahn, aber für Straße und
Rad. Der einfachste Weg: Route in Google Maps oder Komoot planen, Link
kopieren, ins Tool einfügen.

```bash
# Interaktiver Assistent (fragt nach Link oder Start/Ziel):
bm-auto
bm-rad

# Google-Maps-Link (Kurzlink vom Teilen-Button genügt):
bm-auto "https://maps.app.goo.gl/…"

# Komoot-Tour (bei privaten Touren den „Mit Link teilen“-Link nehmen,
# er enthält den nötigen share_token):
bm-rad "https://www.komoot.com/tour/…?share_token=…"

# GPX-Datei (z. B. Komoot-Export — funktioniert immer):
bm-rad --gpx tour.gpx

# Oder klassisch mit Orts-/Adressangaben (hausnummerngenau):
bm-auto --von "Winkelhaider Str. 4a, Feucht" --nach "Bendorf" --oeffnen
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
- ÖPNV-Links lehnt das Tool ab und verweist auf `bm-bahn`.
- Widerspricht das Verkehrsmittel im Link dem Tool (Rad-Link in
  `bm-auto`), wird interaktiv nachgefragt; in Skripten gewinnt der Link.

Ausgaben wie bei bm-bahn in `out/<route>/`: `bericht.html`, `relais.csv`,
`karte.html`, `anytone/*.CSV`.

## Projektstruktur

- `bmtools/bm_api/` — wiederverwendbarer Brandmeister-API-Client (Cache, Modelle)
- `bmtools/routelib/` — gemeinsamer Kern: Erreichbarkeit (Geländemodell),
  Berichte, Karte, Codeplug-Export, Pipeline
- `bmtools/rail/` — bm-bahn (Bahnverbindungen via Transitous)
- `bmtools/road/` — bm-auto/bm-rad (Google-Maps-/Komoot-Link, GPX,
  OSRM-Routing, Geocoding)
- `PROJEKTPLAN.md` — Plan, Entscheidungen, offene Punkte
