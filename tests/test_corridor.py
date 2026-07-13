"""Tests Korridor-Geometrie (Distanz Punkt->Strecke, Streckenkilometer).

Referenzwerte: 1 Breitengrad = ~111,2 km (Erdradius 6371 km), Längengrade
mit cos(Breite) skaliert — auf Breite 50° also ~71,5 km je Grad.
"""
import math

import pytest

from bmtools.routelib.corridor import (
    bounding_box,
    cumulative_km,
    find_in_corridor,
    point_to_segment_km,
)
from tests.conftest import make_device

# Ost-West-Segment auf Breite 50: (lat, lon)
A, B = (50.0, 8.0), (50.0, 9.0)
LON_DEG_KM = 111.194 * math.cos(math.radians(50.0))  # ~71,5 km


def test_punkt_neben_segmentmitte():
    # 0,09° nördlich der Mitte = ~10 km Abstand, t = 0,5
    dist, t = point_to_segment_km((50.09, 8.5), A, B)
    assert dist == pytest.approx(10.0, abs=0.1)
    assert t == pytest.approx(0.5, abs=0.01)


def test_punkt_hinter_segmentende_klemmt_auf_t1():
    dist, t = point_to_segment_km((50.0, 9.5), A, B)
    assert t == 1.0
    assert dist == pytest.approx(0.5 * LON_DEG_KM, rel=0.01)


def test_nullsegment_faellt_nicht_um():
    dist, t = point_to_segment_km((50.1, 8.0), A, A)
    assert t == 0.0
    assert dist == pytest.approx(0.1 * 111.194, rel=0.01)


def test_streckenkilometer():
    cum = cumulative_km([A, (50.0, 8.5), B])
    assert cum[0] == 0.0
    assert cum[1] == pytest.approx(LON_DEG_KM / 2, rel=0.01)
    assert cum[2] == pytest.approx(LON_DEG_KM, rel=0.01)


def test_bounding_box_puffer():
    lat_min, lon_min, lat_max, _lon_max = bounding_box([A, B], 111.0)
    assert lat_min == pytest.approx(49.0, abs=0.01)
    assert lat_max == pytest.approx(51.0, abs=0.01)
    assert lon_min < 8.0 - 1.0  # Längenpuffer > 1° (cos-Skalierung)


def test_korridor_filtert_und_sortiert_nach_streckenkilometer():
    nah_hinten = make_device(id=262002, lat=50.05, lng=8.9)   # ~5,6 km, km ~64
    nah_vorne = make_device(id=262001, lat=50.09, lng=8.2)    # ~10 km, km ~14
    fern = make_device(id=262003, lat=51.0, lng=8.5)          # ~111 km
    ohne_position = make_device(id=262004, lat=None, lng=None)

    hits = find_in_corridor(
        [nah_hinten, nah_vorne, fern, ohne_position], [A, B], corridor_km=20.0)
    assert [h.device.id for h in hits] == [262001, 262002]
    assert hits[0].chainage_km < hits[1].chainage_km
    assert hits[0].distance_km == pytest.approx(10.0, abs=0.2)


def test_korridor_ohne_limit_nimmt_alle_mit_position():
    fern = make_device(id=262003, lat=51.0, lng=8.5)
    hits = find_in_corridor([fern], [A, B], corridor_km=None)
    assert len(hits) == 1
    assert hits[0].distance_km == pytest.approx(111.2, rel=0.01)
