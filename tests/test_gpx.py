"""Tests GPX-Import (Track- und Routen-Punkte, Fehlerfälle)."""
import pytest

from bmtools.road import RouteInputError
from bmtools.road.gpx import read_gpx

GPX_TRACK = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="komoot" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>Von Kühnhofen nach Feucht-Moosbach</name></metadata>
  <trk><name>Von Kühnhofen nach Feucht-Moosbach</name><trkseg>
    <trkpt lat="49.522862" lon="11.425087"><ele>354.3</ele></trkpt>
    <trkpt lat="49.522900" lon="11.425200"><ele>354.0</ele></trkpt>
    <trkpt lat="49.523100" lon="11.425500"><ele>353.8</ele></trkpt>
  </trkseg></trk>
</gpx>"""

GPX_ROUTE_ONLY = """<?xml version="1.0"?>
<gpx version="1.0" xmlns="http://www.topografix.com/GPX/1/0">
  <rte><rtept lat="50.1" lon="7.2"/><rtept lat="50.2" lon="7.3"/></rte>
</gpx>"""


def test_track(tmp_path):
    p = tmp_path / "tour.gpx"
    p.write_text(GPX_TRACK, encoding="utf-8")
    track = read_gpx(p)
    assert track.name == "Von Kühnhofen nach Feucht-Moosbach"
    assert len(track.points) == 3
    assert track.points[0] == (49.522862, 11.425087)


def test_route_fallback(tmp_path):
    p = tmp_path / "route.gpx"
    p.write_text(GPX_ROUTE_ONLY, encoding="utf-8")
    track = read_gpx(p)
    assert track.points == [(50.1, 7.2), (50.2, 7.3)]
    assert track.name == "route"  # kein <name> -> Dateiname


def test_leere_datei(tmp_path):
    p = tmp_path / "leer.gpx"
    p.write_text("<gpx xmlns='http://www.topografix.com/GPX/1/1'/>")
    with pytest.raises(RouteInputError, match="keine Track- oder Routenpunkte"):
        read_gpx(p)


def test_kaputtes_xml(tmp_path):
    p = tmp_path / "kaputt.gpx"
    p.write_text("<gpx><trk>")
    with pytest.raises(RouteInputError, match="nicht lesbar"):
        read_gpx(p)
