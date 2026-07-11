# BrandmeisterTools — Projektplan

Stand: 2026-07-11

## 1. Ziel

Sammlung von Python-Tools rund um das Brandmeister-Netzwerk (DMR & Tetra).
Gemeinsame Basis: ein wiederverwendbarer Brandmeister-API-Client.

**Tool 1 — `bm-rail`:** Findet alle DMR-Relais entlang einer Bahnstrecke
(z. B. ICE Koblenz–Nürnberg) und liefert pro Relais: Rufzeichen, RX/TX-Frequenz,
Colorcode, Standort, Entfernung zur Strecke sowie die Talkgroups in TS1/TS2 —
statisch, zeitgeschaltet und per Cluster.

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
| Korridor | Fester Radius um die Streckengeometrie, konfigurierbar, Default 15 km |
| Output | Konsolentabelle + CSV, HTML-Karte (folium/Leaflet), HTML-Bericht, Codeplug-Export |
| Codeplug | AnyTone CPS-CSV (AT-D890UV); Motorola: manuelle Eingabe anhand HTML-Bericht (s. Einschränkung 4) |
| TG9 Lokal | Wird immer als Standard-Eintrag ergänzt (TS2, bei Simplex TS1) — die API listet sie nie, sie ist auf jedem Relais implizit verfügbar (Entscheidung 2026-07-11) |
| Slot 0 | Simplex-Repeater (RX=TX, z. B. DB0RUF 2 m) melden ihre TGs mit `slot: 0` → Anzeige unter TS1, Codeplug: Slot 1 + DMR MODE 0 (Simplex) |
| Relais ohne TGs | Bleiben in allen Ausgaben sichtbar (vollständiges Lagebild), mit TG9 als Minimum |
| Abdeckungsschätzung | Standard: **Geländemodell** — Sichtlinienprüfung gegen SRTM-Höhendaten (Terrarium-Kacheln, AWS Open Data, Zoom 11 ≈ 50 m Raster, Disk-Cache) mit 4/3-Erdradius, dreistufig Sicht/Grenzbereich(≤30 m Hindernis)/Schatten, inkl. Schatten-Lücken ≥ 5 km. `--no-terrain` = Horizontmodell-Fallback (auch bei Downloadfehler). Alle Online-Relais der Umgebung, nicht nur Korridor-Treffer. Validiert: Mittelrheintal 63 % Schatten, Flachland Nürnberg–Berlin 25 % (inkl. realer Tunnelstrecken) |
| Sprache/Tooling | Python 3.14 (vorhandene venv), `pip` + `pyproject.toml`, ein Repo für alle Tools |

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
│   ├── rail/                 # Tool 1
│   │   ├── cli.py            # Argument-Parsing, Ablaufsteuerung
│   │   ├── route.py          # transport.rest-Abfrage + Fallback-Interpolation
│   │   ├── corridor.py       # Distanz Punkt→Polyline (Haversine, segmentweise)
│   │   ├── report.py         # Tabelle (rich) + CSV
│   │   ├── report_html.py    # HTML-Bericht (Copy&Paste für manuelle CPS-Eingabe)
│   │   ├── mapview.py        # folium-HTML-Karte
│   │   └── codeplug/         # anytone.py (AT-D890UV)
│   └── ...                   # spätere Tools (z. B. MQTT/Lastheard-Monitor)
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
