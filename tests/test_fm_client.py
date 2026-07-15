"""Tests DL3EL-Client: Stützpunkt-Raster, Abfrageparameter, Cache, Dedupe."""
from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from bmtools.fm_api import client as fm_client
from bmtools.fm_api.client import DL3ELClient, query_points

FIXTURES = Path(__file__).parent / "fixtures"

KM_DEG = 1 / 111.195  # 1 km in Breitengrad


def line_route(length_km: float, lat0: float = 49.0, lon0: float = 11.0):
    """Gerade Nord-Süd-Teststrecke mit Punkt je Kilometer."""
    return [(lat0 + k * KM_DEG, lon0) for k in range(int(length_km) + 1)]


def _client(handler, tmp_path, monkeypatch, refresh: bool = False) -> DL3ELClient:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = DL3ELClient(refresh=refresh)
    c._http = httpx.Client(transport=httpx.MockTransport(handler))
    c._cache.dir = tmp_path
    return c


def _fixture_handler(calls: list[httpx.URL]):
    csv = (FIXTURES / "dl3el_nuernberg.csv").read_bytes()
    gpx = (FIXTURES / "dl3el_nuernberg.gpx").read_bytes()
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        body = csv if request.url.params["printas"] == "csv" else gpx
        return httpx.Response(200, content=body)
    return handler


def test_query_points_raster_und_ziel():
    pts = query_points(line_route(120))
    # km 0, 50, 100 plus Ziel bei km 120
    assert len(pts) == 4
    assert pts[0] == (49.0, 11.0)
    assert pts[-1][0] == pytest.approx(round((49.0 + 120 * KM_DEG) * 10) / 10)


def test_query_points_kurze_route_ohne_doppelte_zellen():
    # 3 km: Start und Ziel fallen in dieselbe 0,1°-Zelle → ein Stützpunkt
    assert query_points(line_route(3)) == [(49.0, 11.0)]


def test_repeaters_near_parst_und_merged(tmp_path, monkeypatch):
    calls: list[httpx.URL] = []
    c = _client(_fixture_handler(calls), tmp_path, monkeypatch)
    reps = c.repeaters_near(49.5, 11.0)
    assert len(reps) == 100
    fue = next(r for r in reps if r.callsign == "DB0FUE" and r.tx_mhz == 145.6375)
    assert (fue.lat, fue.lng) == (49.4809, 10.957)  # GPX-Koordinaten gemergt
    # Formularfelder: 49,5° → 49°30' Nord, beide type-Werte
    params = calls[0].params
    assert (params["lat_deg"], params["lat_min"]) == ("49", "30")
    assert (params["lat_NS"], params["lon_EW"]) == ("Nord", "Ost")
    assert params.get_list("type") == ["DL3EL", "fr"]
    assert params["maxgateways"] == "200"
    assert params["dxcc"] == "all"


def test_cache_vermeidet_zweiten_abruf(tmp_path, monkeypatch):
    calls: list[httpx.URL] = []
    c = _client(_fixture_handler(calls), tmp_path, monkeypatch)
    c.repeaters_near(49.5, 11.0)
    assert len(calls) == 2  # CSV + GPX
    # zweiter Aufruf im selben 0,1°-Raster: kein weiterer HTTP-Abruf
    c.repeaters_near(49.52, 11.04)
    assert len(calls) == 2


def test_refresh_ignoriert_cache_und_schreibt_neu(tmp_path, monkeypatch):
    calls: list[httpx.URL] = []
    c = _client(_fixture_handler(calls), tmp_path, monkeypatch)
    c.repeaters_near(49.5, 11.0)
    r = _client(_fixture_handler(calls), tmp_path, monkeypatch, refresh=True)
    r.repeaters_near(49.5, 11.0)
    assert len(calls) == 4  # Cache ignoriert …
    c2 = _client(_fixture_handler(calls), tmp_path, monkeypatch)
    c2.repeaters_near(49.5, 11.0)
    assert len(calls) == 4  # … aber neu geschrieben


def test_repeaters_along_dedupliziert_ueber_stuetzpunkte(tmp_path, monkeypatch):
    calls: list[httpx.URL] = []
    c = _client(_fixture_handler(calls), tmp_path, monkeypatch)
    reps = c.repeaters_along(line_route(60))
    # 2 Stützpunkte × dieselbe Antwort (95 eindeutige) → einmal je Relais
    assert len(calls) == 4
    assert len(reps) == 95
    assert len({(r.callsign, r.tx_mhz) for r in reps}) == 95


def test_fehler_nach_retries(tmp_path, monkeypatch):
    c = _client(lambda r: httpx.Response(500), tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="relaislisten.darc.de"):
        c.repeaters_near(49.5, 11.0)
