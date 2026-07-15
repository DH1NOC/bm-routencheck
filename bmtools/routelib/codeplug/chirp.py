"""CHIRP-CSV-Export — nur die analogen FM-Kanäle.

Generisches CHIRP-CSV (chirpmyradio.com/projects/chirp/wiki/CSV_HowTo):
direkt in CHIRP zu öffnen und von dort auf jedes unterstützte Gerät
ladbar. CHIRP kann kein DMR — DMR-Treffer werden übersprungen, dafür
gibt es den AnyTone-Export.

Feldkonventionen quergeprüft gegen DL3ELs eigene CHIRP-Ausgabe
(printas=chirp, Fixture tests/fixtures/dl3el_nuernberg.chirp):
Duplex als Vorzeichen der Ablage, Offset als Betrag, "Tone" = nur
Encode. Bewusste Abweichung: Mode NFM bei 12,5 kHz (Default) statt
pauschal FM — die Bandbreiten-Festlegung aus FM-UMBAU.md gilt auch hier.
"""
from __future__ import annotations

import csv
from pathlib import Path

from bmtools.fm_api.models import band_label

from ..report import RepeaterResult

CHIRP_COLUMNS = [
    "Location", "Name", "Frequency", "Duplex", "Offset",
    "Tone", "rToneFreq", "cToneFreq", "DtcsCode", "DtcsPolarity",
    "Mode", "TStep", "Skip", "Comment", "URCALL", "RPT1CALL", "RPT2CALL",
]

DEFAULT_TONE_HZ = 88.5  # CHIRP-Standardwert für ungenutzte Tonfelder


def _names(results: list[RepeaterResult]) -> dict[int, str]:
    """Kanalname je Ergebnis: Rufzeichen, bei Mehrband-Standorten plus
    Band, bei gleichem Band plus Frequenz (Eindeutigkeit)."""
    fm = [r for r in results if r.modus == "fm"]
    per_call: dict[str, int] = {}
    for r in fm:
        per_call[r.device.callsign] = per_call.get(r.device.callsign, 0) + 1
    names: dict[int, str] = {}
    used: set[str] = set()
    for r in fm:
        d = r.device
        name = (d.callsign if per_call[d.callsign] == 1
                else f"{d.callsign} {band_label(d.tx_mhz)}")
        if name in used:  # zwei Kanäle desselben Bands (z. B. DB0BGK 70cm)
            name = f"{d.callsign} {d.tx_mhz:g}"
        used.add(name)
        names[id(r)] = name
    return names


def write_chirp(
    results: list[RepeaterResult],
    path: Path,
    bandbreite: str = "12.5",
    ctcss_decode: bool = False,
) -> Path | None:
    """Schreibt chirp.csv; None, wenn kein FM-Kanal dabei ist."""
    names = _names(results)
    rows = []
    for r in results:
        if r.modus != "fm":
            continue
        d = r.device
        offset = d.rx_mhz - d.tx_mhz  # Relais-Eingabe − Ausgabe
        ton = d.ctcss_hz
        tone_mode = ("" if not ton else "TSQL" if ctcss_decode else "Tone")
        tone_hz = f"{ton or DEFAULT_TONE_HZ:g}"
        rows.append([
            str(len(rows) + 1),
            names[id(r)],
            f"{d.tx_mhz:.6f}",                      # Relais-Ausgabe = Geräte-RX
            "" if abs(offset) < 1e-9 else "+" if offset > 0 else "-",
            f"{abs(offset):.6f}",
            tone_mode,
            tone_hz, tone_hz,                        # CHIRP will beide gefüllt
            "023", "NN",                             # DCS ungenutzt (Defaults)
            "FM" if bandbreite == "25" else "NFM",
            "12.5", "",                              # TStep, Skip
            d.city, "", "", "",
        ])
    if not rows:
        return None
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CHIRP_COLUMNS)
        w.writerows(rows)
    return path
