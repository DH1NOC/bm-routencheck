"""AnyTone-CPS-CSV-Export (Channel / TalkGroups / Zone).

ARBEITSANNAHME (Stand 2026-07-11): Spaltenlayout des AT-D878UV (CPS 1.21+).
Das AT-D890UV nutzt ein abweichendes Header-Layout — sobald ein
Beispiel-Export aus der D890UV-CPS vorliegt, werden CHANNEL_COLUMNS /
CHANNEL_DEFAULTS hier angepasst. Deshalb ist alles tabellengesteuert.
"""
from __future__ import annotations

import csv
from pathlib import Path

from bmtools.fm_api.models import band_label

from ..report import RepeaterResult

CHANNEL_COLUMNS = [
    "No.", "Channel Name", "Receive Frequency", "Transmit Frequency",
    "Channel Type", "Transmit Power", "Band Width",
    "CTCSS/DCS Decode", "CTCSS/DCS Encode",
    "Contact", "Contact Call Type", "Contact TG/DMR ID", "Radio ID",
    "Busy Lock/TX Permit", "Squelch Mode", "Optional Signal",
    "DTMF ID", "2Tone ID", "5Tone ID", "PTT ID",
    "Color Code", "Slot", "Scan List", "Receive Group List",
    "PTT Prohibit", "Reverse", "Simplex TDMA", "Slot Suit",
    "AES Digital Encryption", "Digital Encryption", "Call Confirmation",
    "Talk Around(Simplex)", "Work Alone", "Custom CTCSS", "2TONE Decode",
    "Ranging", "Through Mode", "APRS RX",
    "Analog APRS PTT Mode", "Digital APRS PTT Mode", "APRS Report Type",
    "Digital APRS Report Channel", "Correct Frequency[Hz]",
    "SMS Confirmation", "Exclude channel from roaming", "DMR MODE",
    "DataACK Disable", "R5toneBot", "R5ToneEot", "Auto Scan",
    "Ana Aprs Mux", "Send Talker Alias",
]

CHANNEL_DEFAULTS = {
    "Channel Type": "D-Digital",
    "Transmit Power": "High",
    "Band Width": "12.5K",
    "CTCSS/DCS Decode": "Off",
    "CTCSS/DCS Encode": "Off",
    "Contact Call Type": "Group Call",
    "Radio ID": "My Radio",
    "Busy Lock/TX Permit": "Always",
    "Squelch Mode": "Carrier",
    "Optional Signal": "Off",
    "DTMF ID": "1", "2Tone ID": "1", "5Tone ID": "1",
    "PTT ID": "Off",
    "Scan List": "None",
    "Receive Group List": "None",
    "PTT Prohibit": "Off",
    "Reverse": "Off",
    "Simplex TDMA": "Off",
    "Slot Suit": "Off",
    "AES Digital Encryption": "Normal Encryption",
    "Digital Encryption": "Off",
    "Call Confirmation": "Off",
    "Talk Around(Simplex)": "Off",
    "Work Alone": "Off",
    "Custom CTCSS": "251.1",
    "2TONE Decode": "1",
    "Ranging": "Off",
    "Through Mode": "Off",
    "APRS RX": "Off",
    "Analog APRS PTT Mode": "Off",
    "Digital APRS PTT Mode": "Off",
    "APRS Report Type": "Off",
    "Digital APRS Report Channel": "1",
    "Correct Frequency[Hz]": "0",
    "SMS Confirmation": "Off",
    "Exclude channel from roaming": "0",
    "DMR MODE": "1",  # 1 = Repeater
    "DataACK Disable": "0",
    "R5toneBot": "0", "R5ToneEot": "0",
    "Auto Scan": "0",
    "Ana Aprs Mux": "Off",
    "Send Talker Alias": "0",
}

NAME_MAX = 16  # Zeichenlimit für Kanal-/Zonennamen


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        w.writerows(rows)


def _tg_name(tg: int, tg_names: dict[int, str]) -> str:
    return tg_names.get(tg, f"TG{tg}")


def _unique_name(base: str, used: set[str]) -> str:
    """Kanalname eindeutig machen (Kollision → ~2, ~3, …)."""
    name = base[:NAME_MAX]
    n = 2
    while name in used:
        name = base[:NAME_MAX - 2] + f"~{n}"
        n += 1
    used.add(name)
    return name


def write_anytone(
    results: list[RepeaterResult],
    out_dir: Path,
    zone_name: str,
    tg_names: dict[int, str],
    bandbreite: str = "12.5",
    ctcss_decode: bool = False,
) -> list[Path]:
    """bandbreite ("12.5"/"25") und ctcss_decode betreffen nur die
    analogen FM-Kanäle (Festlegungen 2026-07-15, FM-UMBAU.md)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Kanäle: DMR ein Kanal je (Relais, Talkgroup, Slot), Cluster über die
    # lokale TG; FM ein Analogkanal je Relais-Eintrag — gemischte Zone
    channels: list[dict[str, str]] = []
    used_names: set[str] = set()
    used_tgs: set[int] = set()
    for r in results:
        d = r.device
        if not d.tx_mhz or not d.rx_mhz:
            continue
        if r.modus == "fm":
            ton = f"{d.ctcss_hz:g}" if d.ctcss_hz else None
            channels.append({
                "Channel Name": _unique_name(
                    f"{d.callsign} {band_label(d.tx_mhz)}", used_names),
                "Receive Frequency": f"{d.tx_mhz:.5f}",   # Relais-Ausgabe
                "Transmit Frequency": f"{d.rx_mhz:.5f}",  # Relais-Eingabe
                "Channel Type": "A-Analog",
                "Band Width": "25K" if bandbreite == "25" else "12.5K",
                # CTCSS: Encode aus den Daten, Decode default offen
                # (Gerät hört alles); --ctcss-decode setzt den Relais-Ton
                "CTCSS/DCS Encode": ton or "Off",
                "CTCSS/DCS Decode": ton if ctcss_decode and ton else "Off",
                # CC/Slot/DMR MODE: benigne Werte — die CPS ignoriert sie
                # für Analogkanäle (am Import zu verifizieren, F3)
                "Color Code": "1",
                "Slot": "1",
                "DMR MODE": "0",
            })
            continue
        seen: set[tuple[int, int]] = set()
        for s in r.profile.subscriptions:
            if (s.talkgroup, s.slot) in seen:
                continue
            seen.add((s.talkgroup, s.slot))
            used_tgs.add(s.talkgroup)
            name = f"{d.callsign} {s.talkgroup}"[:NAME_MAX]
            if name in used_names:  # gleiche TG auf beiden Slots
                name = f"{d.callsign} {s.talkgroup} S{s.slot}"[:NAME_MAX]
            name = _unique_name(name, used_names)
            channels.append({
                "Channel Name": name,
                "Receive Frequency": f"{d.tx_mhz:.5f}",   # Relais-Ausgabe
                "Transmit Frequency": f"{d.rx_mhz:.5f}",  # Relais-Eingabe
                "Contact": _tg_name(s.talkgroup, tg_names),
                "Contact TG/DMR ID": str(s.talkgroup),
                "Color Code": str(d.colorcode or 1),
                # Slot 0 = Simplex-Repeater ohne TDMA -> Slot 1, DMR MODE 0
                "Slot": str(s.slot if s.slot in (1, 2) else 1),
                "DMR MODE": "1" if d.tx_mhz != d.rx_mhz else "0",
            })

    channel_rows = []
    for i, ch in enumerate(channels, start=1):
        row = {"No.": str(i), **CHANNEL_DEFAULTS, **ch}
        channel_rows.append([row.get(col, "") for col in CHANNEL_COLUMNS])
    channel_path = out_dir / "Channel.CSV"
    _write(channel_path, CHANNEL_COLUMNS, channel_rows)

    # Talkgroup-Kontakte
    tg_header = ["No.", "Radio ID", "Name", "Call Type", "Call Alert"]
    tg_rows = [
        [str(i), str(tg), _tg_name(tg, tg_names), "Group Call", "None"]
        for i, tg in enumerate(sorted(used_tgs), start=1)
    ]
    tg_path = out_dir / "TalkGroups.CSV"
    _write(tg_path, tg_header, tg_rows)

    # Zone mit allen Kanälen
    zone_header = [
        "No.", "Zone Name", "Zone Channel Member",
        "Zone Channel Member RX Frequency", "Zone Channel Member TX Frequency",
        "A Channel", "A Channel RX Frequency", "A Channel TX Frequency",
        "B Channel", "B Channel RX Frequency", "B Channel TX Frequency",
        "Zone Hide",
    ]
    names = [c["Channel Name"] for c in channels]
    rx = [c["Receive Frequency"] for c in channels]
    tx = [c["Transmit Frequency"] for c in channels]
    zone_rows = [[
        "1", zone_name[:NAME_MAX],
        "|".join(names), "|".join(rx), "|".join(tx),
        names[0], rx[0], tx[0],
        names[min(1, len(names) - 1)], rx[min(1, len(rx) - 1)], tx[min(1, len(tx) - 1)],
        "0",
    ]] if names else []
    zone_path = out_dir / "Zone.CSV"
    _write(zone_path, zone_header, zone_rows)

    return [channel_path, tg_path, zone_path]
