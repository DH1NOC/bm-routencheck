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

    def viewshed(self, lat: float, lon: float, agl_m: float, max_km: float,
                 mobile_m: float = 2.0, n_rays: int = 720,
                 step_km: float = PROFILE_STEP_KM,
                 marginal_m: float = 30.0):
        """Sichtfeld eines Relais: welche Punkte im Umkreis sind funktech-
        nisch sichtbar (Empfänger in `mobile_m` Höhe, 4/3-Erdradius)?

        Klassischer Viewshed über Radialstrahlen: je Strahl wird der
        laufende maximale Geländewinkel mitgeführt; sichtbar ist, wessen
        Empfangswinkel darüber liegt. Zusätzlich wird der Grenzbereich
        (Hindernis <= marginal_m über der Sichtlinie, Beugung plausibel)
        ausgewiesen — genähert über das winkelmaximale Hindernis des
        Strahls; weitere, flachere Hindernisse bleiben unberücksichtigt,
        die Schätzung ist also leicht optimistisch.

        Returns: (level, lats, lons) — Arrays der Form (n_rays, n_steps);
        level: 2 = Sicht, 1 = Grenzbereich, 0 = Schatten.
        """
        n_steps = max(int(max_km / step_km), 8)
        d = np.arange(1, n_steps + 1, dtype=np.float64) * step_km  # (S,)
        az = np.radians(np.linspace(0.0, 360.0, n_rays, endpoint=False))  # (R,)
        dlat = (d[None, :] * np.cos(az)[:, None]) / 111.32
        dlon = (d[None, :] * np.sin(az)[:, None]) / (
            111.32 * math.cos(math.radians(lat)))
        lats = lat + dlat
        lons = lon + dlon
        ground = self.elevations(lats.ravel(), lons.ravel()).reshape(lats.shape)
        antenna = float(self.elevations(
            np.array([lat]), np.array([lon]))[0]) + agl_m
        drop = 1000.0 * d ** 2 / (2.0 * EFFECTIVE_EARTH_KM)  # (S,) in m
        dist_m = d[None, :] * 1000.0
        terrain_angle = (ground - drop[None, :] - antenna) / dist_m
        rx_angle = (ground + mobile_m - drop[None, :] - antenna) / dist_m
        running_max = np.maximum.accumulate(terrain_angle, axis=1)
        prev_max = np.concatenate(
            [np.full((n_rays, 1), -np.inf), running_max[:, :-1]], axis=1)
        # Abstand des maßgeblichen Hindernisses mitführen: Höhe über der
        # Sichtlinie = d_Hindernis * (Hinderniswinkel - Empfangswinkel)
        steps = np.arange(n_steps)
        obs_idx = np.maximum.accumulate(
            np.where(terrain_angle >= running_max, steps[None, :], 0), axis=1)
        prev_obs_idx = np.concatenate(
            [np.zeros((n_rays, 1), dtype=np.int64), obs_idx[:, :-1]], axis=1)
        obstruction = 1000.0 * d[prev_obs_idx] * (prev_max - rx_angle)
        level = np.where(rx_angle >= prev_max, 2,
                         np.where(obstruction <= marginal_m, 1, 0)
                         ).astype(np.uint8)
        return level, lats, lons

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
