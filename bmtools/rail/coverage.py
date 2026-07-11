"""Grobe Abdeckungsschätzung entlang der Strecke.

Modell: Sichtlinien-Funkhorizont je Relais aus der Antennenhöhe
(d ≈ 4,12·(√h_Antenne + √h_Mobil) km), ohne Geländemodell. Das ist im
Flachland brauchbar und in Tälern/Mittelgebirgen optimistisch — der
ausgewiesene "ohne Abdeckung"-Anteil ist also eher eine Untergrenze.
Gerechnet wird gegen alle online gemeldeten Repeater der Umgebung,
nicht nur gegen die Treffer im Suchkorridor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from bmtools.bm_api.models import Device
from .corridor import bounding_box, cumulative_km, Point

MOBILE_HEIGHT_M = 2.0     # Handfunkgerät im Zug
DEFAULT_AGL_M = 15.0      # Annahme, wenn Antennenhöhe unbekannt
SAMPLE_KM = 0.5           # Abtastschritt entlang der Strecke
MIN_GAP_KM = 5.0          # kleinere Lücken werden nicht einzeln gelistet
BBOX_BUFFER_KM = 60.0     # Relais-Vorfilter um die Strecke


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
    uncovered_km: float
    gaps: list[Gap]  # nur Lücken >= MIN_GAP_KM, längste zuerst

    @property
    def uncovered_pct(self) -> float:
        return 100.0 * self.uncovered_km / self.total_km if self.total_km else 0.0


def estimate_coverage(points: list[Point], repeaters: list[Device]) -> CoverageEstimate:
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
    reps: list[tuple[float, float, float]] = []
    for d in repeaters:
        if d.lat is None or d.lng is None:
            continue
        if not (lat_min <= d.lat <= lat_max and lon_min <= d.lng <= lon_max):
            continue
        reps.append((d.lat, d.lng, horizon_km(d.agl or DEFAULT_AGL_M)))

    def covered(lat: float, lon: float) -> bool:
        return any(_haversine_km(lat, lon, rl, rn) <= rr for rl, rn, rr in reps)

    flags = [covered(lat, lon) for _, lat, lon in samples]

    uncovered = 0.0
    gaps: list[Gap] = []
    gap_start: float | None = None
    for i, (k, _, _) in enumerate(samples):
        seg_end = samples[i + 1][0] if i + 1 < len(samples) else total
        if not flags[i]:
            uncovered += seg_end - k
            if gap_start is None:
                gap_start = k
        elif gap_start is not None:
            gaps.append(Gap(gap_start, k))
            gap_start = None
    if gap_start is not None:
        gaps.append(Gap(gap_start, total))

    gaps = [g for g in gaps if g.length_km >= MIN_GAP_KM]
    gaps.sort(key=lambda g: -g.length_km)
    return CoverageEstimate(total_km=total, uncovered_km=uncovered, gaps=gaps)
