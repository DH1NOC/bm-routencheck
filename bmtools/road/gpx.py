"""GPX-Import — der garantierte Weg für Komoot & Co.

Geparst wird über defusedxml statt xml.etree direkt: GPX-Dateien
kommen nicht nur vom Nutzer selbst (Komoot-Export, von anderen
geteilte Tracks), und xml.etree ist laut eigener Doku nicht gegen
bösartiges XML gehärtet (Entity-Aufblasen → Speicher-DoS). Ansonsten
namespace-tolerant: GPX 1.0/1.1 nutzen unterschiedliche Namespaces,
Portale ergänzen eigene. Gelesen werden Track-Punkte (trkpt),
ersatzweise Routen-Punkte (rtept).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import parse as _xml_parse

from bmtools.routelib.model import Point

from . import RouteInputError


@dataclass
class GpxTrack:
    name: str
    points: list[Point]  # (lat, lon)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_gpx(path: Path) -> GpxTrack:
    try:
        root = _xml_parse(path).getroot()
    except (ParseError, DefusedXmlException, OSError) as e:
        raise RouteInputError(f"GPX-Datei nicht lesbar ({path}): {e}") from e
    if root is None:
        raise RouteInputError(f"GPX-Datei nicht lesbar ({path}): leer")

    points: list[Point] = []
    route_points: list[Point] = []
    name = ""
    for el in root.iter():
        tag = _local(el.tag)
        if tag in ("trkpt", "rtept"):
            try:
                p = (float(el.attrib["lat"]), float(el.attrib["lon"]))
            except (KeyError, ValueError):
                continue
            (points if tag == "trkpt" else route_points).append(p)
        elif tag == "name" and not name and (el.text or "").strip():
            name = (el.text or "").strip()

    points = points or route_points
    if len(points) < 2:
        raise RouteInputError(
            f"GPX-Datei enthält keine Track- oder Routenpunkte: {path}")
    return GpxTrack(name=name or path.stem, points=points)
