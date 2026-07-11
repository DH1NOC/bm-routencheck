"""Interaktive HTML-Karte: Streckenverlauf + Relais-Marker (folium/Leaflet)."""
from __future__ import annotations

import html
from pathlib import Path

import folium

from .report import RepeaterResult, _fmt_subs
from .route import Route


def write_map(results: list[RepeaterResult], route: Route,
              corridor_km: float, path: Path) -> None:
    lats = [p[0] for p in route.points]
    lons = [p[1] for p in route.points]
    m = folium.Map()
    m.fit_bounds([(min(lats), min(lons)), (max(lats), max(lons))])

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
