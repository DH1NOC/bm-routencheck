"""Geometrie: Distanz von Relais-Standorten zur Streckengeometrie.

Bewusst ohne GIS-Abhängigkeiten: segmentweise Distanzberechnung über eine
lokale äquirektangulare Projektion — bei Korridorbreiten bis ~50 km mehr
als genau genug.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from bmtools.bm_api.models import Device

EARTH_RADIUS_KM = 6371.0

Point = tuple[float, float]  # (lat, lon)


def _project_km(p: Point, ref_lat_deg: float) -> tuple[float, float]:
    """Grad → km in lokaler Ebene (x=Ost, y=Nord)."""
    k = math.pi / 180.0 * EARTH_RADIUS_KM
    return (p[1] * k * math.cos(math.radians(ref_lat_deg)), p[0] * k)


def point_to_segment_km(p: Point, a: Point, b: Point) -> tuple[float, float]:
    """(Abstand in km, Anteil t in [0,1] entlang des Segments a->b)."""
    ref = (a[0] + b[0]) / 2
    px, py = _project_km(p, ref)
    ax, ay = _project_km(a, ref)
    bx, by = _project_km(b, ref)
    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), t


def cumulative_km(points: list[Point]) -> list[float]:
    """Streckenkilometer je Punkt (Start = 0)."""
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        ref = (a[0] + b[0]) / 2
        ax, ay = _project_km(a, ref)
        bx, by = _project_km(b, ref)
        cum.append(cum[-1] + math.hypot(bx - ax, by - ay))
    return cum


def bounding_box(points: list[Point], buffer_km: float) -> tuple[float, float, float, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    dlat = buffer_km / 111.0
    dlon = buffer_km / (111.0 * math.cos(math.radians(sum(lats) / len(lats))))
    return (min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon)


@dataclass
class CorridorHit:
    device: Device
    distance_km: float   # Abstand des Relais zur Strecke
    chainage_km: float   # Streckenkilometer ab Startbahnhof


def find_in_corridor(
    devices: list[Device], points: list[Point], corridor_km: float
) -> list[CorridorHit]:
    """Alle Geräte mit Abstand <= corridor_km, sortiert nach Streckenkilometer."""
    lat_min, lon_min, lat_max, lon_max = bounding_box(points, corridor_km)
    cum = cumulative_km(points)
    hits: list[CorridorHit] = []
    for dev in devices:
        if dev.lat is None or dev.lng is None:
            continue
        if not (lat_min <= dev.lat <= lat_max and lon_min <= dev.lng <= lon_max):
            continue
        p = (dev.lat, dev.lng)
        best_dist = math.inf
        best_chainage = 0.0
        for i, (a, b) in enumerate(zip(points, points[1:])):
            # Grobfilter: Segment ganz außer Reichweite überspringen
            if (
                min(a[0], b[0]) - corridor_km / 111.0 > dev.lat
                or max(a[0], b[0]) + corridor_km / 111.0 < dev.lat
            ):
                continue
            dist, t = point_to_segment_km(p, a, b)
            if dist < best_dist:
                best_dist = dist
                best_chainage = cum[i] + t * (cum[i + 1] - cum[i])
        if best_dist <= corridor_km:
            hits.append(CorridorHit(dev, best_dist, best_chainage))
    hits.sort(key=lambda h: h.chainage_km)
    return hits
