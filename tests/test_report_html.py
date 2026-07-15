"""Smoke-Test HTML-Bericht: rendert der Bericht vollständige, korrekt
escapte Seiten mit Abschnittstabelle? (Template-Brüche fallen sonst erst
im echten Lauf auf.)"""
from pathlib import Path

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.coverage import estimate_coverage
from bmtools.routelib.model import Route, Station
from bmtools.routelib.report_html import write_html_report
from tests.conftest import make_device, make_fm_repeater, make_fm_result, make_result
from tests.test_coverage import _route


def test_bericht_enthaelt_relais_abschnitte_und_umlaute(tmp_path: Path):
    points = _route(30.0)
    device = make_device(callsign="DB0MÜ", lat=50.0, lng=8.0, city="Über<stadt>")
    route = Route(points=points,
                  stations=[Station("Nürnberg Hbf", *points[0]),
                            Station("Würzburg Hbf", *points[-1])],
                  legs=["ICE 26 (Nürnberg -> Würzburg)"])
    coverage = estimate_coverage(points, [device], terrain=None)
    results = [make_result(device, [TalkgroupSub(262, 1, "static")])]

    out = tmp_path / "bericht.html"
    write_html_report(results, route, out,
                      tg_names={262: "Deutschland"}, coverage=coverage)
    html = out.read_text(encoding="utf-8")

    assert "DB0MÜ" in html
    assert "Über&lt;stadt&gt;" in html          # HTML-Escaping
    assert "Nürnberg Hbf" in html and "Würzburg Hbf" in html
    assert "Deutschland" in html                # TG-Name aufgelöst
    assert html.count("<html") == 1


def test_bericht_beide_modi_mit_fm_kanaltabelle(tmp_path: Path):
    points = _route(30.0)
    route = Route(points=points,
                  stations=[Station("Start", *points[0]),
                            Station("Ziel", *points[-1])])
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
        make_fm_result(make_fm_repeater(
            callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525,
            ctcss_hz=88.5, locator="JO40AA")),
    ]
    out = tmp_path / "bericht.html"
    write_html_report(results, route, out, modus="beide")
    html = out.read_text(encoding="utf-8")

    assert "DMR- und FM-Relais entlang der Strecke" in html
    assert "relaislisten.darc.de" in html       # Quelle genannt
    assert "DB0FX 70cm" in html                 # FM-Kanalname mit Band
    assert "-7.6 MHz" in html                   # Ablage aus rx−tx berechnet
    assert "88.5" in html
    # Pilotton-Hinweis: Ton wird gesendet, Relais ohne Angabe ggf. Tonruf
    assert "CTCSS-Pilotton" in html
    assert "1750-Hz-Tonruf" in html
    assert "Öffnen mit" in html                 # Spalte je FM-Kanal
    assert "CTCSS (wird gesendet)" in html      # Ton bekannt
    assert "Locator JO40AA" in html
    assert html.count("<html") == 1


def test_bericht_nur_fm_ohne_tg_bloecke(tmp_path: Path):
    points = _route(30.0)
    route = Route(points=points,
                  stations=[Station("Start", *points[0]),
                            Station("Ziel", *points[-1])])
    results = [make_fm_result(make_fm_repeater(
        callsign="DB0FX", tx_mhz=145.6375, rx_mhz=145.0375, ctcss_hz=None))]
    out = tmp_path / "bericht.html"
    write_html_report(results, route, out, modus="fm")
    html = out.read_text(encoding="utf-8")

    assert "FM-Relais entlang der Strecke" in html
    assert "DB0FX 2m" in html
    assert "-0.6 MHz" in html
    # kein CTCSS gelistet → Öffnungsmechanismus ehrlich als offen markiert
    assert "Träger oder 1750-Hz-Tonruf" in html
    assert "Talkgroup" not in html              # keine TG-Blöcke bei FM
    assert "Brandmeister" not in html           # Quelle: nur DL3EL
