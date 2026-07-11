# BrandmeisterTools

Python-Tools rund um das Brandmeister-DMR-Netzwerk.

## bm-rail — DMR-Relais entlang einer Bahnstrecke

Findet alle Brandmeister-Relais im Korridor einer Bahnverbindung und liefert
Rufzeichen, Frequenzen, Colorcode und die Talkgroups in TS1/TS2 — statisch,
zeitgeschaltet (mit Zeitfenster, Lokalzeit) und Cluster.

```bash
# Installation (einmalig, in der venv)
pip install -e .

# Nutzung
bm-rail --from "Koblenz Hbf" --to "Nürnberg Hbf" --corridor 15
bm-rail --from Koblenz --via "Frankfurt Hbf" --to Nürnberg
bm-rail --stations "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --straight-line
```

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

**Hinweis:** Der AnyTone-Export nutzt derzeit das D878UV-Spaltenlayout als
Arbeitsannahme; die Anpassung auf das AT-D890UV steht aus (siehe
`PROJEKTPLAN.md`, M5).

Datenquellen: [Brandmeister-API](https://api.brandmeister.network/v2/) (ohne
Key, nur Lesezugriff, Antworten werden lokal gecacht) und
[Transitous](https://transitous.org) für die Streckengeometrie.

## Projektstruktur

- `bmtools/bm_api/` — wiederverwendbarer Brandmeister-API-Client (Cache, Modelle)
- `bmtools/rail/` — bm-rail (Route, Korridor, Berichte, Codeplug-Export)
- `PROJEKTPLAN.md` — Plan, Entscheidungen, offene Punkte
