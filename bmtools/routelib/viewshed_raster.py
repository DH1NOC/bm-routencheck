"""Viewshed-Rasterisierung eines Relais — prozess-pool-tauglich.

Eigenes Modul, damit die Worker-Prozesse des Karten-Renderings nur
numpy/PIL/httpx importieren und nicht das schwere folium-Paket.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .coverage import MARGINAL_OBSTRUCTION_M, MOBILE_HEIGHT_M, horizon_km
from .terrain import TerrainModel

# Ein TerrainModel je Worker-Prozess (der HTTP-Client ist nicht
# picklebar); der Kachel-Disk-Cache wird zwischen den Prozessen geteilt.
_terrain: TerrainModel | None = None

# Aufgabe: (lat, lng, agl_m, w, h, lat_min, lon_min, lat_max, lon_max)
RenderTask = tuple[float, float, float, int, int, float, float, float, float]

# Ergebnis: (los, marginal_bits, bbox) — auf die belegte Pixel-Bbox
# (y0, y1, x0, x1) des globalen Rasters zugeschnitten, bbox=None bei
# leerem Sichtfeld.
Bbox = tuple[int, int, int, int]
RenderResult = tuple[np.ndarray, np.ndarray, "Bbox | None"]


def init_worker() -> None:
    global _terrain
    _terrain = TerrainModel()


def merc_y(lat: float) -> float:
    return math.log(math.tan(math.radians(45.0 + lat / 2.0)))


def render_relay(task: RenderTask, terrain: TerrainModel | None = None,
                 ) -> RenderResult:
    """Sicht- und Grenzbereichs-Layer eines Relais ins Rasterbild zeichnen.

    Zeilen des Rasters liegen in Mercator-Y (Leaflet spannt ImageOverlays
    linear in Mercator auf).

    Returns (los, marginal_bits, bbox): uint8-Layer (0/1) und
    np.packbits-komprimierte Grenzbereichs-Maske, beide auf die belegte
    Pixel-Bbox (y0, y1, x0, x1) des globalen (h, w)-Rasters
    zugeschnitten; bbox=None, wenn das Sichtfeld leer ist.

    Der Zuschnitt hält die Rückgabe klein: ein Sichtfeld belegt nur den
    Umkreis seines Horizonts, das volle Raster wären bei
    HEATMAP_MAX_PX 3,2 MB je Relais durch die Prozesspool-Pipe.
    """
    lat, lng, agl, w, h, lat_min, lon_min, lat_max, lon_max = task
    t = terrain if terrain is not None else _terrain
    assert t is not None, "Worker ohne init_worker() gestartet"
    y_min, y_max = merc_y(lat_min), merc_y(lat_max)

    def to_px(la: float, lo: float) -> tuple[float, float]:
        x = (lo - lon_min) / (lon_max - lon_min) * (w - 1)
        y = (y_max - merc_y(la)) / (y_max - y_min) * (h - 1)
        return x, y

    level, lats, lons = t.viewshed(lat, lng, agl, horizon_km(agl),
                                   mobile_m=MOBILE_HEIGHT_M,
                                   marginal_m=MARGINAL_OBSTRUCTION_M)
    center = to_px(lat, lng)
    layers = {2: Image.new("L", (w, h), 0), 1: Image.new("L", (w, h), 0)}
    for lvl, img in layers.items():
        draw = ImageDraw.Draw(img)
        mask = level == lvl
        for ray in range(mask.shape[0]):
            # Läufe der Stufe entlang des Strahls als Linien zeichnen
            idx = np.flatnonzero(np.diff(np.concatenate(
                ([0], mask[ray].view(np.int8), [0]))))
            for start, stop in zip(idx[::2], idx[1::2], strict=True):
                p1 = center if start == 0 else to_px(
                    lats[ray, start], lons[ray, start])
                p2 = to_px(lats[ray, stop - 1], lons[ray, stop - 1])
                draw.line([p1, p2], fill=1, width=2)
    # Erst filtern, dann zuschneiden: MaxFilter(3) verbreitert die
    # gezeichneten Läufe um ein Pixel — ein vorheriger Zuschnitt würde
    # den Rand des Sichtfelds abschneiden.
    los = np.asarray(layers[2].filter(ImageFilter.MaxFilter(3)),
                     dtype=np.uint8)
    marg = np.asarray(layers[1].filter(ImageFilter.MaxFilter(3)),
                      dtype=bool)
    zeilen = np.flatnonzero(los.any(axis=1) | marg.any(axis=1))
    spalten = np.flatnonzero(los.any(axis=0) | marg.any(axis=0))
    if not len(zeilen):
        # Leeres Sichtfeld (Relais außerhalb des Rasters, komplett
        # verschattet) — die Aufrufer überspringen es
        return (np.zeros((0, 0), dtype=np.uint8),
                np.zeros(0, dtype=np.uint8), None)
    y0, y1 = int(zeilen[0]), int(zeilen[-1]) + 1
    x0, x1 = int(spalten[0]), int(spalten[-1]) + 1
    return (los[y0:y1, x0:x1], np.packbits(marg[y0:y1, x0:x1]),
            (y0, y1, x0, x1))
