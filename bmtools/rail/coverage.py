"""Abdeckungsschätzung entlang der Strecke.

Zwei Modelle:
- Horizont (Fallback): Sichtlinien-Funkhorizont je Relais aus der
  Antennenhöhe, ohne Gelände — in Tälern optimistisch.
- Gelände (Standard): echtes Höhenprofil je Streckenpunkt→Relais mit
  4/3-Erdradius. Dreistufig: Sicht / Grenzbereich (Hindernis knapp,
  Beugung wahrscheinlich) / Schatten.

Gerechnet wird gegen alle online gemeldeten Repeater der Umgebung,
nicht nur gegen die Treffer im Suchkorridor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from bmtools.bm_api.models import Device
from .corridor import bounding_box, cumulative_km, Point
from .terrain import TerrainModel

MOBILE_HEIGHT_M = 2.0     # Handfunkgerät im Zug
DEFAULT_AGL_M = 15.0      # Annahme, wenn Antennenhöhe unbekannt
SAMPLE_KM = 0.5           # Abtastschritt entlang der Strecke
MIN_GAP_KM = 5.0          # kleinere Lücken werden nicht einzeln gelistet
BBOX_BUFFER_KM = 60.0     # Relais-Vorfilter um die Strecke
MARGINAL_OBSTRUCTION_M = 30.0  # Hindernis bis hierhin: "Grenzbereich"

LOS, MARGINAL, SHADOW = 2, 1, 0


@dataclass(frozen=True)
class SamplePoint:
    km: float
    status: int
    los: tuple[str, ...]       # Rufzeichen mit Sichtkontakt
    marginal: tuple[str, ...]  # Rufzeichen im Grenzbereich


def horizon_km(agl_m: float) -> float:
    """Radiohorizont in km für gegebene Antennenhöhe (AGL, Meter)."""
    return 4.12 * (math.sqrt(max(agl_m, 3.0)) + math.sqrt(MOBILE_HEIGHT_M))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


@dataclass
class Gap:
    start_km: float
    end_km: float

    @property
    def length_km(self) -> float:
        return self.end_km - self.start_km


@dataclass
class CoverageEstimate:
    total_km: float
    covered_km: float
    marginal_km: float
    uncovered_km: float
    gaps: list[Gap]  # Schatten-Lücken >= MIN_GAP_KM, längste zuerst
    terrain_used: bool
    samples: list[SamplePoint]
    reachable_ids: set[int]  # Geräte-IDs mit Sichtkontakt zu >=1 Streckenpunkt

    def pct(self, km: float) -> float:
        return 100.0 * km / self.total_km if self.total_km else 0.0

    @property
    def uncovered_pct(self) -> float:
        return self.pct(self.uncovered_km)


def estimate_coverage(points: list[Point], repeaters: list[Device],
                      terrain: TerrainModel | None = None) -> CoverageEstimate:
    cum = cumulative_km(points)
    total = cum[-1]

    # Strecke in ~SAMPLE_KM-Schritten abtasten (Polyline-Punkte sind dichter)
    samples: list[tuple[float, float, float]] = []
    next_km = 0.0
    for p, k in zip(points, cum):
        if k >= next_km:
            samples.append((k, p[0], p[1]))
            next_km = k + SAMPLE_KM

    lat_min, lon_min, lat_max, lon_max = bounding_box(points, BBOX_BUFFER_KM)
    reps: list[tuple[float, float, float, float, str, int]] = []
    for d in repeaters:
        if d.lat is None or d.lng is None:
            continue
        if not (lat_min <= d.lat <= lat_max and lon_min <= d.lng <= lon_max):
            continue
        agl = d.agl or DEFAULT_AGL_M
        reps.append((d.lat, d.lng, horizon_km(agl), agl, d.callsign, d.id))

    reachable_ids: set[int] = set()

    def classify(km: float, lat: float, lon: float) -> SamplePoint:
        candidates = sorted(
            ((dist, rl, rn, agl, cs, did)
             for rl, rn, radius, agl, cs, did in reps
             if (dist := _haversine_km(lat, lon, rl, rn)) <= radius),
            key=lambda c: c[0])
        los: list[str] = []
        marginal: list[str] = []
        # Alle Relais in Horizont-Reichweite prüfen — eine Kappung auf die
        # nächsten N führte zu Widersprüchen mit der Viewshed-Heatmap
        # (fernes Relais mit Sicht, nahe Relais alle verschattet)
        for dist, rl, rn, agl, cs, did in candidates:
            if terrain is None:
                los.append(cs)  # Horizontmodell: in Reichweite = versorgt
                reachable_ids.add(did)
                continue
            obstruction = terrain.obstruction_m(
                rl, rn, agl, lat, lon, MOBILE_HEIGHT_M, dist)
            if obstruction <= 0:
                los.append(cs)
                reachable_ids.add(did)
            elif obstruction <= MARGINAL_OBSTRUCTION_M:
                marginal.append(cs)
        status = LOS if los else (MARGINAL if marginal else SHADOW)
        return SamplePoint(km, status, tuple(los), tuple(marginal))

    sample_points = [classify(k, lat, lon) for k, lat, lon in samples]
    flags = [s.status for s in sample_points]

    covered = marginal = uncovered = 0.0
    gaps: list[Gap] = []
    gap_start: float | None = None
    for i, (k, _, _) in enumerate(samples):
        seg_end = samples[i + 1][0] if i + 1 < len(samples) else total
        seg_len = seg_end - k
        if flags[i] == LOS:
            covered += seg_len
        elif flags[i] == MARGINAL:
            marginal += seg_len
        else:
            uncovered += seg_len
        if flags[i] == SHADOW:
            if gap_start is None:
                gap_start = k
        elif gap_start is not None:
            gaps.append(Gap(gap_start, k))
            gap_start = None
    if gap_start is not None:
        gaps.append(Gap(gap_start, total))

    gaps = [g for g in gaps if g.length_km >= MIN_GAP_KM]
    gaps.sort(key=lambda g: -g.length_km)
    return CoverageEstimate(
        total_km=total, covered_km=covered, marginal_km=marginal,
        uncovered_km=uncovered, gaps=gaps, terrain_used=terrain is not None,
        samples=sample_points, reachable_ids=reachable_ids)
