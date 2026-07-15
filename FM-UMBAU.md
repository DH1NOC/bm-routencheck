# FM-Umbau — Skizze: Analoge FM-Relais in bm-routencheck integrieren

Stand: 2026-07-15 (Entwurf, noch nicht begonnen; Festlegungen aus
Abschnitt 8 sind vom Nutzer entschieden)

## 1. Ziel und Grundsatzentscheidung

Die drei Tools (`bm-bahn`, `bm-auto`, `bm-rad`) sollen zusätzlich zu den
Brandmeister-DMR-Relais auch **analoge FM-Relais** entlang der Route
auswerten — gleiche Pipeline, gleiche Ausgaben (Bericht, Karte, CSV,
Codeplug). Entscheidung vom 2026-07-15: **Integration in dieses Projekt**,
kein separates fm-routencheck (~80 % des Codes wären sonst dupliziert;
fachlich ist es dieselbe Frage).

Bedienung: neues gemeinsames Flag

```
--modus {dmr,fm,beide}      (Alias: --mode; Default: beide — Festlegung 2026-07-15)
```

Der Default `beide` ändert die Ausgaben bestehender Aufrufe (mehr
Einträge, neue Spalten gefüllt, zusätzliche DL3EL-Abfragen je Lauf) —
bewusst in Kauf genommen; wer das alte Verhalten braucht, setzt
`--modus dmr`.

Bei `beide` erscheinen DMR- und FM-Relais gemeinsam in Bericht, Karte und
CSV (Spalte/Badge „Modus"); der Codeplug-Export schreibt digitale und
analoge Kanäle in dieselbe Zone.

## 2. Datenquelle: relaislisten.darc.de (DL3EL)

Alle Kandidaten am 2026-07-15 live geprüft; nur eine Quelle erfüllt
Keyless-Prinzip **und** Deutschland-Abdeckung:

| Quelle | Befund (2026-07-15) |
|---|---|
| repeatermap.de | ❌ API nur noch mit Token (Vergabe auf Anfrage) — verletzt Keyless |
| RepeaterBook `exportROW.php` | ❌ `{"error_code":"auth_missing"}` — nicht mehr keyless |
| hearham.com `/api/repeaters/v1` | ❌ keyless, aber nur 19 FM-Relais in DL (von 22 350 gesamt) |
| przemienniki.net `rxf.xml` | ❌ keyless, aber nur 123 DE-Einträge; `mode`-Filter wird ignoriert |
| **relaislisten.darc.de** | ✅ keyless CGI, > 8000 Relais aus > 60 Ländern, CTCSS enthalten |

### Verifizierter Endpunkt

```
GET https://relaislisten.darc.de/cgi-bin/relais.pl
    ?sel=latlon&lat_deg=49&lat_min=30&lat_NS=Nord
    &lon_deg=11&lon_min=0&lon_EW=Ost
    &dxcc=dl&maxgateways=100&printas=csv&type=DL3EL&kmmls=km
```

Testabfrage um Nürnberg (2026-07-15) lieferte plausible FM-Relais
(DB0FUE, DB0UN, DB0GJ, …) mit Spalten
`Call;QRG;Input;Locator;Info;Breite;Länge;CTCSS;Mode/Node;Entfernung`.

### Eigenheiten (verifiziert, beim Client-Bau zu beachten)

- **Nur Umkreissuche, kein Volldump** — anders als BM `/device`. Es gibt
  keinen Radius-Parameter; zurück kommen die `maxgateways` nächsten
  Relais, nach Entfernung sortiert (Abfragestrategie: Abschnitt 4).
- **Schmutzige Formate:** CSV ist ISO-8859-1, Zeilen enden auf `<br>`,
  HTML-Entities im Text (`F&#252rth`), Dezimalkomma bei Frequenzen,
  Koordinaten nur bogenminutengenau (`49°28'N`).
  Die **GPX-Ausgabe** (`printas=gpx`) hat dezimale Koordinaten mit
  4 Nachkommastellen (`lat="+49.4809000"`), aber vor dem eigentlichen
  XML eine HTML-Präambel und `<br>`-Präfixe je Zeile → beide Formate
  brauchen einen defensiven Parser. **Ergebnis F0: CSV als Basis,
  Koordinaten aus zweitem GPX-Abruf derselben Query gemergt** (Schlüssel:
  Waypoint-Name = Call, erstes Token des `<cmt>` = QRG). Geprüft:
  `printas=chirp` liefert keine Koordinaten, taugt also nicht als
  Ein-Abruf-Alternative (bleibt aber Referenz für F3).
- **`type`-Parameter:** `type` ist im Formular eine Checkbox-Mehrfach-
  auswahl — mehrere `type=`-Parameter kombinierbar. **Ergebnis F0
  (2026-07-15): `type=DL3EL&type=fr`.** Die DL3EL-Basisliste allein ist
  unvollständig (um Nürnberg fehlten 5 echte FM-Relais mit Ablage:
  DB0TMH, DB0XG, DB0RWH, DB0KR, DB0IN — alle nur in der `fr`-Liste);
  `el`/`il` (Echolink/IRLP) brachten nur 2 exotische Zusatzeinträge und
  meist keine Input-QRG → weggelassen. Die beiden Listen überlappen
  sich, der Server dedupliziert **nicht** (18 Dubletten in 300
  Einträgen; teils mit unterschiedlich vielen Nachkommastellen,
  `438,5125` vs. `438,51250`) → Client-Dedupe über
  `(callsign, round(tx_mhz, 4))`.
- **Keine Antennenhöhe (agl)** in den Daten → `DEFAULT_AGL_M = 15.0`
  aus `coverage.py` greift für alle FM-Relais. Abdeckungsschätzung wird
  dadurch konservativer als bei BM (dort liefert die API agl oft mit).
- **Kein SLA, Hobby-Projekt** — moderate Request-Rate, Disk-Cache
  Pflicht, User-Agent mit Kontaktadresse (wie `bm_api/client.py`).
- Inaktive Relais werden ohne `showall=all` unterdrückt — Default so
  lassen (Analogie zur BM-24h-Regel: nur aktive Relais).

## 3. Datenmodell und Modul-Layout

Neues Paket **`bmtools/fm_api/`** als Geschwister von `bm_api/`:

```
bmtools/fm_api/
├── __init__.py
├── client.py      # DL3ELClient: Umkreis-Abfragen, Drosselung, Cache
├── parser.py      # CSV/GPX-Antworten → FmRepeater (Encoding, Entities, <br>)
└── models.py      # FmRepeater
```

```python
@dataclass(frozen=True)
class FmRepeater:
    id: int              # synthetisch, s. u.
    callsign: str
    tx_mhz: float        # Relais-Ausgabe (= RX des Funkgeräts)
    rx_mhz: float        # Relais-Eingabe (= TX des Funkgeräts)
    ctcss_hz: float | None
    lat: float
    lng: float
    city: str            # Info-Spalte, bereinigt
    locator: str
```

**Gemeinsames Interface statt Vererbung:** `coverage.py` und
`corridor.py` brauchen von einem Relais nur `lat`, `lng`, `agl`,
`callsign`, `id` (verifiziert: `coverage.py:107-108`, `corridor.py:84-89`).
Vorschlag: ein `typing.Protocol` „`RepeaterLike`" in `routelib/model.py`
mit genau diesen Attributen; `Device` erfüllt es unverändert,
`FmRepeater` bekommt `agl = None` als Property. `coverage`/`corridor`
tauschen ihren `Device`-Import gegen das Protocol — sonst keine Änderung.

**Synthetische IDs:** `CoverageEstimate.reachable_ids` u. a. arbeiten mit
`int`-IDs. DL3EL hat keine numerischen IDs. Damit sich FM- und DMR-IDs
im `beide`-Modus nie beißen: FM-IDs als negativer laufender Zähler oder
stabiler Hash < 0 (BM-Repeater-IDs sind 6-stellig positiv).

**Kanal- statt Standort-Sicht:** DL3EL liefert je Band einen Eintrag
(DB0FUE 2 m und 70 cm = zwei Zeilen). Das passt zum bestehenden Modell —
jeder Eintrag wird ein eigenes „Relais" (eigener Kanal), dedupliziert
wird über `(callsign, tx_mhz)`.

## 4. Abfragestrategie entlang der Route

Da es nur Umkreissuche gibt:

1. Route in Stützpunkte rastern (Vorschlag: alle **50 km** entlang
   `cumulative_km`, plus Start/Ziel).
2. Je Stützpunkt eine Abfrage mit `maxgateways=100`; Antworten über
   `(callsign, tx_mhz)` deduplizieren.
3. Plausibilitätsanker: `coverage.py` filtert ohnehin auf eine BBox mit
   `BBOX_BUFFER_KM = 60` um die Strecke — Schrittweite und `maxgateways`
   müssen zusammen sicherstellen, dass alle Relais im 60-km-Band
   gefunden werden. **Dichte-Check F0 (2026-07-15), Region Ruhrgebiet
   (51°30'N 7°30'E, dichteste Region) mit `type=DL3EL&type=fr`:**
   Eintrag Nr. 100 liegt bei 75 km, Nr. 200 bei 129 km, Nr. 300 bei
   166 km (`maxgateways=300` wird akzeptiert). Bei 50-km-Raster braucht
   ein Stützpunkt ≈ 65 km Radius (60 km BBox + halbe Schrittweite) —
   100 wäre zu knapp, **Festlegung: `maxgateways=200`**.
4. Caching wie `bm_api`: `Cache("bmtools/fm", ttl=24*3600)`, Cache-Key =
   gerundeter Stützpunkt (z. B. auf 0,1°), damit ähnliche Routen Treffer
   teilen; `--aktualisieren` wirkt auch hier.
5. Drosselung: `REQUEST_DELAY`-Mechanik aus `bm_api/client.py`
   wiederverwenden (ggf. `_fetch_json`-Kern in ein gemeinsames Modul
   ziehen — einziger Unterschied ist Text- statt JSON-Antwort).

## 5. Änderungen in der Pipeline (`routelib/`)

| Stelle | Änderung |
|---|---|
| `pipeline.run_pipeline()` | Parameter `modus`; lädt BM-Repeater und/oder FM-Relais. TG-Profil-Schleife (`_with_local_tg`, `client.profile`) nur für DMR-Treffer. Konsolen-Texte modusabhängig („… ohne DMR" → „… ohne Relais") |
| `report.RepeaterResult` | Wird modusfähig: `profile` optional (FM hat keins) oder eigenes `FmResult` + gemeinsame Basis — Entscheidung bei F2. Konsolentabelle: für FM entfallen CC/TS1/TS2, stattdessen Spalte **CTCSS**; Titel „DMR-Relais …" wird modusabhängig |
| `report.write_csv` | Neue Spalten `modus`, `ctcss_hz`; TG-/CC-Spalten bei FM leer. Eine Datei für beide Modi (Konsistenz-Zusage: Karte/Bericht/CSV zeigen dieselben Relais) |
| `report_html` | Kanaltabellen je Relais: FM-Variante ohne TG-Blöcke, mit CTCSS und Ablage (±600 kHz / ±7,6 MHz aus rx−tx berechnen und anzeigen) |
| `mapview` | Popup modusabhängig; Marker-Farbe je Modus (DMR blau, FM grün o. ä.), Grenzbereich bleibt grau. Viewshed-Logik unverändert |
| `coverage` / `corridor` | Nur Import-Umstellung auf das `RepeaterLike`-Protocol (Abschnitt 3) |
| CLI (`rail/cli.py`, `road/cli.py`, `cli.py`) | Flag `--modus` (Alias `--mode`), interaktive Abfrage als dritte Frage; Durchreichen an `run_pipeline` |

Fachliche Regeln, die **nicht** auf FM übertragen werden: TG9-Ergänzung,
Slot-0-Behandlung, Colorcode — alles rein DMR. Neue FM-Regel analog zur
Frequenz-Sicht-Regel (festgelegt und umgesetzt in F2): **RX =
Relais-Ausgabe**, unverändert aus Gerätesicht; **CTCSS gilt als
Encode-Ton** (Gerät sendet Ton), Decode standardmäßig offen — steht so
im Bericht-Kopf; die Ablage wird stets aus rx−tx berechnet (F0-Befund:
Auslandsablagen weichen ab) und in Bericht/Karte angezeigt.

Abweichung von der Skizze (F2): FM-Marker sind **orange** statt grün —
die Farbwelt des Projekts ist bewusst ohne Rot/Grün (CVD-sicher,
s. `ui.py`); Orange ist die etablierte Akzentfarbe.

## 6. Codeplug-Export (AnyTone)

`codeplug/anytone.py` ist tabellengesteuert — analoge Kanäle brauchen nur
andere Feldwerte, keine neuen Spalten:

| Feld | FM-Wert |
|---|---|
| `Channel Type` | `A-Analog` |
| `Band Width` | Default `12.5K`; per Flag `--bandbreite {12.5,25}` global auf `25K` umstellbar (das Relais-Raster steht nicht in den Daten, eine Automatik ist daher nicht möglich — Festlegung 2026-07-15) |
| `CTCSS/DCS Encode` | Ton aus Daten (z. B. `88.5`), sonst `Off` |
| `CTCSS/DCS Decode` | Default `Off` (Gerät hört alles); per Flag `--ctcss-decode` auf den Relais-Ton setzbar (Festlegung 2026-07-15) |
| `Contact` / `Contact TG/DMR ID` / `Color Code` / `Slot` / `DMR MODE` | leer bzw. Defaults — für Analogkanäle ignoriert die CPS diese Felder (am Import zu verifizieren) |
| Kanalname | `<Call> <Band>` z. B. `DB0FUE 70cm` (16-Zeichen-Limit beachten) |

`TalkGroups.CSV` erhält keine FM-Einträge; die Zone nimmt analoge und
digitale Kanäle gemischt auf. Der D890UV-Vorbehalt aus M5 gilt unverändert.

### CHIRP-Export (zusätzlich, nur FM-Kanäle)

Neu (Nutzerwunsch 2026-07-15): zusätzlich zum AnyTone-Export schreibt
jeder Lauf mit FM-Anteil ein **`chirp.csv`** im generischen
CHIRP-CSV-Format — direkt in CHIRP zu öffnen bzw. importieren und von
dort auf jedes CHIRP-unterstützte Gerät ladbar. CHIRP kann kein DMR;
die Datei enthält ausschließlich die FM-Kanäle.

Format ([CSV HowTo](https://chirpmyradio.com/projects/chirp/wiki/CSV_HowTo)):
Header-basiertes Komma-CSV; Spalten mit sinnvollen Defaults dürfen
entfallen. Geplante Spalten und Mapping:

| CHIRP-Spalte | Wert |
|---|---|
| `Location` | laufende Nummer ab 1 |
| `Name` | Rufzeichen (+ Band bei Mehrband-Standorten, z. B. `DB0FUE 70`) |
| `Frequency` | Relais-Ausgabe in MHz (= RX des Funkgeräts, Punkt als Dezimaltrenner) |
| `Duplex` | `+`/`-` aus Vorzeichen von (Eingabe − Ausgabe); leer bei Simplex |
| `Offset` | Betrag der Ablage in MHz (`0.600000`, `7.600000`) |
| `Tone` | `Tone` wenn CTCSS vorhanden (nur Encode); mit `--ctcss-decode`: `TSQL`; sonst leer |
| `rToneFreq` / `cToneFreq` | CTCSS-Ton in Hz (CHIRP erwartet beide Felder gefüllt, genutzt wird je nach `Tone`-Modus) |
| `Mode` | `NFM` bei 12,5 kHz (Default), `FM` bei `--bandbreite 25` |
| `Comment` | Standort/Info aus den DL3EL-Daten |

Umsetzung als `codeplug/chirp.py` neben `anytone.py`, gleiche
tabellengesteuerte Machart. Kein Blindformat-Risiko wie beim D890UV:
CHIRP ist frei verfügbar, der Import wird in F3 real getestet.
Querprüfung möglich: DL3EL selbst bietet `printas=chirp` — dessen
Ausgabe dient in F0/F3 als Referenz für Feldbelegungen (z. B.
Duplex-/Tone-Konventionen), auch wenn wir aus unseren gefilterten
Routen-Treffern exportieren, nicht aus der Roh-Antwort.

## 7. Meilensteine (je mit abgenommenem Testlauf, Kein Try&Error)

- [x] **F0 — Quelle festnageln** (erledigt 2026-07-15): `type`-Kombination
      und Abfragestrategie an drei Regionen verifiziert (Nürnberg,
      Aachen grenznah, Ruhrgebiet als Dichte-Check) — Ergebnisse in
      Abschnitt 2/4 eingearbeitet (`type=DL3EL&type=fr`,
      `maxgateways=200`, Client-Dedupe). Umgesetzt: `bmtools/fm_api/`
      mit `models.py` (`FmRepeater`, synthetische negative IDs via
      CRC32) und `parser.py` (CSV-Parse, GPX-Koordinaten-Merge über
      `(Call, QRG)`, Dedupe); aufgezeichnete Antworten als Fixtures in
      `tests/fixtures/dl3el_*` (CSV Nürnberg + Aachen, GPX Nürnberg,
      CHIRP Nürnberg als Referenz für F3), Tests in
      `tests/test_fm_parser.py`. Befunde:
      - Entities **vor** dem Spalten-Split dekodieren — `&deg;` enthält
        selbst ein `;` und zerlegt sonst die Koordinatenspalten; Info-
        Spalten mit echtem `;` werden per Feldzählung wieder gefügt.
      - Auslandsqualität (Aachen, 108/300 Einträge NL/ON/LX/F): Koordi-
        naten und CTCSS brauchbar; **Ablagen abweichend** (NL-70 cm
        +1,6 MHz) — Ablage immer aus rx−tx berechnen, nie annehmen.
      - 7/300 Aachen-Zeilen unbrauchbar und vom Parser verworfen (Input
        leer/`#WERT!`/`Simplex`/`0,0000`, Ausgabe `00` — auch ein
        deutscher Eintrag darunter); um Nürnberg 0/100.
      - Wenige Simplex-Einträge (Input = Ausgabe, z. B. DB0HBG) bleiben
        drin; Darstellung entscheidet F2.
      - Die HTML-Webansicht enthält ebenfalls Dezimalkoordinaten
        (aprs.fi-Links) — Alternative zum GPX-Merge, nicht genutzt.
      Abnahme: CSV-Antwort um Nürnberg (`type=DL3EL&type=fr`,
      `maxgateways=100`) deckungsgleich mit der Webansicht
      (`printas=html`) derselben Query — 100 Zeilen, identische
      (Call, QRG)-Menge.
- [x] **F1 — `fm_api`-Client** (erledigt 2026-07-15): `client.py` mit
      `DL3ELClient` — Umkreisabfrage je Stützpunkt (CSV + GPX derselben
      Query), Disk-Cache `Cache(24*3600, "bmtools/fm")` mit Rohantworten
      als Wert und auf 0,1° gerastetem Stützpunkt als Key (abgefragt
      wird der Rasterpunkt selbst, damit Key und Query identisch sind;
      Versatz ≤ ~7 km ist gegen den 129-km-Antwortradius unerheblich),
      Drosselung 1 s Grundpause + Retry-Backoff (bewusst ohne
      Retry-After-Logik — das CGI kennt kein Rate-Limit, daher eigener
      `_fetch_text` statt Refactoring von `bm_api._fetch_json`),
      `repeaters_along()` mit 50-km-Raster + Ziel und Dedupe. Tests mit
      MockTransport gegen die F0-Fixtures (`tests/test_fm_client.py`).
      Zusatzbefund: negative Koordinaten funktionieren — Formular-Wörter
      `South`/`West` live verifiziert (London-Probe liefert GB3-Relais
      mit korrekt negativen Längen aus dem GPX-Merge).
      Abnahme: Trockenlauf Koblenz→Frankfurt→Würzburg→Nürnberg
      (269 km, 7 Stützpunkte): 425 eindeutige FM-Relais, davon 51 im
      25-km-Korridor — Verlauf plausibel (DB0ZK Koblenz km 0, Feldberg-
      Relais km 62, DB0WZ Würzburg km 177, DB0FUE/DB0UN/DB0ANN am Ziel),
      korrekt nach Streckenkilometer sortiert.
- [x] **F2 — Pipeline/Berichte** (erledigt 2026-07-15):
      `RepeaterLike`-Protocol in `routelib/model.py`, `coverage`/
      `corridor` auf das Protocol umgestellt. Entscheidung Results:
      **ein** `RepeaterResult` mit `profile: DeviceProfile | None` und
      explizitem `modus`-Feld (keine FmResult-Hierarchie — eine Liste,
      gemeinsame Sortierung). Konsolentabelle/CSV/HTML/Karte modusfähig
      (Spalten Modus + CTCSS nur wenn nötig; reines DMR sieht aus wie
      vorher), Pipeline lädt je Modus BM und/oder DL3EL (FM überspringt
      die TG-Profil-Schleife), CLIs mit `--modus`/`--mode` (Default
      beide, interaktive Frage in allen Assistenten). Codeplug-Export
      erhält vorerst nur die DMR-Kanäle (analog + CHIRP: F3); bei
      `--modus fm` entfällt er. Abnahme: `bm-bahn --modus beide`
      Koblenz→Nürnberg (355 km, Geländemodell): 69 Relais (20 DMR,
      49 FM) konsistent in CSV (Spalten modus/ctcss_hz), Karte
      (19 blaue, 44 orange, 6 graue Marker = 69) und Bericht (69
      Abschnitte, 49 FM-Kanaltabellen mit CTCSS und Ablage);
      AnyTone-Export weiter rein digital.
- [x] **F3 — Codeplug analog** (umgesetzt 2026-07-15, CPS-Import-Check
      offen, s. u.): `write_anytone` schreibt FM-Treffer als
      `A-Analog`-Kanäle in die gemischte Zone (Kanalname
      `<Call> <Band>`, Band Width je `--bandbreite`, CTCSS Encode aus
      den Daten, Decode per `--ctcss-decode`; CC/Slot/DMR MODE bekommen
      benigne Werte 1/1/0 statt Leerfeldern — minimiert Importfehler,
      die CPS ignoriert sie für Analogkanäle); `TalkGroups.CSV` bleibt
      rein DMR. Neu `codeplug/chirp.py`: generisches CHIRP-CSV, nur
      FM-Kanäle, Name = Call (+ Band nur bei Mehrband, + QRG bei
      Banddoppelung), Duplex/Offset aus rx−tx, `Tone`/`TSQL` je
      `--ctcss-decode`, NFM/FM je `--bandbreite`. Flags in beiden CLIs
      (geteilt über `ui.add_fm_arguments`).
      Befunde aus der Querprüfung gegen DL3EL `printas=chirp`:
      - Dedupe verbessert: bei Dubletten ersetzt ein Eintrag **mit**
        CTCSS einen tonlosen (DB0THM trägt den Ton nur im fr-Eintrag) —
        sonst hätte der Codeplug den Ton verloren.
      - Die Quelle enthält vereinzelt widersprüchliche CTCSS-Angaben je
        Liste (DB0CJ: 71,9 vs. 100,0 Hz) und uneinheitliche
        Simplex-Reste in der eigenen CHIRP-Ausgabe — unsere Schreibweise
        (Duplex leer, Offset 0) ist die saubere CHIRP-Semantik.
      Abnahme: Lauf Koblenz→Nürnberg `--modus beide` → 184 Kanäle
      (135 digital + 49 analog) in einer Zone, `chirp.csv` mit 49
      FM-Kanälen. `chirp.csv` mit dem **echten CHIRP-Treiber**
      (Upstream `generic_csv`) fehlerfrei geladen: Frequenzen, Ablagen,
      Töne, NFM korrekt; TSQL- (`--ctcss-decode`) und FM-Variante
      (`--bandbreite 25`) ebenfalls verifiziert. **Noch offen (Nutzer):**
      Import von `anytone/` in der AnyTone-CPS — analoger Kanal mit
      korrektem CTCSS (D890UV-Vorbehalt aus M5 gilt unverändert).
- [ ] **F4 — Doku:** README (Modus-Flag, neue Quelle, `chirp.csv` in
      der Ausgaben-Tabelle), PROJEKTPLAN (Eigenheiten DL3EL nach
      Abschnitt „Datenquellen" übernehmen, diese Datei danach auflösen).

## 8. Festlegungen durch den Nutzer

Entschieden am 2026-07-15:

| Punkt | Festlegung |
|---|---|
| Bandbreite Analogkanäle | Default 12,5 kHz; 25 kHz wird unterstützt (`--bandbreite`, s. Abschnitt 6) |
| CTCSS Decode | Default aus (Gerät hört alles); optional per `--ctcss-decode` auf den Relais-Ton |
| Nachbarländer | Mitnehmen: Abfrage mit `dxcc=all`; die geografische Eingrenzung leistet die Umkreissuche + Coverage-BBox. Grenzregion-Check in F0 |
| Default für `--modus` | `beide` — geänderte Ausgaben bestehender Aufrufe bewusst in Kauf genommen (s. Abschnitt 1) |

Damit sind alle Festlegungen getroffen; die Skizze ist umsetzungsbereit
(Start: F0).
