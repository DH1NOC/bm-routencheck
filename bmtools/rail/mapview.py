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
{_legend_line(*STATUS_STYLE[SHADOW][:2])} Schatten (gepunktet)
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
            color, dash, label = STATUS_STYLE[status]
            folium.PolyLine(pts, color=color, weight=5, opacity=0.95,
                            dash_array=dash, tooltip=label).add_to(m)
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
