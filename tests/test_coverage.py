"""Tests Abdeckungsschätzung (Horizontmodell, ohne Gelände/Netz)."""
import math

import pytest

from bmtools.routelib.coverage import (
    LOS,
    MIN_GAP_KM,
    SHADOW,
    estimate_coverage,
    horizon_km,
)
from tests.conftest import make_device

LON_DEG_KM = 111.194 * math.cos(math.radians(50.0))  # ~71,5 km auf Breite 50


def _route(km: float, step_km: float = 0.5) -> list[tuple[float, float]]:
    """Ost-West-Strecke ab (50, 8) mit gegebener Länge."""
    n = int(km / step_km)
    return [(50.0, 8.0 + i * step_km / LON_DEG_KM) for i in range(n + 1)]


def test_horizont_formel():
    # 30 m Antenne + 2 m Mobilstation: 4,12*(sqrt(30)+sqrt(2)) = ~28,4 km
    assert horizon_km(30.0) == pytest.approx(28.4, abs=0.1)
    # Mindesthöhe 3 m verhindert Null-Horizont bei fehlender Angabe
    assert horizon_km(0.0) == horizon_km(3.0)


def test_relais_am_start_deckt_bis_zum_horizont():
    repeater = make_device(lat=50.0, lng=8.0, agl=30.0)  # Horizont ~28,4 km
    cov = estimate_coverage(_route(60.0), [repeater], terrain=None)

    assert not cov.terrain_used
    assert cov.total_km == pytest.approx(60.0, abs=0.6)
    assert cov.covered_km == pytest.approx(28.4, abs=1.0)
    assert cov.uncovered_km == pytest.approx(60.0 - 28.4, abs=1.0)
    assert cov.marginal_km == 0.0
    assert cov.reachable_ids == {repeater.id}
    assert cov.samples[0].status == LOS
    assert cov.samples[-1].status == SHADOW

    # Der unversorgte Rest ist eine einzige Lücke bis Streckenende
    assert len(cov.gaps) == 1
    assert cov.gaps[0].start_km == pytest.approx(28.4, abs=1.0)
    assert cov.gaps[0].end_km == pytest.approx(cov.total_km)
    assert cov.uncovered_pct == pytest.approx(100 * cov.uncovered_km / cov.total_km)


def test_kurze_luecken_werden_nicht_gelistet():
    # Zwei Relais mit kleiner Lücke dazwischen (< MIN_GAP_KM):
    # 15-m-Horizont ~21,8 km; Relais bei km 0 und km 47 auf 50 km Strecke
    r1 = make_device(id=262001, lat=50.0, lng=8.0, agl=15.0)
    r2 = make_device(id=262002, lat=50.0, lng=8.0 + 47.0 / LON_DEG_KM, agl=15.0)
    cov = estimate_coverage(_route(50.0), [r1, r2], terrain=None)

    mitte = [s for s in cov.samples if 22.5 < s.km < 24.5]
    assert all(s.status == SHADOW for s in mitte)  # Lücke existiert …
    assert all(g.length_km >= MIN_GAP_KM for g in cov.gaps)  # … wird aber
    assert cov.gaps == []                                    # nicht gelistet
    assert cov.reachable_ids == {262001, 262002}


def test_fortschritt_je_streckenpunkt():
    repeater = make_device(lat=50.0, lng=8.0, agl=30.0)
    meldungen: list[tuple[int, int]] = []
    estimate_coverage(_route(10.0), [repeater], terrain=None,
                      sample_progress=lambda f, g: meldungen.append((f, g)))
    gesamt = meldungen[0][1]
    assert gesamt > 0
    assert [f for f, _ in meldungen] == list(range(gesamt + 1))
    assert all(g == gesamt for _, g in meldungen)


def test_relais_ausserhalb_des_puffers_ignoriert():
    # >60 km neben der Strecke: fällt schon am Bounding-Box-Vorfilter
    weit_weg = make_device(lat=51.0, lng=8.0, agl=1000.0)
    cov = estimate_coverage(_route(10.0), [weit_weg], terrain=None)
    assert cov.reachable_ids == set()
    assert cov.covered_km == 0.0


def test_leere_strecke_ohne_division_durch_null():
    cov = estimate_coverage([(50.0, 8.0), (50.0, 8.0)], [], terrain=None)
    assert cov.total_km == 0.0
    assert cov.pct(0.0) == 0.0
