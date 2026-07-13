"""Tests freies Geocoding (Adressen/Orte) über Transitous — ohne Netz."""
import httpx
import pytest

from bmtools.road import RouteInputError
from bmtools.road.geocode import geocode_candidates


def _http(payload: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=payload)))


def test_kandidaten_mit_region():
    payload = [
        {"name": "Colmantstraße 7", "lat": 50.425, "lon": 7.574,
         "areas": [{"name": "Bendorf"}, {"name": "Deutschland"}]},
        {"name": "Colmantstraße", "lat": 50.73, "lon": 7.09, "areas": []},
    ]
    candidates = geocode_candidates("Colmantstraße 7", http=_http(payload))
    assert candidates[0].name == "Colmantstraße 7"
    assert candidates[0].region == "Bendorf, Deutschland"
    assert candidates[1].region == ""


def test_nicht_gefunden_ist_nutzerfehler():
    with pytest.raises(RouteInputError, match="nicht gefunden"):
        geocode_candidates("xyzzy-gibts-nicht", http=_http([]))
