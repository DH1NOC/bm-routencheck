"""Tests CHIRP-CSV-Export — inkl. Querprüfung der Feldkonventionen gegen
DL3ELs eigene CHIRP-Ausgabe (printas=chirp, aufgezeichnet in F0)."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from bmtools.bm_api.models import TalkgroupSub
from bmtools.fm_api import dedupe, parse_csv
from bmtools.routelib.codeplug.chirp import CHIRP_COLUMNS, write_chirp
from tests.conftest import (
    make_device, make_fm_repeater, make_fm_result, make_result)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(encoding="utf-8")))


def test_nur_fm_kanaele_mit_duplex_und_ton(tmp_path: Path):
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static")]),  # DMR
        make_fm_result(make_fm_repeater(
            callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525, ctcss_hz=88.5)),
        make_fm_result(make_fm_repeater(          # NL-Ablage: +1,6 MHz
            callsign="PI2RMD", tx_mhz=430.3625, rx_mhz=431.9625,
            ctcss_hz=None)),
        make_fm_result(make_fm_repeater(          # Simplex-Gateway
            callsign="DB0SX", tx_mhz=145.2375, rx_mhz=145.2375,
            ctcss_hz=None)),
    ]
    out = write_chirp(results, tmp_path / "chirp.csv")
    rows = _read(out)

    assert list(rows[0].keys()) == CHIRP_COLUMNS
    assert [r["Location"] for r in rows] == ["1", "2", "3"]  # DMR fehlt
    fx, rmd, sx = rows
    assert (fx["Frequency"], fx["Duplex"], fx["Offset"]) == \
        ("439.125000", "-", "7.600000")
    assert (fx["Tone"], fx["rToneFreq"], fx["cToneFreq"]) == \
        ("Tone", "88.5", "88.5")
    assert fx["Mode"] == "NFM"                    # 12,5 kHz Default
    assert (rmd["Duplex"], rmd["Offset"]) == ("+", "1.600000")
    assert rmd["Tone"] == ""
    assert (sx["Duplex"], sx["Offset"]) == ("", "0.000000")


def test_flags_tsql_und_fm_bei_25khz(tmp_path: Path):
    results = [make_fm_result(make_fm_repeater(ctcss_hz=88.5))]
    out = write_chirp(results, tmp_path / "chirp.csv",
                      bandbreite="25", ctcss_decode=True)
    row = _read(out)[0]
    assert row["Tone"] == "TSQL"
    assert row["Mode"] == "FM"


def test_namen_band_nur_bei_mehrband(tmp_path: Path):
    results = [
        make_fm_result(make_fm_repeater(callsign="DB0EIN")),
        make_fm_result(make_fm_repeater(
            callsign="DB0ZWEI", tx_mhz=145.6, rx_mhz=145.0)),
        make_fm_result(make_fm_repeater(
            callsign="DB0ZWEI", tx_mhz=438.8, rx_mhz=431.2)),
        make_fm_result(make_fm_repeater(          # gleiches Band doppelt
            callsign="DB0ZWEI", tx_mhz=439.225, rx_mhz=431.625)),
    ]
    names = [r["Name"] for r in _read(write_chirp(results, tmp_path / "c.csv"))]
    assert names == ["DB0EIN", "DB0ZWEI 2m", "DB0ZWEI 70cm", "DB0ZWEI 439.225"]


def test_ohne_fm_keine_datei(tmp_path: Path):
    results = [make_result(make_device(), [TalkgroupSub(262, 1, "static")])]
    assert write_chirp(results, tmp_path / "chirp.csv") is None
    assert not (tmp_path / "chirp.csv").exists()


def test_querpruefung_gegen_dl3el_referenz(tmp_path: Path):
    """Duplex-, Offset- und Tone-Konventionen müssen der CHIRP-Ausgabe
    von DL3EL selbst entsprechen (gleiche Quelldaten aus F0).
    Bewusst ausgenommen: Mode (wir schreiben NFM bei 12,5 kHz)."""
    # Je (Call, QRG) können mehrere Referenzzeilen existieren — die
    # Quelle enthält Dubletten, teils mit widersprüchlichem CTCSS
    # (DB0CJ: 71,9 Hz in der fr-, 100,0 Hz in der DL3EL-Liste)
    referenz: dict[tuple[str, float], list[dict[str, str]]] = {}
    for line in (FIXTURES / "dl3el_nuernberg.chirp").read_text(
            encoding="iso-8859-1").splitlines():
        line = html.unescape(line.removesuffix("<br>"))
        cells = next(csv.reader([line]))
        if not cells or not cells[0].isdigit():
            continue
        row = dict(zip(CHIRP_COLUMNS, cells, strict=False))
        key = (row["Name"], round(float(row["Frequency"]), 4))
        referenz.setdefault(key, []).append(row)

    repeaters = dedupe(parse_csv(
        (FIXTURES / "dl3el_nuernberg.csv").read_text(encoding="iso-8859-1")))
    results = [make_fm_result(r) for r in repeaters]
    rows = _read(write_chirp(results, tmp_path / "chirp.csv"))

    def passt(row: dict[str, str], ref: dict[str, str]) -> bool:
        if row["Duplex"] == "":
            # Simplex: die Referenz schreibt hier uneinheitliche Reste
            # ("+" mit Offset 0.0 bei DB0BH, leer mit Offset 0.6 bei
            # DB0HBG) — CHIRP wertet beides als "kein Versatz"; nur die
            # effektive Bedeutung vergleichen
            if ref["Duplex"] != "" and float(ref["Offset"]) != 0.0:
                return False
        elif (row["Duplex"] != ref["Duplex"]
              or float(row["Offset"]) != float(ref["Offset"])):
            return False
        if row["Tone"] != ref["Tone"]:
            return False
        return (not row["Tone"]
                or float(row["rToneFreq"]) == float(ref["rToneFreq"]))

    verglichen = 0
    for row in rows:
        key = (row["Name"].split()[0], round(float(row["Frequency"]), 4))
        refs = referenz.get(key)
        if refs is None:
            continue
        assert any(passt(row, ref) for ref in refs), (key, row, refs)
        verglichen += 1
    assert verglichen >= 80  # fast alle 95 eindeutigen Kanäle abgeglichen
