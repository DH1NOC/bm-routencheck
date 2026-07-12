"""Interaktive HTML-Karte: Streckenverlauf + Relais-Marker (folium/Leaflet)."""
from __future__ import annotations

import base64
import html
import io
import math
import os
from bisect import bisect_right
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import folium
import numpy as np
from PIL import Image

from . import viewshed_raster
from .corridor import bounding_box, cumulative_km
from .coverage import (DEFAULT_AGL_M, LOS, MARGINAL, SHADOW,
                       CoverageEstimate, horizon_km)
from .report import RepeaterResult, _fmt_subs
from .route import Route
from .terrain import TerrainModel

HEATMAP_PX_KM = 0.25       # Zielauflösung des Rasters
HEATMAP_MAX_PX = 1800      # Deckel je Achse
# Kräftige Hellblau->Dunkelblau-Rampe (CVD-sicher: eine Farbachse,
# Helligkeit trägt die Information): hellste Stufe = nur Grenzbereich
# (Beugung), darüber 1 / 2 / >=3 Relais mit freier Sicht
HEATMAP_RAMP = np.array([
    (0, 0, 0, 0),           # keine Abdeckung: transparent
    (166, 214, 235, 110),   # nur Grenzbereich — #A6D6EB
    (86, 180, 233, 150),    # 1 Relais  — #56B4E9
    (0, 114, 178, 195),     # 2 Relais  — #0072B2
    (3, 57, 92, 230),       # >=3 Relais — #03395C
], dtype=np.uint8)

# Farbenblind-sicher (rechnerisch geprüft: CVD-Delta-E >= 57, Kontrast zur
# Kartenfläche >= 3:1) und redundant über den Linienstil kodiert — Status
# ist nie nur an der Farbe erkennbar.
STATUS_STYLE = {
    LOS: ("#0072B2", None, "Abdeckung wahrscheinlich (Sicht)"),
    MARGINAL: ("#B86200", "10,6", "Grenzbereich (Beugung möglich)"),
    SHADOW: ("#000000", "2,7", "Funkschatten (geschätzt)"),
}


def _legend_line(color: str, dash: str | None) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<svg width="34" height="8" style="vertical-align:middle">'
            f'<line x1="1" y1="4" x2="33" y2="4" stroke="{color}" '
            f'stroke-width="4"{dash_attr}/></svg>')


_LEGEND = f"""
<div style="position:fixed; bottom:16px; left:16px; z-index:9999;
     background:#fff; color:#111; padding:8px 12px; border-radius:6px;
     box-shadow:0 1px 4px #0006; font:13px/1.8 sans-serif;">
<b>Geschätzte DMR-Abdeckung</b><br>
{_legend_line(*STATUS_STYLE[LOS][:2])} Sicht (durchgezogen)<br>
{_legend_line(*STATUS_STYLE[MARGINAL][:2])} Grenzbereich (gestrichelt)<br>
{_legend_line(*STATUS_STYLE[SHADOW][:2])} Schatten (gepunktet)<br>
<span style="display:inline-block;width:30px;height:10px;vertical-align:middle;
background:linear-gradient(90deg,#A6D6EB,#56B4E9,#0072B2,#03395C)"></span>
Relais-Sichtfeld (hellste Stufe: nur Beugung, sonst dunkler = mehr Relais)
</div>
"""


def _coverage_raster(results: list[RepeaterResult], route: Route,
                     terrain: TerrainModel):
    """Viewsheds aller Korridor-Relais in ein RGBA-Raster aggregieren.

    Ein Blauton, Deckkraft nach Zahl der abdeckenden Relais (sequenzielle
    Ein-Farb-Rampe, farbfehlsichtigkeits-sicher).
    """
    # Raster-Ausdehnung: Strecke plus jedes Relais samt seiner vollen
    # Sichtweite — sonst werden Viewsheds am Rasterrand abgeschnitten
    # (weit abseits stehende Relais sogar komplett).
    lat_min, lon_min, lat_max, lon_max = bounding_box(route.points, 2.0)
    for r in results:
        d = r.device
        radius = horizon_km(d.agl or DEFAULT_AGL_M)
        dlat = radius / 111.32
        dlon = radius / (111.32 * math.cos(math.radians(d.lat)))
        lat_min = min(lat_min, d.lat - dlat)
        lat_max = max(lat_max, d.lat + dlat)
        lon_min = min(lon_min, d.lng - dlon)
        lon_max = max(lon_max, d.lng + dlon)
    mid_lat = (lat_min + lat_max) / 2
    width_km = (lon_max - lon_min) * 111.32 * math.cos(math.radians(mid_lat))
    height_km = (lat_max - lat_min) * 111.32
    w = min(int(width_km / HEATMAP_PX_KM), HEATMAP_MAX_PX)
    h = min(int(height_km / HEATMAP_PX_KM), HEATMAP_MAX_PX)

    # Volle Horizont-Reichweite rechnen — dieselbe Grenze wie in der
    # Streckenklassifikation, sonst widersprechen sich Linie und Heatmap
    tasks: list[viewshed_raster.RenderTask] = [
        (r.device.lat, r.device.lng, r.device.agl or DEFAULT_AGL_M,
         w, h, lat_min, lon_min, lat_max, lon_max)
        for r in results]

    # Kacheln aller Sichtfelder vorab in einem Rutsch parallel laden —
    # verhindert bei kaltem Cache doppelte Downloads konkurrierender Worker
    pre_lats, pre_lons = [], []
    for lat, lng, agl, *_ in tasks:
        d_km = np.arange(0.0, horizon_km(agl) + 4.0, 4.0)
        az = np.radians(np.arange(0.0, 360.0, 5.0))
        pre_lats.append((lat + np.outer(np.cos(az), d_km) / 111.32).ravel())
        pre_lons.append((lng + np.outer(np.sin(az), d_km)
                         / (111.32 * math.cos(math.radians(lat)))).ravel())
    terrain.prefetch(np.concatenate(pre_lats), np.concatenate(pre_lons))

    count = np.zeros((h, w), dtype=np.uint8)   # Relais mit freier Sicht
    marginal = np.zeros((h, w), dtype=bool)    # Grenzbereich (Beugung)
    if len(tasks) > 1:
        workers = min(len(tasks), os.cpu_count() or 2)
        with ProcessPoolExecutor(
                max_workers=workers,
                initializer=viewshed_raster.init_worker) as pool:
            rendered = list(pool.map(viewshed_raster.render_relay, tasks))
    else:
        rendered = [viewshed_raster.render_relay(t, terrain) for t in tasks]
    for los, marg_bits in rendered:
        count += los
        marginal |= np.unpackbits(
            marg_bits, count=h * w).reshape(h, w).astype(bool)

    # Rampenindex: 0 = nichts, 1 = nur Grenzbereich, 2..4 = 1/2/>=3 Relais
    index = np.where(count > 0, 1 + np.clip(count, 0, 3),
                     marginal.astype(np.uint8))
    rgba = HEATMAP_RAMP[index]
    # PNG selbst kodieren: branca normalisiert numpy-Arrays kanalweise auf
    # 255 und würde die Farbe verfälschen (Blau -> Cyan)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return uri, [[lat_min, lon_min], [lat_max, lon_max]]


def _coverage_segments(route: Route, coverage: CoverageEstimate):
    """Streckenpunkte zu Abschnitten gleichen Abdeckungsstatus bündeln.

    Liefert (status, punkte, start_km, end_km) je Abschnitt.
    """
    cum = cumulative_km(route.points)
    sample_kms = [s.km for s in coverage.samples]

    def status_at(km: float) -> int:
        idx = bisect_right(sample_kms, km) - 1
        return coverage.samples[max(idx, 0)].status

    segments: list[tuple[int, list, float, float]] = []
    current = status_at(0.0)
    pts = [route.points[0]]
    seg_start = 0.0
    for prev_k, p, k in zip(cum, route.points[1:], cum[1:]):
        s = status_at((prev_k + k) / 2)
        if s == current:
            pts.append(p)
        else:
            segments.append((current, pts, seg_start, prev_k))
            pts = [pts[-1], p]
            seg_start = prev_k
            current = s
    segments.append((current, pts, seg_start, cum[-1]))
    return segments


def _reachable_in_range(coverage: CoverageEstimate, start_km: float,
                        end_km: float, listed: set[str],
                        status: int) -> str:
    """Erreichbare Relais eines Abschnitts als Tooltip-Zusatz.

    * markiert Relais, die nicht in der Ergebnisliste stehen (z. B. wegen
    --corridor-Limit oder weil sie nur grenzwertig erreichbar sind).
    """
    names: set[str] = set()
    unlisted: set[str] = set()
    for s in coverage.samples:
        if start_km - 0.25 <= s.km <= end_km:
            pool = s.los if status == LOS else (s.los + s.marginal)
            for c in pool:
                (names if c in listed else unlisted).add(c)
    parts = sorted(names) + [f"{c}*" for c in sorted(unlisted)]
    if not parts:
        return ""
    suffix = " (* nicht in der Relais-Liste)" if unlisted else ""
    return f" — Relais: {', '.join(parts)}{suffix}"


def write_map(results: list[RepeaterResult], route: Route,
              corridor_km: float, path: Path,
              coverage: CoverageEstimate | None = None,
              terrain: TerrainModel | None = None) -> None:
    lats = [p[0] for p in route.points]
    lons = [p[1] for p in route.points]
    m = folium.Map()
    m.fit_bounds([(min(lats), min(lons)), (max(lats), max(lons))])

    if terrain is not None and results:
        image_uri, bounds = _coverage_raster(results, route, terrain)
        folium.raster_layers.ImageOverlay(
            image=image_uri, bounds=bounds, opacity=0.8,
            name="Relais-Sichtfelder (rechnerisch)",
        ).add_to(m)
        folium.LayerControl().add_to(m)

    if coverage is not None and coverage.samples:
        listed = {r.device.callsign for r in results}
        for status, pts, start_km, end_km in _coverage_segments(route, coverage):
            color, dash, label = STATUS_STYLE[status]
            tooltip = f"km {start_km:.0f}–{end_km:.0f}: {label}"
            if status != SHADOW:
                tooltip += _reachable_in_range(
                    coverage, start_km, end_km, listed, status)
            folium.PolyLine(pts, color=color, weight=5, opacity=0.95,
                            dash_array=dash, tooltip=tooltip).add_to(m)
        m.get_root().html.add_child(folium.Element(_LEGEND))
    else:
        folium.PolyLine(route.points, color="#c00", weight=3,
                        tooltip="Bahnstrecke").add_to(m)
    for s in route.stations:
        folium.Marker(
            (s.lat, s.lon), tooltip=s.name,
            icon=folium.Icon(color="red", icon="train", prefix="fa"),
        ).add_to(m)

    e = html.escape
    for r in results:
        d = r.device
        popup = (
            f"<b>{e(d.callsign)}</b> — {e(d.city)}<br>"
            f"RX <code>{d.tx_mhz:.5f}</code> / TX <code>{d.rx_mhz:.5f}</code> MHz, "
            f"CC{d.colorcode}<br>"
            f"TS1: {e(_fmt_subs(r.profile.for_slot(1)) or '–')}<br>"
            f"TS2: {e(_fmt_subs(r.profile.for_slot(2)) or '–')}<br>"
            f"<small>km {r.hit.chainage_km:.0f}, Abstand "
            f"{r.hit.distance_km:.1f} km, DMR-ID {d.id}</small>"
        )
        folium.Marker(
            (d.lat, d.lng),
            tooltip=f"{d.callsign} ({r.hit.distance_km:.1f} km)",
            popup=folium.Popup(popup, max_width=340),
            icon=folium.Icon(color="blue", icon="tower-cell", prefix="fa"),
        ).add_to(m)

    m.save(str(path))
