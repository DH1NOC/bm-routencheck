"""GPX-Import — der garantierte Weg für Komoot & Co.

Bewusst nur Standardbibliothek (xml.etree), namespace-tolerant:
GPX 1.0/1.1 nutzen unterschiedliche Namespaces, Portale ergänzen
eigene. Gelesen werden Track-Punkte (trkpt), ersatzweise
Routen-Punkte (rtept).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from . import RouteInputError
from bmtools.routelib.model import Point


@dataclass
class GpxTrack:
    name: str
    points: list[Point]  # (lat, lon)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_gpx(path: Path) -> GpxTrack:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        raise RouteInputError(f"GPX-Datei nicht lesbar ({path}): {e}")

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
            name = el.text.strip()

    points = points or route_points
    if len(points) < 2:
        raise RouteInputError(
            f"GPX-Datei enthält keine Track- oder Routenpunkte: {path}")
    return GpxTrack(name=name or path.stem, points=points)
