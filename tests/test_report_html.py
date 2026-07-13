"""Smoke-Test HTML-Bericht: rendert der Bericht vollständige, korrekt
escapte Seiten mit Abschnittstabelle? (Template-Brüche fallen sonst erst
im echten Lauf auf.)"""
from pathlib import Path

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.coverage import estimate_coverage
from bmtools.routelib.model import Route, Station
from bmtools.routelib.report_html import write_html_report
from tests.conftest import make_device, make_result
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
