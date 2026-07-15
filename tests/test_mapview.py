"""Smoke-Test Karte: FM-Marker (orange, CVD-sicher) und Modus-Popups."""
from pathlib import Path

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.mapview import write_map
from bmtools.routelib.model import Route, Station
from tests.conftest import make_device, make_fm_repeater, make_fm_result, make_result


def test_karte_gemischt_faerbt_fm_orange(tmp_path: Path):
    points = [(50.0, 8.0), (50.1, 8.1), (50.2, 8.2)]
    route = Route(points=points,
                  stations=[Station("Start", *points[0]),
                            Station("Ziel", *points[-1])])
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
        make_fm_result(make_fm_repeater(
            callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525,
            ctcss_hz=88.5, locator="JO40AA")),
    ]
    out = tmp_path / "karte.html"
    write_map(results, route, out)
    html = out.read_text(encoding="utf-8")

    assert "orange" in html                    # FM-Marker (kein Grün: CVD)
    assert "CTCSS 88.5 Hz" in html
    assert "Ablage -7.6 MHz" in html
    assert "Locator JO40AA" in html
    assert "DB0FX (5.0 km) — FM" in html        # Tooltip mit Modus-Zusatz
    assert "TS1" in html                        # DMR-Popup weiter vollständig
