"""Tests Komoot-Link-Parser und Tour-Abruf.

URL-Fixtures sind echte Nutzer-Links (2026-07-12/13): eine öffentliche
Smarttour (e-Präfix-ID) und eine private Tour mit share_token.
"""
import httpx
import pytest

from bmtools.road import RouteInputError
from bmtools.road.komoot import KomootRef, fetch_tour, is_komoot_url, parse_komoot_url

SMARTTOUR_URL = ("https://www.komoot.com/de-de/smarttour/e1868296068/"
                 "traumpfad-hoehlen-und-schluchtensteig?ref=wdd&t_s=referral")
PRIVATE_URL = ("https://www.komoot.com/de-de/tour/3051244254"
               "?share_token=aL1X1vcGvYbnkMGIijaGX9MsDxIDVy5rYpb2icwSyCq2am0OpL"
               "&ref=wtd")

META = {"id": 1868296068, "name": "Testtour", "sport": "touringbicycle",
        "distance": 27600.0, "status": "public"}
ITEMS = {"items": [{"lat": 49.52, "lng": 11.42, "alt": 354.3, "t": 0},
                   {"lat": 49.53, "lng": 11.40, "alt": 350.0, "t": 60}]}


def test_parse_smarttour_mit_e_praefix():
    ref = parse_komoot_url(SMARTTOUR_URL)
    assert ref.tour_id == 1868296068
    assert ref.share_token is None


def test_parse_private_tour_mit_share_token():
    ref = parse_komoot_url(PRIVATE_URL)
    assert ref.tour_id == 3051244254
    assert ref.share_token == \
        "aL1X1vcGvYbnkMGIijaGX9MsDxIDVy5rYpb2icwSyCq2am0OpL"


def test_kein_tour_link():
    with pytest.raises(RouteInputError, match="kein Komoot-Tour-Link"):
        parse_komoot_url("https://www.komoot.com/de-de/collection/12345")


def test_is_komoot_url():
    assert is_komoot_url(SMARTTOUR_URL)
    assert not is_komoot_url("https://maps.app.goo.gl/x")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_tour_mit_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["share_token"] == "tok"  # an beiden Calls
        if request.url.path.endswith("/coordinates"):
            return httpx.Response(200, json=ITEMS)
        return httpx.Response(200, json=META)

    tour = fetch_tour(KomootRef(3051244254, "tok"), _client(handler))
    assert tour.name == "Testtour"
    assert tour.sport == "touringbicycle"
    assert tour.distance_km == pytest.approx(27.6)
    assert tour.points == [(49.52, 11.42), (49.53, 11.40)]


def test_fetch_tour_privat_ohne_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "AccessDenied"})

    with pytest.raises(RouteInputError, match="Mit Link teilen"):
        fetch_tour(KomootRef(3051244254), _client(handler))


def test_fetch_tour_unbekannte_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "NotFound"})

    with pytest.raises(RouteInputError, match="3051244254"):
        fetch_tour(KomootRef(3051244254), _client(handler))


def test_fetch_tour_html_fallback():
    # /coordinates schlägt fehl -> Koordinaten aus dem escapten JSON
    # der Tour-Seite (so liegt es dort eingebettet, verifiziert 2026-07-12)
    page = ('<script>x = "{\\"coordinates\\":{\\"items\\":'
            '[{\\"lat\\":50.1,\\"lng\\":7.2,\\"alt\\":100},'
            '{\\"lat\\":50.2,\\"lng\\":7.3,\\"alt\\":110}]}}"</script>')

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/coordinates"):
            return httpx.Response(500)
        if request.url.host == "www.komoot.com":
            return httpx.Response(200, text=page)
        return httpx.Response(200, json=META)

    tour = fetch_tour(KomootRef(1868296068), _client(handler),
                      page_url="https://www.komoot.com/de-de/smarttour/e1868296068/x")
    assert tour.points == [(50.1, 7.2), (50.2, 7.3)]


def test_fetch_tour_ohne_geometrie_verweist_auf_gpx():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/coordinates"):
            return httpx.Response(500)
        return httpx.Response(200, json=META)

    with pytest.raises(RouteInputError, match="--gpx"):
        fetch_tour(KomootRef(1868296068), _client(handler))
