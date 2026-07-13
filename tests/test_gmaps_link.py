"""Tests Google-Maps-Link-Parser.

Die Lang-URLs sind echte, am 2026-07-12 aus Nutzer-Kurzlinks
expandierte Fixtures (Auto- und Rad-Route Feucht-Moosbach -> Bendorf).
"""
import httpx
import pytest

from bmtools.road import RouteInputError
from bmtools.road.gmaps_link import (
    expand_short_link,
    is_gmaps_url,
    parse_gmaps_url,
)

CAR_URL = (
    "https://www.google.com/maps/dir/Winkelhaider+Str.+4A,+90537+Feucht-Moosbach/"
    "Colmantstra%C3%9Fe+7,+56170+Bendorf/@49.8587679,8.0542712,8z/"
    "data=!4m14!4m13!1m5!1m1!1s0x479f5e7c38f94c3d:0xfc36f8b9175358e1"
    "!2m2!1d11.2614733!2d49.3933308!1m5!1m1!1s0x47be62a26073dca7:0x3503efbdeb037fd1"
    "!2m2!1d7.5743396!2d50.4253325!3e0?entry=tts"
)
BIKE_URL = CAR_URL.replace("!3e0", "!3e1")


def test_parse_car_link():
    route = parse_gmaps_url(CAR_URL)
    assert route.mode == "car"
    assert len(route.waypoints) == 2
    start, ziel = route.waypoints
    assert start.name == "Winkelhaider Str. 4A, 90537 Feucht-Moosbach"
    assert ziel.name == "Colmantstraße 7, 56170 Bendorf"
    assert (start.lat, start.lon) == (49.3933308, 11.2614733)
    assert (ziel.lat, ziel.lon) == (50.4253325, 7.5743396)
    assert all(w.resolved for w in route.waypoints)


def test_parse_bike_link():
    assert parse_gmaps_url(BIKE_URL).mode == "bike"


def test_transit_link_verweist_auf_bm_rail():
    with pytest.raises(RouteInputError, match="bm-rail"):
        parse_gmaps_url(CAR_URL.replace("!3e0", "!3e3"))


def test_koordinaten_pfadsegmente_ohne_blob():
    url = "https://www.google.com/maps/dir/49.39,11.26/50.42,7.57/@50,9,8z"
    route = parse_gmaps_url(url)
    assert [(w.lat, w.lon) for w in route.waypoints] == \
        [(49.39, 11.26), (50.42, 7.57)]
    assert route.mode is None


def test_drag_via_mehr_paare_als_namen():
    # Drei !1d/!2d-Paare, zwei benannte Enden -> unbenannter Zwischenpunkt
    url = (
        "https://www.google.com/maps/dir/Start/Ziel/@50,9,8z/"
        "data=!1m5!2m2!1d11.0!2d49.0!1m3!2m2!1d10.0!2d49.5"
        "!1m5!2m2!1d7.5!2d50.4!3e0"
    )
    route = parse_gmaps_url(url)
    assert [w.name for w in route.waypoints] == ["Start", "Via 1", "Ziel"]
    assert [(w.lat, w.lon) for w in route.waypoints] == \
        [(49.0, 11.0), (49.5, 10.0), (50.4, 7.5)]


def test_api1_form():
    url = ("https://www.google.com/maps/dir/?api=1&origin=Koblenz"
           "&destination=N%C3%BCrnberg&waypoints=W%C3%BCrzburg%7CFürth"
           "&travelmode=bicycling")
    route = parse_gmaps_url(url)
    assert route.mode == "bike"
    assert [w.name for w in route.waypoints] == \
        ["Koblenz", "Würzburg", "Fürth", "Nürnberg"]
    assert not any(w.resolved for w in route.waypoints)  # geocoden nötig


def test_kein_routenlink():
    with pytest.raises(RouteInputError, match="kein Google-Maps-Routenlink"):
        parse_gmaps_url("https://www.google.com/maps/place/Koblenz")


def test_is_gmaps_url():
    assert is_gmaps_url(CAR_URL)
    assert is_gmaps_url("https://maps.app.goo.gl/xaSZdtWAmRcPMDuYA")
    assert not is_gmaps_url("https://www.komoot.com/tour/3051244254")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_expand_short_link():
    # Verifiziertes Verhalten 2026-07-12: ein einziger 302 zur Lang-URL
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "maps.app.goo.gl"
        return httpx.Response(302, headers={"location": CAR_URL})

    assert expand_short_link(
        "https://maps.app.goo.gl/xaSZdtWAmRcPMDuYA", _client(handler)) == CAR_URL


def test_expand_short_link_consent_wall():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={
            "location": "https://consent.google.com/m?continue=..."})

    with pytest.raises(RouteInputError, match="Adresszeile"):
        expand_short_link("https://maps.app.goo.gl/x", _client(handler))


def test_expand_short_link_ohne_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="kein Redirect")

    with pytest.raises(RouteInputError, match="nicht aufgelöst"):
        expand_short_link("https://maps.app.goo.gl/x", _client(handler))
