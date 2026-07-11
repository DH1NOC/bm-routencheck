"""Digitales Höhenmodell für Sichtlinienprüfungen.

Quelle: 'Terrarium'-Höhenkacheln aus dem AWS-Open-Data-Programm
(s3.amazonaws.com/elevation-tiles-prod, SRTM-basiert, ohne Anmeldung).
Zoom 11 entspricht in Deutschland ca. 50 m Rasterweite. Kacheln werden
auf Platte gecacht; ein Streckenlauf lädt einmalig ~10–30 MB.
"""
from __future__ import annotations

import math
from pathlib import Path

import httpx
import numpy as np
from PIL import Image
from platformdirs import user_cache_dir

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 11
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

EFFECTIVE_EARTH_KM = 6371.0 * 4.0 / 3.0  # 4/3-Erdradius (Funk-Refraktion)
PROFILE_STEP_KM = 0.09                   # Abtastung entlang des Profils
MAX_PROFILE_POINTS = 800


class TerrainError(RuntimeError):
    """Höhendaten nicht verfügbar (Netz/Quelle)."""


class TerrainModel:
    def __init__(self, zoom: int = ZOOM):
        self.zoom = zoom
        self.n = 2 ** zoom
        self.cache_dir = Path(user_cache_dir("bmtools")) / "terrain" / str(zoom)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})
        self._tiles: dict[tuple[int, int], np.ndarray] = {}
        self.tiles_downloaded = 0

    def _tile(self, tx: int, ty: int) -> np.ndarray:
        cached = self._tiles.get((tx, ty))
        if cached is not None:
            return cached
        path = self.cache_dir / f"{tx}_{ty}.png"
        if not path.exists():
            r = self._http.get(TILE_URL.format(z=self.zoom, x=tx, y=ty))
            if r.status_code != 200:
                raise TerrainError(
                    f"Höhenkachel {self.zoom}/{tx}/{ty} nicht ladbar "
                    f"(HTTP {r.status_code})")
            path.write_bytes(r.content)
            self.tiles_downloaded += 1
        img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
        arr = img[:, :, 0] * 256.0 + img[:, :, 1] + img[:, :, 2] / 256.0 - 32768.0
        if len(self._tiles) > 512:  # ~130 MB Deckel für den RAM-Cache
            self._tiles.clear()
        self._tiles[(tx, ty)] = arr
        return arr

    def elevations(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Geländehöhen (m üNN) für Koordinaten-Arrays; Nearest Neighbor —
        bei ~50 m Raster und ~90 m Profilschritt ausreichend."""
        lat_r = np.radians(np.asarray(lats, dtype=np.float64))
        x = (np.asarray(lons, dtype=np.float64) + 180.0) / 360.0 * self.n
        y = (1.0 - np.log(np.tan(lat_r) + 1.0 / np.cos(lat_r)) / math.pi) / 2.0 * self.n
        max_px = self.n * 256 - 1
        px = np.clip((x * 256).astype(np.int64), 0, max_px)
        py = np.clip((y * 256).astype(np.int64), 0, max_px)
        tx, ox = px // 256, px % 256
        ty, oy = py // 256, py % 256
        out = np.empty(px.shape, dtype=np.float32)
        for tile_key in set(zip(tx.tolist(), ty.tolist())):
            mask = (tx == tile_key[0]) & (ty == tile_key[1])
            out[mask] = self._tile(*tile_key)[oy[mask], ox[mask]]
        return out

    def obstruction_m(self, lat_a: float, lon_a: float, agl_a: float,
                      lat_b: float, lon_b: float, agl_b: float,
                      dist_km: float) -> float:
        """Maximale Hindernishöhe (m) über der Sichtlinie A→B.

        <= 0 bedeutet freie Sicht (inkl. 4/3-Erdkrümmung). Endpunkte
        werden ausgenommen (dort steht die Antenne selbst).
        """
        n = min(max(int(dist_km / PROFILE_STEP_KM) + 1, 8), MAX_PROFILE_POINTS)
        f = np.linspace(0.0, 1.0, n)
        lats = lat_a + (lat_b - lat_a) * f
        lons = lon_a + (lon_b - lon_a) * f
        ground = self.elevations(lats, lons)
        a_amsl = float(ground[0]) + agl_a
        b_amsl = float(ground[-1]) + agl_b
        ray = a_amsl + (b_amsl - a_amsl) * f
        d = f * dist_km
        bulge = 1000.0 * d * (dist_km - d) / (2.0 * EFFECTIVE_EARTH_KM)
        clearance = ground[1:-1] + bulge[1:-1] - ray[1:-1]
        return float(clearance.max()) if len(clearance) else -1e9
