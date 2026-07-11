"""Interaktive HTML-Karte: Streckenverlauf + Relais-Marker (folium/Leaflet)."""
from __future__ import annotations

import base64
import html
import io
import math
from bisect import bisect_right
from pathlib import Path

import folium
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .corridor import bounding_box, cumulative_km
from .coverage import (DEFAULT_AGL_M, LOS, MARGINAL, MOBILE_HEIGHT_M, SHADOW,
                       CoverageEstimate, horizon_km)
from .report import RepeaterResult, _fmt_subs
from .route import Route
from .terrain import TerrainModel

HEATMAP_BUFFER_KM = 30.0   # Overlay-Rand um die Strecke
HEATMAP_PX_KM = 0.25       # Zielauflösung des Rasters
HEATMAP_MAX_PX = 1800      # Deckel je Achse
# Kräftige Hellblau->Dunkelblau-Rampe (CVD-sicher: eine Farbachse,
# Helligkeit trägt die Information) für 0 / 1 / 2 / >=3 sichtbare Relais
HEATMAP_RAMP = np.array([
    (0, 0, 0, 0),           # keine Abdeckung: transparent
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
background:linear-gradient(90deg,#56B4E9,#0072B2,#03395C)"></span>
Relais-Sichtfeld (dunkler = mehr Relais)
</div>
"""


def _coverage_raster(results: list[RepeaterResult], route: Route,
                     terrain: TerrainModel):
    """Viewsheds aller Korridor-Relais in ein RGBA-Raster aggregieren.

    Ein Blauton, Deckkraft nach Zahl der abdeckenden Relais (sequenzielle
    Ein-Farb-Rampe, farbfehlsichtigkeits-sicher).
    """
    lat_min, lon_min, lat_max, lon_max = bounding_box(
        route.points, HEATMAP_BUFFER_KM)
    mid_lat = (lat_min + lat_max) / 2
    width_km = (lon_max - lon_min) * 111.32 * math.cos(math.radians(mid_lat))
    height_km = (lat_max - lat_min) * 111.32
    w = min(int(width_km / HEATMAP_PX_KM), HEATMAP_MAX_PX)
    h = min(int(height_km / HEATMAP_PX_KM), HEATMAP_MAX_PX)

    # Zeilen direkt in Mercator-Y verteilen: Leaflet spannt das Bild linear
    # in Mercator auf — so bleibt die Geometrie ohne Reprojektion korrekt.
    def merc_y(lat: float) -> float:
        return math.log(math.tan(math.radians(45.0 + lat / 2.0)))

    y_min, y_max = merc_y(lat_min), merc_y(lat_max)

    def to_px(lat: float, lon: float) -> tuple[float, float]:
        x = (lon - lon_min) / (lon_max - lon_min) * (w - 1)
        y = (y_max - merc_y(lat)) / (y_max - y_min) * (h - 1)
        return x, y

    count = np.zeros((h, w), dtype=np.uint8)
    for r in results:
        d = r.device
        agl = d.agl or DEFAULT_AGL_M
        visible, lats, lons = terrain.viewshed(
            d.lat, d.lng, agl, min(horizon_km(agl), 50.0),
            mobile_m=MOBILE_HEIGHT_M)
        layer = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(layer)
        center = to_px(d.lat, d.lng)
        for ray in range(visible.shape[0]):
            vis = visible[ray]
            # sichtbare Läufe entlang des Strahls als Linien zeichnen
            idx = np.flatnonzero(np.diff(np.concatenate(
                ([0], vis.view(np.int8), [0]))))
            for start, stop in zip(idx[::2], idx[1::2]):
                p1 = center if start == 0 else to_px(
                    lats[ray, start], lons[ray, start])
                p2 = to_px(lats[ray, stop - 1], lons[ray, stop - 1])
                draw.line([p1, p2], fill=1, width=2)
        layer = layer.filter(ImageFilter.MaxFilter(3))
        count = count + np.asarray(layer, dtype=np.uint8)

    rgba = HEATMAP_RAMP[np.clip(count, 0, len(HEATMAP_RAMP) - 1)]
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
