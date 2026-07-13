"""Tests Transitous-Anbindung (Antwort-Parsing, Filter) ohne Netz.

Die MOTIS-Antworten sind auf das Nötigste reduzierte Nachbauten der
echten /plan- und /geocode-Strukturen (Stand 2026-07).
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from bmtools.rail.bahn_link import BahnLinkError, fetch_verbindung
from bmtools.rail.route import NoItineraryError, PlanOptions, RoutePlanner
from bmtools.routelib.model import Station, decode_polyline

FRM = Station("Lindau-Insel", 47.544343, 9.680465)
TO = Station("Augsburg Hbf", 48.365444, 10.885568)


def _encode(points: list[tuple[float, float]], precision: int = 7) -> str:
    """Google-Encoded-Polyline (Gegenstück zu decode_polyline)."""
    factor = 10 ** precision
    out: list[str] = []
    prev = (0, 0)
    for lat, lon in points:
        cur = (round(lat * factor), round(lon * factor))
        for delta in (cur[0] - prev[0], cur[1] - prev[1]):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev = cur
    return "".join(out)


def test_polyline_roundtrip():
    pts = [(47.544343, 9.680465), (48.365444, 10.885568), (48.0, -1.5)]
    assert decode_polyline(_encode(pts)) == pts
    grob = decode_polyline(_encode(pts, 5), 5)
    for (lat, lon), (elat, elon) in zip(grob, pts, strict=True):
        assert lat == pytest.approx(elat, abs=1e-5)
        assert lon == pytest.approx(elon, abs=1e-5)


def _leg(mode: str = "RAIL", name: str = "RE7 (3285)",
         start: str = "2026-08-17T04:57:00Z") -> dict[str, Any]:
    return {
        "mode": mode, "startTime": start, "routeShortName": name,
        "from": {"name": FRM.name}, "to": {"name": TO.name},
        "legGeometry": {
            "points": _encode([(FRM.lat, FRM.lon), (TO.lat, TO.lon)]),
            "precision": 7},
    }


def _plan_response() -> dict[str, Any]:
    walk = {"mode": "WALK", "startTime": "2026-08-17T04:54:00Z",
            "legGeometry": {"points": "", "precision": 7}}
    direkt = {"startTime": "2026-08-17T04:54:00Z",
              "endTime": "2026-08-17T07:15:00Z",
              "transfers": 0, "legs": [walk, _leg()]}
    umsteiger = {"startTime": "2026-08-17T05:07:00Z",
                 "endTime": "2026-08-17T07:00:00Z", "transfers": 1,
                 "legs": [_leg(name="RB93", start="2026-08-17T05:07:00Z"),
                          _leg(name="RE96", start="2026-08-17T06:00:00Z")]}
    return {"itineraries": [direkt, umsteiger]}


def _planner(payload: object, status: int = 200) -> RoutePlanner:
    def handler(request: httpx.Request) -> httpx.Response:
        handler.last_request = request  # type: ignore[attr-defined]
        return httpx.Response(status, json=payload)

    planner = RoutePlanner()
    planner._http = httpx.Client(transport=httpx.MockTransport(handler))
    planner._handler = handler  # type: ignore[attr-defined]
    return planner


def test_segment_options_parst_motis_antwort():
    planner = _planner(_plan_response())
    options = planner.segment_options(FRM, TO, PlanOptions())

    assert len(options) == 2
    direkt = options[0]
    assert direkt.transfers == 0
    assert direkt.trains == ["RE7 (3285)"]         # WALK-Leg übersprungen
    assert direkt.dep is not None
    assert f"{direkt.dep:%H:%M}" == "06:57"        # UTC -> Lokalzeit (CEST)
    assert direkt.start < direkt.dep               # start inkl. Fußweg
    assert direkt.points[0] == pytest.approx((FRM.lat, FRM.lon))
    assert "Lindau-Insel -> Augsburg Hbf" in direkt.labels[0]


def test_direktfilter_filtert_clientseitig_und_erklaert_leermenge():
    planner = _planner(_plan_response())
    options = planner.segment_options(FRM, TO, PlanOptions(direct_only=True))
    assert [o.transfers for o in options] == [0]

    nur_umsteiger = {"itineraries": _plan_response()["itineraries"][1:]}
    planner = _planner(nur_umsteiger)
    with pytest.raises(NoItineraryError, match="Direktfilters verworfen"):
        planner.segment_options(FRM, TO, PlanOptions(direct_only=True))


def test_geocode_liefert_kandidaten_mit_region():
    planner = _planner([{"name": "Koblenz Hbf", "lat": 50.35, "lon": 7.59,
                         "areas": [{"name": "Deutschland"},
                                   {"name": "Rheinland-Pfalz"}]}])
    [station] = planner.geocode_candidates("Koblenz", limit=1)
    assert station.name == "Koblenz Hbf"
    assert station.region == "Deutschland, Rheinland-Pfalz"

    with pytest.raises(NoItineraryError, match="nicht gefunden"):
        _planner([]).geocode_candidates("Nirgendwo")


RECON = (
    "¶HKI¶T$A=1@O=Lindau-Insel@X=9680465@Y=47544343@L=8000230@a=128@"
    "$A=1@O=Augsburg Hbf@X=10885568@Y=48365444@L=8000013@a=128@"
    "$202608170657$202608170915$             3285$$1$$$$$$¶KC¶#VE#2#"
)


def test_fetch_verbindung_ohne_netz():
    payload = {"startOrt": "Lindau-Insel", "zielOrt": "Augsburg Hbf",
               "hinfahrtDatum": "2026-08-17T06:57:00+02:00",
               "hinfahrtRecon": RECON}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/d406032b-b663-4266-952d-f8e117dd3e41")
        return httpx.Response(200, json=payload)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    v = fetch_verbindung("d406032b-b663-4266-952d-f8e117dd3e41", http=http)
    assert v.start_ort == "Lindau-Insel"
    assert len(v.legs) == 1 and v.legs[0].train == "3285"


def test_fetch_verbindung_abgelaufen():
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500, json={})))
    with pytest.raises(BahnLinkError, match="abgelaufen"):
        fetch_verbindung("00000000-0000-0000-0000-000000000000", http=http)


def test_fetch_verbindung_json_kaputt_wird_gemeldet():
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"startOrt": "X"})))
    with pytest.raises(BahnLinkError, match="hinfahrtRecon"):
        fetch_verbindung("00000000-0000-0000-0000-000000000000", http=http)
