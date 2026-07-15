"""Tests DL3EL-Parser: echte aufgezeichnete Antworten (2026-07-15) als Fixtures.

Abfragen: sel=latlon, dxcc=all, type=DL3EL&type=fr, printas=csv/gpx;
Nürnberg (49°30'N 11°00'E, maxgateways=100) und als Grenzregion
Aachen (50°46'N 6°06'E, maxgateways=300, NL/ON/LX/F-Einträge).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bmtools.fm_api import (
    FmRepeater,
    dedupe,
    fm_repeater_id,
    merge_gpx_coords,
    parse_csv,
    parse_gpx_coords,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="iso-8859-1")


@pytest.fixture(scope="module")
def nuernberg() -> list[FmRepeater]:
    return parse_csv(fixture_text("dl3el_nuernberg.csv"))


@pytest.fixture(scope="module")
def aachen() -> list[FmRepeater]:
    return parse_csv(fixture_text("dl3el_aachen.csv"))


def by_call(repeaters: list[FmRepeater], call: str, mhz: float) -> FmRepeater:
    return next(r for r in repeaters
                if r.callsign == call and abs(r.tx_mhz - mhz) < 1e-6)


def test_nuernberg_alle_zeilen_geparst(nuernberg):
    # 100 Datenzeilen, alle mit gültigen Frequenzen und Koordinaten
    assert len(nuernberg) == 100


def test_felder_vollstaendig(nuernberg):
    fue = by_call(nuernberg, "DB0FUE", 145.6375)
    assert fue.rx_mhz == 145.0375
    assert fue.ctcss_hz == 88.5
    assert fue.locator == "JN59LL"
    # Entity ohne Schluss-Semikolon: "F&#252rth" → "Fürth"
    assert fue.city == "Fürth, gekoppelt mit 70cm"
    # Bogenminuten: 49°28'N 10°57'E
    assert fue.lat == pytest.approx(49 + 28 / 60)
    assert fue.lng == pytest.approx(10 + 57 / 60)


def test_ctcss_leer_ist_none(nuernberg):
    assert by_call(nuernberg, "DB0UN", 145.650).ctcss_hz is None


def test_gpx_koordinaten_merge(nuernberg):
    coords = parse_gpx_coords(fixture_text("dl3el_nuernberg.gpx"))
    merged = merge_gpx_coords(nuernberg, coords)
    fue = by_call(merged, "DB0FUE", 145.6375)
    assert (fue.lat, fue.lng) == (49.4809, 10.957)
    # Mehrband-Standort: beide Bänder bekommen ihre eigenen Koordinaten
    assert by_call(merged, "DB0FUE", 438.625).lat == 49.4809
    # alle Relais der Antwort haben einen GPX-Treffer bekommen
    assert all(r.lat != pytest.approx(round(r.lat * 60) / 60, abs=1e-9)
               or (r.lat, r.lng) in coords.values() for r in merged)


def test_merge_ohne_gpx_treffer_behaelt_grobe_koordinaten(nuernberg):
    fue = by_call(nuernberg, "DB0FUE", 145.6375)
    merged = merge_gpx_coords([fue], {})
    assert merged[0].lat == pytest.approx(49 + 28 / 60)


def test_dedupe_ueber_call_und_qrg(nuernberg):
    # DL3EL- und fr-Liste überlappen: DB0THM steht als 438,51250 und
    # 438,5125 in der Antwort — nach Dedupe genau einmal, und zwar mit
    # dem CTCSS des vollständigeren fr-Eintrags (der DL3EL-Eintrag
    # kommt zuerst, ist aber tonlos)
    unique = dedupe(nuernberg)
    assert len(unique) == 95
    thm = [r for r in unique if r.callsign == "DB0THM"]
    assert len(thm) == 1
    assert thm[0].ctcss_hz == 88.5


def test_aachen_unbrauchbare_zeilen_verworfen(aachen):
    # 300 Zeilen; 7 ohne parsebare Frequenzen werden verworfen: Input
    # leer (ON0LIL/ON0VOS/ON0LUS), "#WERT!" (ON0SAM), "Simplex" (ON0GB),
    # Input "0,0000" (DB0NPR), Ausgabe "00" (DM0HA)
    assert len(aachen) == 293
    assert not any(r.callsign in ("ON0SAM", "ON0GB", "DB0NPR", "DM0HA")
                   for r in aachen)


def test_aachen_auslandsdaten(aachen):
    # Belgisches Relais mit CTCSS und Bogenminuten-Koordinaten
    tb = by_call(aachen, "ON0TB", 145.6375)
    assert tb.ctcss_hz == 131.8
    assert tb.lat == pytest.approx(50.5, abs=0.01)
    # NL-70cm nutzt +1,6 MHz statt −7,6 MHz: Ablage kommt aus den Daten
    rmd = by_call(aachen, "PI2RMD", 430.3625)
    assert rmd.rx_mhz == pytest.approx(431.9625)


def test_fm_repeater_id_stabil_negativ_und_bandgetrennt():
    a = fm_repeater_id("DB0FUE", 145.6375)
    assert a < 0
    assert a == fm_repeater_id("DB0FUE", 145.6375)
    assert a != fm_repeater_id("DB0FUE", 438.625)


def test_info_spalte_mit_semikolon():
    zeile = ("DB0XX;439,000;431,400;JN59MM;Ort; mit Semikolon;"
             "49&deg;30'N;11&deg;00'E;88,5Hz;;1.00km<br>")
    (r,) = parse_csv(zeile)
    assert r.city == "Ort; mit Semikolon"
    assert r.ctcss_hz == 88.5
    assert r.lat == pytest.approx(49.5)
