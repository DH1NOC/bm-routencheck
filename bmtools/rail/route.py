"""Ermittlung der Bahnstrecken-Geometrie über Transitous (MOTIS).

Primär: echte Fahrt-Polyline der Verbindung (z. B. ICE Koblenz–Nürnberg).
Fallback: Luftlinien-Interpolation zwischen manuell angegebenen Bahnhöfen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

TRANSITOUS = "https://api.transitous.org/api/v1"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

Point = tuple[float, float]  # (lat, lon)


@dataclass
class Station:
    name: str
    lat: float
    lon: float


@dataclass
class Route:
    points: list[Point]
    stations: list[Station]
    legs: list[str] = field(default_factory=list)  # Beschreibung, z. B. "ICE 27"
    is_interpolated: bool = False


def decode_polyline(encoded: str, precision: int = 7) -> list[Point]:
    """Google-Encoded-Polyline dekodieren (MOTIS nutzt Präzision 7)."""
    factor = 10 ** precision
    points: list[Point] = []
    index = lat = lon = 0
    while index < len(encoded):
        for is_lon in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        points.append((lat / factor, lon / factor))
    return points


class RoutePlanner:
    def __init__(self):
        self._http = httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT})

    def geocode_station(self, query: str) -> Station:
        r = self._http.get(
            f"{TRANSITOUS}/geocode",
            params={"text": query, "type": "STOP", "language": "de"},
        )
        r.raise_for_status()
        results = r.json()
        if not results:
            raise RuntimeError(f"Bahnhof nicht gefunden: {query!r}")
        best = results[0]
        return Station(name=best["name"], lat=best["lat"], lon=best["lon"])

    def _plan_leg(self, frm: Station, to: Station) -> tuple[list[Point], list[str]]:
        r = self._http.get(
            f"{TRANSITOUS}/plan",
            params={
                "fromPlace": f"{frm.lat},{frm.lon}",
                "toPlace": f"{to.lat},{to.lon}",
                "numItineraries": 1,
            },
        )
        r.raise_for_status()
        itineraries = r.json().get("itineraries") or []
        if not itineraries:
            raise RuntimeError(f"Keine Verbindung gefunden: {frm.name} -> {to.name}")
        points: list[Point] = []
        labels: list[str] = []
        for leg in itineraries[0]["legs"]:
            if leg.get("mode") == "WALK":
                continue
            geometry = leg.get("legGeometry") or {}
            decoded = decode_polyline(
                geometry.get("points") or "", int(geometry.get("precision") or 7)
            )
            if points and decoded and points[-1] == decoded[0]:
                decoded = decoded[1:]
            points.extend(decoded)
            label = leg.get("routeShortName") or leg.get("mode") or "?"
            frm_name = (leg.get("from") or {}).get("name", "?")
            to_name = (leg.get("to") or {}).get("name", "?")
            labels.append(f"{label} ({frm_name} -> {to_name})")
        return points, labels

    def route_via_journey(self, station_names: list[str]) -> Route:
        """Echte Fahrt-Geometrie: Verbindungssuche je aufeinanderfolgendem Paar."""
        stations = [self.geocode_station(n) for n in station_names]
        points: list[Point] = []
        legs: list[str] = []
        for frm, to in zip(stations, stations[1:]):
            leg_points, leg_labels = self._plan_leg(frm, to)
            if points and leg_points and points[-1] == leg_points[0]:
                leg_points = leg_points[1:]
            points.extend(leg_points)
            legs.extend(leg_labels)
        if len(points) < 2:
            raise RuntimeError("Verbindung lieferte keine brauchbare Geometrie.")
        return Route(points=points, stations=stations, legs=legs)

    def route_interpolated(self, station_names: list[str]) -> Route:
        """Fallback: Luftlinie zwischen den angegebenen Bahnhöfen."""
        stations = [self.geocode_station(n) for n in station_names]
        if len(stations) < 2:
            raise RuntimeError("Fallback braucht mindestens zwei Bahnhöfe.")
        points = [(s.lat, s.lon) for s in stations]
        return Route(points=points, stations=stations, is_interpolated=True)

    def route(self, station_names: list[str]) -> Route:
        try:
            return self.route_via_journey(station_names)
        except (httpx.HTTPError, RuntimeError) as e:
            print(f"WARNUNG: Verbindungssuche fehlgeschlagen ({e}); "
                  f"nutze Luftlinien-Fallback zwischen den Bahnhöfen.")
            return self.route_interpolated(station_names)
