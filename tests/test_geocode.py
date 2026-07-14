"""Tests freies Geocoding (Adressen/Orte) über Transitous — ohne Netz."""
import httpx
import pytest

from bmtools.road import RouteInputError
from bmtools.road.geocode import geocode_candidates


def _http(payload: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=payload)))


def test_kandidaten_mit_plz_ort_und_land():
    payload = [
        {"name": "Winkelhaider Straße 4a", "lat": 49.393, "lon": 11.261,
         "zip": "90537",
         "areas": [
             {"name": "Deutschland", "adminLevel": 2.0, "default": False},
             {"name": "Bayern", "adminLevel": 4.0, "default": False},
             {"name": "Mittelfranken", "adminLevel": 5.0, "default": False},
             {"name": "Feucht", "adminLevel": 8.0, "default": True},
         ]},
        {"name": "Colmantstraße", "lat": 50.73, "lon": 7.09, "areas": []},
    ]
    candidates = geocode_candidates("Winkelhaider Str. 4a",
                                    http=_http(payload))
    assert candidates[0].name == "Winkelhaider Straße 4a"
    assert candidates[0].region == "90537 Feucht, Bayern, Deutschland"
    assert candidates[1].region == ""


def test_region_ohne_default_und_plz_nimmt_feinste_area():
    payload = [{"name": "Colmantstraße 7", "lat": 50.425, "lon": 7.574,
                "areas": [{"name": "Deutschland", "adminLevel": 2.0},
                          {"name": "Bendorf", "adminLevel": 8.0}]}]
    candidates = geocode_candidates("Colmantstraße 7", http=_http(payload))
    assert candidates[0].region == "Bendorf, Deutschland"


def test_region_stadtstaat_ohne_dopplung():
    payload = [{"name": "Alexanderplatz", "lat": 52.52, "lon": 13.41,
                "areas": [{"name": "Deutschland", "adminLevel": 2.0},
                          {"name": "Berlin", "adminLevel": 4.0,
                           "default": True}]}]
    candidates = geocode_candidates("Alexanderplatz", http=_http(payload))
    assert candidates[0].region == "Berlin, Deutschland"


def test_labelgleiche_treffer_werden_zusammengefasst():
    hit = {"name": "Colmantstraße 7", "lat": 50.7337, "lon": 7.0891,
           "zip": "53115",
           "areas": [{"name": "Bonn", "adminLevel": 8.0, "default": True}]}
    payload = [hit, {**hit, "lat": 50.7338}]
    candidates = geocode_candidates("Colmantstr. 7", http=_http(payload))
    assert len(candidates) == 1


def test_nicht_gefunden_ist_nutzerfehler():
    with pytest.raises(RouteInputError, match="nicht gefunden"):
        geocode_candidates("xyzzy-gibts-nicht", http=_http([]))
