"""Tests Straßen-Routing: OSRM-Primärweg und Fallback-Kette."""
import httpx
import pytest

from bmtools.road.routing import route_from_track, route_waypoints
from bmtools.routelib.model import Waypoint


def encode_polyline(points, precision=5):
    """Gegenstück zu decode_polyline — nur für Test-Fixtures."""
    factor = 10 ** precision
    out = []
    prev_lat = prev_lon = 0
    for lat, lon in points:
        for value, prev in ((round(lat * factor), prev_lat),
                            (round(lon * factor), prev_lon)):
            delta = value - prev
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lon = round(lat * factor), round(lon * factor)
    return "".join(out)


WAYPOINTS = [Waypoint("Feucht", 49.3933308, 11.2614733),
             Waypoint("Bendorf", 50.4253325, 7.5743396)]
GEOMETRY = [(49.3933, 11.2615), (49.9, 9.5), (50.4253, 7.5743)]


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_osrm_route():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "routing.openstreetmap.de"
        assert "/routed-car/" in request.url.path
        # beide Wegpunkte als lon,lat im Pfad
        assert "11.261473,49.393331;7.574340,50.425333" in request.url.path
        return httpx.Response(200, json={
            "code": "Ok",
            "routes": [{"geometry": encode_polyline(GEOMETRY),
                        "distance": 363000.0, "duration": 13200.0}],
        })

    route = route_waypoints(WAYPOINTS, "car", _client(handler))
    assert route.points == pytest.approx(GEOMETRY)
    assert route.stations == WAYPOINTS
    assert not route.is_interpolated
    assert route.legs == ["Auto-Route (OSRM/OpenStreetMap): 363 km, 3:40 h"]


def test_osrm_bike_profil():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/routed-bike/" in request.url.path
        return httpx.Response(200, json={
            "code": "Ok",
            "routes": [{"geometry": encode_polyline(GEOMETRY),
                        "distance": 448000.0, "duration": 59000.0}],
        })

    route = route_waypoints(WAYPOINTS, "bike", _client(handler))
    assert "Rad-Route" in route.legs[0]


def test_fallback_transitous():
    warnings: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "routing.openstreetmap.de":
            return httpx.Response(500)
        assert request.url.host == "api.transitous.org"
        assert request.url.params["directModes"] == "CAR"
        assert request.url.params["maxDirectTime"] == "86400"
        return httpx.Response(200, json={"direct": [{
            "duration": 13200,
            "legs": [{"mode": "CAR", "distance": 363000.0,
                      "legGeometry": {
                          "points": encode_polyline(GEOMETRY, 7),
                          "precision": 7}}],
        }]})

    route = route_waypoints(WAYPOINTS, "car", _client(handler),
                            warn=warnings.append)
    assert route.points == pytest.approx(GEOMETRY)
    assert "Transitous" in route.legs[0]
    assert len(warnings) == 1 and "OSRM" in warnings[0]


def test_fallback_luftlinie():
    warnings: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    route = route_waypoints(WAYPOINTS, "car", _client(handler),
                            warn=warnings.append)
    assert route.is_interpolated
    assert route.points == [(w.lat, w.lon) for w in WAYPOINTS]
    assert len(warnings) == 2 and "Luftlinie" in warnings[1]


def test_wegpunkt_ohne_koordinaten():
    with pytest.raises(ValueError, match="ohne Koordinaten"):
        route_waypoints([Waypoint("Feucht", 49.39, 11.26),
                         Waypoint("Bendorf", None, None)],  # type: ignore[arg-type]
                        "car")


def test_route_from_track():
    route = route_from_track(GEOMETRY, "Komoot-Tour „Test“: 12,3 km",
                             start_name="Kühnhofen", end_name="Moosbach")
    assert route.points == GEOMETRY
    assert [s.name for s in route.stations] == ["Kühnhofen", "Moosbach"]
    assert (route.stations[0].lat, route.stations[0].lon) == GEOMETRY[0]
    assert not route.is_interpolated
