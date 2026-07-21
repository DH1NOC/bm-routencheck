"""Tests Kartenbild (U7): Geometrie, Maßstab, Komposition, Kachel-Cache
— ohne Netz (Kachel-Download gestubbt)."""
from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image

from bmtools.routelib import mapimage
from bmtools.routelib.mapimage import (
    KachelLader,
    _massstab_laenge_m,
    _meter_pro_pixel,
    _zoom_fuer_bounds,
    render_kartenbild,
)

BOUNDS = [[50.0, 8.0], [50.2, 8.2]]


def _overlay_uri() -> str:
    buf = io.BytesIO()
    Image.new("RGBA", (2, 2), (0, 114, 178, 120)).save(buf, "PNG")
    return ("data:image/png;base64,"
            + base64.b64encode(buf.getvalue()).decode())


def _bildfarben(bild: Image.Image) -> set[object]:
    farben = bild.getcolors(bild.width * bild.height)
    assert farben is not None
    return {f for _, f in farben}


def _payload() -> dict[str, Any]:
    return {
        "bounds": BOUNDS,
        "stationen": [{"name": "Start", "lat": 50.0, "lon": 8.0},
                      {"name": "Ziel", "lat": 50.2, "lon": 8.2}],
        "stile": {
            "2": {"farbe": "#0072B2", "dash": None, "label": "Sicht"},
            "1": {"farbe": "#B86200", "dash": "10,6", "label": "Grenz"},
            "0": {"farbe": "#000000", "dash": "2,7", "label": "Schatten"},
        },
        "segmente": [
            {"status": "2", "tooltip": "",
             "punkte": [[50.0, 8.0], [50.1, 8.1]]},
            {"status": "1", "tooltip": "",
             "punkte": [[50.1, 8.1], [50.2, 8.2]]},
        ],
        "route": None,
        "overlay": {"uri": _overlay_uri(),
                    "bounds": [[50.05, 8.05], [50.15, 8.15]],
                    "name": "Sichtfelder"},
        "marker": [{"lat": 50.05, "lng": 8.15, "farbe": "fm",
                    "tooltip": "", "popup": ""}],
        "legende": None,
    }


def _stub_download(monkeypatch):
    """Kachel-Download durch einfarbige Kacheln ersetzen (kein Netz)."""
    def fake(self, tx, ty):
        pfad = self._pfad(tx, ty)
        if pfad.exists():
            return
        Image.new("RGB", (256, 256), "#eeeeee").save(pfad)
        with self._lock:
            self.geladen += 1
    monkeypatch.setattr(KachelLader, "_download", fake)


def _lader(monkeypatch, tmp_path, zoom=10) -> KachelLader:
    monkeypatch.setattr(mapimage, "user_cache_dir",
                        lambda name: str(tmp_path))
    _stub_download(monkeypatch)
    return KachelLader(zoom)


# ------------------------------------------------------- Geometrie

def test_zoom_passt_ins_zielmass():
    klein = _zoom_fuer_bounds(BOUNDS, 1600, 1200)
    ganz_de = _zoom_fuer_bounds([[47.3, 5.9], [55.1, 15.0]], 1600, 1200)
    assert ganz_de < klein <= mapimage.MAX_ZOOM  # große Fläche: raus
    for bounds, zoom in ((BOUNDS, klein),
                         ([[47.3, 5.9], [55.1, 15.0]], ganz_de)):
        x0, y1 = mapimage._merc_px(bounds[0][0], bounds[0][1], zoom)
        x1, y0 = mapimage._merc_px(bounds[1][0], bounds[1][1], zoom)
        assert x1 - x0 <= 1600 and y1 - y0 <= 1200
        # eine Stufe näher würde nicht mehr passen (größter Zoom),
        # außer die Kappung greift
        if zoom < mapimage.MAX_ZOOM:
            x0, y1 = mapimage._merc_px(bounds[0][0], bounds[0][1],
                                       zoom + 1)
            x1, y0 = mapimage._merc_px(bounds[1][0], bounds[1][1],
                                       zoom + 1)
            assert x1 - x0 > 1600 or y1 - y0 > 1200


def test_meter_pro_pixel_aequator_zoom0():
    assert abs(_meter_pro_pixel(0.0, 0) - 156543.03) < 1


def test_massstab_runde_laengen():
    assert _massstab_laenge_m(10.0) == 1000       # 1300 m roh -> 1 km
    assert _massstab_laenge_m(3.9) == 500
    assert _massstab_laenge_m(0.2) == 20


# ------------------------------------------------------ Komposition

def test_kartenbild_zeichnet_route_marker_und_beschriftung(
        monkeypatch, tmp_path):
    lader = _lader(monkeypatch, tmp_path)
    bild = render_kartenbild(_payload(), lader=lader)

    assert bild.mode == "RGB"
    farben = _bildfarben(bild)
    assert (0, 114, 178) in farben    # Sicht-Segment (durchgezogen)
    assert (184, 98, 0) in farben     # Grenzbereich-Strichelung
    assert (230, 159, 0) in farben    # FM-Marker
    assert (213, 94, 0) in farben     # Wegpunkt-Marker
    assert (17, 17, 17) in farben     # Maßstab/Attribution
    assert lader.geladen > 0


def test_kachel_cache_wird_wiederverwendet(monkeypatch, tmp_path):
    lader = _lader(monkeypatch, tmp_path)
    meldungen: list[tuple[int, int]] = []
    render_kartenbild(_payload(), lader=lader,
                      tile_progress=lambda f, g: meldungen.append((f, g)))
    assert meldungen[0][0] == 0
    assert meldungen[-1] == (meldungen[-1][1], meldungen[-1][1])

    zweiter = KachelLader(lader.zoom)  # gleicher Cache-Ordner
    render_kartenbild(_payload(), lader=zweiter)
    assert zweiter.geladen == 0        # alles aus dem Disk-Cache


def test_fallback_route_ohne_coverage(monkeypatch, tmp_path):
    lader = _lader(monkeypatch, tmp_path)
    payload = _payload()
    payload["segmente"] = None
    payload["overlay"] = None
    payload["route"] = [[50.0, 8.0], [50.2, 8.2]]
    bild = render_kartenbild(payload, lader=lader)
    assert (204, 0, 0) in _bildfarben(bild)  # rote Fallback-Linie (#c00)
