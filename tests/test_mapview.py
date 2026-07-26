"""Smoke-Test Karte: FM-Marker (orange, CVD-sicher), Modus-Popups,
Sichtfeld-Fortschritt, GUI-Kartendaten (U4)."""
import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib import mapview as mapview_mod
from bmtools.routelib import terrain as terrain_mod
from bmtools.routelib.mapview import karten_daten, write_map
from bmtools.routelib.model import Route, Station
from tests.conftest import make_device, make_fm_repeater, make_fm_result, make_result


def kunstgelaende(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Zerklüftetes, aber deterministisches Kunstgelände.

    Flaches Stub-Gelände liefert nur volle Sichtkreise — hier entstehen
    echte Schatten und Grenzbereiche, damit Zuschnitt und Aggregation
    der Sichtfelder überhaupt etwas zu tun haben.
    """
    la = np.asarray(lats, dtype=np.float64)
    lo = np.asarray(lons, dtype=np.float64)
    h = (400.0 * np.sin(la * 37.0) * np.cos(lo * 41.0)
         + 250.0 * np.sin(la * 113.0 + lo * 97.0)
         + 120.0 * np.cos(la * 211.0 - lo * 173.0))
    return h.astype(np.float32)


def kunstgelaende_modell(tmp_path: Path, monkeypatch) -> terrain_mod.TerrainModel:
    monkeypatch.setattr(terrain_mod, "user_cache_dir", lambda name: str(tmp_path))
    terrain = terrain_mod.TerrainModel()
    monkeypatch.setattr(terrain, "elevations", kunstgelaende)
    monkeypatch.setattr(terrain, "prefetch",
                        lambda lats, lons, progress=None: None)
    return terrain


def serialisiere_pool(monkeypatch, terrain: terrain_mod.TerrainModel) -> None:
    """Prozesspool durch einen seriellen Ersatz tauschen.

    Die echten Worker bauen über init_worker() ein eigenes TerrainModel
    und laden Höhenkacheln aus dem Netz — im Test unerwünscht. Geprüft
    werden soll die Aggregation, nicht das Forken.
    """
    class Ergebnis:
        def __init__(self, wert):
            self._wert = wert

        def result(self):
            return self._wert

    class SerielleAusfuehrung:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, *args):
            return Ergebnis(fn(*args, terrain))

    monkeypatch.setattr(mapview_mod, "ProcessPoolExecutor", SerielleAusfuehrung)
    monkeypatch.setattr(mapview_mod, "as_completed", lambda fs: fs)


def overlay_pixel(uri: str) -> np.ndarray:
    """RGBA-Array eines Overlay-Daten-URI."""
    roh = base64.b64decode(uri.partition("base64,")[2])
    return np.asarray(Image.open(io.BytesIO(roh)).convert("RGBA"))


@pytest.fixture
def sichtfeld_szenario(tmp_path: Path, monkeypatch):
    """Drei Relais auf Kunstgelände entlang einer kurzen Route."""
    terrain = kunstgelaende_modell(tmp_path, monkeypatch)
    serialisiere_pool(monkeypatch, terrain)
    points = [(50.0 + i * 0.02, 8.0 + i * 0.03) for i in range(12)]
    route = Route(points=points, stations=[Station("Start", *points[0])])
    results = [
        make_result(make_device(id=1, callsign="DB0AA", lat=50.05, lng=8.05)),
        make_result(make_device(id=2, callsign="DB0BB", lat=50.14, lng=8.19)),
        make_result(make_device(id=3, callsign="DB0CC", lat=50.20, lng=8.30)),
    ]
    return terrain, route, results


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


def test_karten_daten_fuer_die_gui(tmp_path: Path):
    """U4: karten_daten liefert dieselben Inhalte wie die folium-Karte
    als JSON-fähiges Dict (Marker-Popups aus denselben Helfern)."""
    points = [(50.0, 8.0), (50.123456789, 8.1), (50.2, 8.2)]
    route = Route(points=points,
                  stations=[Station("Start", *points[0]),
                            Station("Ziel", *points[-1])])
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
        make_fm_result(make_fm_repeater(
            callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525,
            ctcss_hz=88.5, locator="JO40AA")),
    ]

    daten = karten_daten(results, route, route_label="Bahnstrecke",
                         waypoint_icon="train")

    json.dumps(daten)  # muss ohne Sonderbehandlung serialisierbar sein
    assert [e["name"] for e in daten["ebenen"]] == [
        "OpenStreetMap", "Carto (Ausweichkarte)"]
    assert daten["bounds"] == [[50.0, 8.0], [50.2, 8.2]]
    assert daten["stations_icon"] == "train"
    assert [s["name"] for s in daten["stationen"]] == ["Start", "Ziel"]
    # Ohne Coverage: einfache Routenlinie, gerundet auf 5 Stellen
    assert daten["segmente"] is None and daten["legende"] is None
    assert daten["route"][1] == [50.12346, 8.1]
    farben = {m["farbe"] for m in daten["marker"]}
    assert farben == {"dmr", "fm"}
    fm_popup = next(m["popup"] for m in daten["marker"]
                    if m["farbe"] == "fm")
    assert "CTCSS 88.5 Hz (wird gesendet)" in fm_popup
    assert "Locator JO40AA" in fm_popup


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


# Stand vor dem Zuschnitt-Refactor (render_relay liefert seit dem nur
# noch die belegte Pixel-Bbox statt des vollen Rasters). Gehasht wird
# das dekodierte RGBA-Array, nicht die PNG-Bytes: zlib-Ausgaben sind
# über Versionen und Plattformen hinweg nicht garantiert gleich, die
# Pixel dagegen reine numpy-Rechnung.
SUMMENKARTE_SHA256 = "39bf9d136e83cb253e21a406993e572819112768500d4760c922134b5af6da10"


def test_summenkarte_bleibt_unveraendert(sichtfeld_szenario, tmp_path: Path):
    """Regressionsanker der aggregierten Sichtfeld-Heatmap.

    Schlägt dieser Test fehl, hat sich das gerenderte Sichtfeld-Overlay
    geändert. War das beabsichtigt (Rampe, Auflösung, Viewshed-Modell),
    ist der Hash bewusst neu zu setzen — dann bitte im Commit begründen,
    warum sich die Abdeckungsdarstellung ändern durfte.
    """
    terrain, route, results = sichtfeld_szenario
    overlay = write_map(results, route, tmp_path / "karte.html",
                        terrain=terrain)
    assert overlay is not None
    pixel = overlay_pixel(overlay[0])
    assert hashlib.sha256(pixel.tobytes()).hexdigest() == SUMMENKARTE_SHA256
