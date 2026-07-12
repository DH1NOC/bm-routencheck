"""Gemeinsames Routen-Datenmodell aller Tools (rail, car, bike).

Eine Route ist eine Punktfolge mit benannten Wegpunkten — woher die
Geometrie stammt (Bahnverbindung, Straßenrouting, Komoot, GPX), ist
für die nachgelagerte Pipeline (Erreichbarkeit, Berichte, Karte,
Codeplug) unerheblich.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[float, float]  # (lat, lon)


@dataclass
class Waypoint:
    name: str
    lat: float
    lon: float
    region: str = ""  # z. B. "Deutschland, Bayern, Mittelfranken"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.region})" if self.region else self.name


# Historischer Name aus bm-rail; dort sind Wegpunkte Bahnhöfe.
Station = Waypoint


@dataclass
class Route:
    points: list[Point]
    stations: list[Waypoint]
    legs: list[str] = field(default_factory=list)
    is_interpolated: bool = False


def decode_polyline(encoded: str, precision: int = 7) -> list[Point]:
    """Google-Encoded-Polyline dekodieren (MOTIS: Präzision 7, OSRM: 5)."""
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
