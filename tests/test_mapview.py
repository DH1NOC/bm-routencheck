"""Smoke-Test Karte: FM-Marker (orange, CVD-sicher), Modus-Popups,
Sichtfeld-Fortschritt."""
from pathlib import Path

import numpy as np

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib import terrain as terrain_mod
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
        make_fm_result(make_fm_repeater(
            callsign="DB0OT", tx_mhz=145.6, rx_mhz=145.0, ctcss_hz=None)),
    ]
    out = tmp_path / "karte.html"
    write_map(results, route, out)
    html = out.read_text(encoding="utf-8")

    assert "orange" in html                    # FM-Marker (kein Grün: CVD)
    assert "CTCSS 88.5 Hz (wird gesendet)" in html
    # ohne CTCSS-Angabe: Öffnungsweg ehrlich offen lassen
    assert "Träger oder Tonruf 1750 Hz" in html
    assert "Ablage -7.6 MHz" in html
    assert "Locator JO40AA" in html
    assert "DB0FX (5.0 km) — FM" in html        # Tooltip mit Modus-Zusatz
    assert "TS1" in html                        # DMR-Popup weiter vollständig


def test_sichtfelder_melden_fortschritt(tmp_path: Path, monkeypatch):
    """Ein Relais (sequenzieller Pfad, kein Prozesspool) auf flachem
    Stub-Gelände: viewshed_progress meldet (0, 1) und (1, 1)."""
    monkeypatch.setattr(terrain_mod, "user_cache_dir",
                        lambda name: str(tmp_path))
    terrain = terrain_mod.TerrainModel()
    monkeypatch.setattr(
        terrain, "elevations",
        lambda lats, lons: np.zeros(np.shape(lats), dtype=np.float32))
    monkeypatch.setattr(terrain, "prefetch",
                        lambda lats, lons, progress=None: None)

    points = [(50.0, 8.0), (50.1, 8.1), (50.2, 8.2)]
    route = Route(points=points, stations=[Station("Start", *points[0])])
    results = [make_result(make_device(), [TalkgroupSub(262, 1, "static")])]
    meldungen: list[tuple[int, int]] = []
    out = tmp_path / "karte.html"
    write_map(results, route, out, terrain=terrain,
              viewshed_progress=lambda f, g: meldungen.append((f, g)))
    assert meldungen == [(0, 1), (1, 1)]
    assert "data:image/png" in out.read_text(encoding="utf-8")  # Overlay da
