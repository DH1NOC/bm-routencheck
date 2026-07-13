"""Straßen-Routing (Auto/Rad) über die Wegpunkte eines Google-Links.

Primärquelle: FOSSGIS-OSRM (routing.openstreetmap.de, keyless,
verifiziert 2026-07-12) — beide Profile, Via-Punkte in einem Request.
Fallback-Kette bei Ausfall: Transitous directModes (je Wegpunkt-Paar,
verifiziert 2026-07-13) -> Luftlinie mit Warnung.

Komoot-Touren und GPX-Dateien umgehen das Routing komplett:
route_from_track() macht aus fertiger Geometrie direkt ein Route-Objekt.
"""
from __future__ import annotations

from typing import Callable

import httpx

from bmtools.routelib.model import Point, Route, Waypoint, decode_polyline

OSRM_URL = ("https://routing.openstreetmap.de/routed-{profile}"
            "/route/v1/driving/{coords}")
TRANSITOUS_PLAN = "https://api.transitous.org/api/v1/plan"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

OSRM_PROFILE = {"car": "car", "bike": "bike", "foot": "foot"}
TRANSITOUS_MODE = {"car": "CAR", "bike": "BIKE", "foot": "WALK"}
MODE_LABEL = {"car": "Auto", "bike": "Rad", "foot": "Fuß"}

Warn = Callable[[str], None]


class RoutingError(RuntimeError):
    """Routing-Backend lieferte keine brauchbare Route."""


def _fmt_h(seconds: float) -> str:
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}:{m:02d} h"


def _check_waypoints(waypoints: list[Waypoint], mode: str) -> None:
    if mode not in OSRM_PROFILE:
        raise ValueError(f"Unbekanntes Profil: {mode!r}")
    if len(waypoints) < 2:
        raise ValueError("Routing braucht mindestens Start und Ziel.")
    unresolved = [w.name for w in waypoints
                  if w.lat is None or w.lon is None]
    if unresolved:  # Geocoding ist Sache des Aufrufers (CLI)
        raise ValueError(f"Wegpunkte ohne Koordinaten: {unresolved}")


def route_waypoints(waypoints: list[Waypoint], mode: str,
                    http: httpx.Client | None = None,
                    warn: Warn = print) -> Route:
    """Route über alle Wegpunkte; fällt gestuft zurück statt zu scheitern."""
    _check_waypoints(waypoints, mode)
    own_client = http is None
    http = http or httpx.Client(timeout=60,
                                headers={"User-Agent": USER_AGENT})
    try:
        try:
            return _route_osrm(waypoints, mode, http)
        except (httpx.HTTPError, RoutingError) as e:
            warn(f"WARNUNG: OSRM-Routing fehlgeschlagen ({e}); "
                 f"versuche Transitous.")
        try:
            return _route_transitous(waypoints, mode, http)
        except (httpx.HTTPError, RoutingError) as e:
            warn(f"WARNUNG: Transitous-Routing fehlgeschlagen ({e}); "
                 f"nutze Luftlinie zwischen den Wegpunkten — Ergebnis nur "
                 f"als grobe Orientierung brauchbar!")
        return Route(points=[(w.lat, w.lon) for w in waypoints],
                     stations=list(waypoints),
                     legs=["Luftlinie (Routing nicht verfügbar)"],
                     is_interpolated=True)
    finally:
        if own_client:
            http.close()


def _route_osrm(waypoints: list[Waypoint], mode: str,
                http: httpx.Client) -> Route:
    coords = ";".join(f"{w.lon:.6f},{w.lat:.6f}" for w in waypoints)
    r = http.get(
        OSRM_URL.format(profile=OSRM_PROFILE[mode], coords=coords),
        params={"overview": "full", "geometries": "polyline"})
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM: {data.get('code')} "
                           f"{data.get('message', '')}".strip())
    route = data["routes"][0]
    points = decode_polyline(route["geometry"], precision=5)
    if len(points) < 2:
        raise RoutingError("OSRM lieferte keine Geometrie.")
    label = (f"{MODE_LABEL[mode]}-Route (OSRM/OpenStreetMap): "
             f"{route['distance'] / 1000:.0f} km, "
             f"{_fmt_h(route['duration'])}")
    return Route(points=points, stations=list(waypoints), legs=[label])


def _route_transitous(waypoints: list[Waypoint], mode: str,
                      http: httpx.Client) -> Route:
    """Fallback: Street-Routing von Transitous, je Wegpunkt-Paar ein
    Request (directModes kennt keine Via-Punkte)."""
    points: list[Point] = []
    dist_m = 0.0
    dur_s = 0.0
    for frm, to in zip(waypoints, waypoints[1:]):
        r = http.get(TRANSITOUS_PLAN, params={
            "fromPlace": f"{frm.lat},{frm.lon}",
            "toPlace": f"{to.lat},{to.lon}",
            "directModes": TRANSITOUS_MODE[mode],
            "transitModes": "",
            # Default-Limit filtert lange Abschnitte weg (verifiziert
            # 2026-07-13: 15 km Rad ohne maxDirectTime -> leer)
            "maxDirectTime": 86400,
        })
        r.raise_for_status()
        direct = r.json().get("direct") or []
        if not direct:
            raise RoutingError(
                f"Transitous: keine Direktroute {frm.name} -> {to.name}.")
        dur_s += float(direct[0].get("duration") or 0)
        for leg in direct[0]["legs"]:
            g = leg.get("legGeometry") or {}
            seg = decode_polyline(g.get("points") or "",
                                  int(g.get("precision") or 7))
            if points and seg and points[-1] == seg[0]:
                seg = seg[1:]
            points.extend(seg)
            dist_m += float(leg.get("distance") or 0)
    if len(points) < 2:
        raise RoutingError("Transitous lieferte keine Geometrie.")
    label = (f"{MODE_LABEL[mode]}-Route (Transitous, Ersatz für OSRM): "
             f"{dist_m / 1000:.0f} km, {_fmt_h(dur_s)}")
    return Route(points=points, stations=list(waypoints), legs=[label])


def route_from_track(points: list[Point], label: str,
                     start_name: str = "Start",
                     end_name: str = "Ziel") -> Route:
    """Fertige Geometrie (Komoot, GPX) als Route-Objekt."""
    if len(points) < 2:
        raise ValueError("Track braucht mindestens zwei Punkte.")
    stations = [Waypoint(start_name, *points[0]),
                Waypoint(end_name, *points[-1])]
    return Route(points=list(points), stations=stations, legs=[label])
