"""Interaktive HTML-Karte: Streckenverlauf + Relais-Marker (folium/Leaflet)."""
from __future__ import annotations

import html
from bisect import bisect_right
from pathlib import Path

import folium

from .corridor import cumulative_km
from .coverage import LOS, MARGINAL, SHADOW, CoverageEstimate
from .report import RepeaterResult, _fmt_subs
from .route import Route

STATUS_STYLE = {
    LOS: ("#2e7d32", "Abdeckung wahrscheinlich (Sicht)"),
    MARGINAL: ("#f9a825", "Grenzbereich (Beugung möglich)"),
    SHADOW: ("#c62828", "Funkschatten (geschätzt)"),
}

_LEGEND = """
<div style="position:fixed; bottom:16px; left:16px; z-index:9999;
     background:#fff; color:#222; padding:8px 12px; border-radius:6px;
     box-shadow:0 1px 4px #0006; font:13px/1.6 sans-serif;">
<b>Geschätzte DMR-Abdeckung</b><br>
<span style="color:#2e7d32;">■</span> Sicht &nbsp;
<span style="color:#f9a825;">■</span> Grenzbereich &nbsp;
<span style="color:#c62828;">■</span> Schatten
</div>
"""


def _coverage_segments(route: Route, coverage: CoverageEstimate):
    """Streckenpunkte zu Abschnitten gleichen Abdeckungsstatus bündeln."""
    cum = cumulative_km(route.points)
    sample_kms = [k for k, _ in coverage.samples]
    statuses = [s for _, s in coverage.samples]

    def status_at(km: float) -> int:
        idx = bisect_right(sample_kms, km) - 1
        return statuses[max(idx, 0)]

    segments: list[tuple[int, list]] = []
    current = status_at(0.0)
    pts = [route.points[0]]
    for prev_k, p, k in zip(cum, route.points[1:], cum[1:]):
        s = status_at((prev_k + k) / 2)
        if s == current:
            pts.append(p)
        else:
            segments.append((current, pts))
            pts = [pts[-1], p]
            current = s
    segments.append((current, pts))
    return segments


def write_map(results: list[RepeaterResult], route: Route,
              corridor_km: float, path: Path,
              coverage: CoverageEstimate | None = None) -> None:
    lats = [p[0] for p in route.points]
    lons = [p[1] for p in route.points]
    m = folium.Map()
    m.fit_bounds([(min(lats), min(lons)), (max(lats), max(lons))])

    if coverage is not None and coverage.samples:
        for status, pts in _coverage_segments(route, coverage):
            color, label = STATUS_STYLE[status]
            folium.PolyLine(pts, color=color, weight=5, opacity=0.9,
                            tooltip=label).add_to(m)
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
