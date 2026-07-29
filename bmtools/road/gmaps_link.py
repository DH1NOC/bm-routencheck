"""Google-Maps-Routenlink -> Wegpunkte + Verkehrsmittel.

Der Link enthält KEINE Routen-Geometrie, nur Wegpunkte (verifiziert
2026-07-12): Namen als Pfadsegmente zwischen /dir/ und /@, präzise
Koordinaten im undokumentierten data=-Blob als !1d<lon>!2d<lat>-Paare,
Verkehrsmittel als !3e0..3. Geroutet wird danach selbst (OSRM).

Unterstützte Formen:
- https://www.google.com/maps/dir/<wp1>/<wp2>/.../@.../data=!...
  (auch mit eingeschobenen Parameter-Segmenten wie /am=t/)
- https://www.google.com/maps/dir/?api=1&origin=...&destination=...
  (dokumentierte Maps-URLs-API)
- Kurzlinks https://maps.app.goo.gl/... (ein 302 auf die Lang-URL,
  verifiziert 2026-07-12; Auflösung via expand_short_link)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote_plus, urlsplit

import httpx

from . import RouteInputError

USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

SHORTLINK_HOSTS = {"maps.app.goo.gl", "goo.gl", "g.co"}

# !3e-Werte des data=-Blobs bzw. travelmode= der api=1-Form
_MODE_BY_3E = {"0": "car", "1": "bike", "2": "foot", "3": "transit"}
_MODE_BY_TRAVELMODE = {"driving": "car", "bicycling": "bike",
                       "walking": "foot", "transit": "transit"}

# Parameter-Pfadsegmente wie am=t, die Google seit ~2026-07 zwischen
# @-Viewport und data=-Blob einschiebt (verifiziert 2026-07-29, Issue #1)
_PARAM_SEGMENT = re.compile(r"^[a-z][a-z0-9_]{0,11}=")
_COORD_SEGMENT = re.compile(r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")
_BLOB_PAIR = re.compile(r"!1d(-?\d+(?:\.\d+)?)!2d(-?\d+(?:\.\d+)?)")
_BLOB_MODE = re.compile(r"!3e(\d)")


@dataclass
class LinkWaypoint:
    """Wegpunkt aus dem Link; Koordinaten fehlen, wenn der data=-Blob
    sie nicht hergibt — dann muss der Name geocodiert werden."""
    name: str
    lat: float | None = None
    lon: float | None = None

    @property
    def resolved(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass
class GmapsRoute:
    waypoints: list[LinkWaypoint]
    mode: str | None  # "car" | "bike" | "foot" | None (Link ohne Angabe)


def is_gmaps_url(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return ("google." in host and "/maps" in urlsplit(url).path) \
        or host in SHORTLINK_HOSTS


def expand_short_link(url: str, http: httpx.Client | None = None) -> str:
    """Kurzlink (maps.app.goo.gl u. ä.) zur Lang-URL auflösen."""
    own_client = http is None
    http = http or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})
    try:
        current = url
        for _ in range(5):
            r = http.get(current, follow_redirects=False)
            target = r.headers.get("location")
            if r.status_code in (301, 302, 303, 307, 308) and target:
                if "consent.google" in urlsplit(target).netloc:
                    raise RouteInputError(
                        "Google verlangt eine Cookie-Zustimmung, der Kurzlink "
                        "lässt sich so nicht auflösen. Bitte die Route im "
                        "Browser öffnen und die vollständige URL aus der "
                        "Adresszeile kopieren.")
                current = target
                if "/maps" in urlsplit(target).path:
                    return target
                continue
            break
        raise RouteInputError(
            f"Kurzlink konnte nicht aufgelöst werden: {url} — bitte die "
            f"vollständige URL aus der Browser-Adresszeile verwenden.")
    finally:
        if own_client:
            http.close()


def parse_gmaps_url(url: str) -> GmapsRoute:
    """Lang-URL (oder api=1-Form) parsen. Kein Netzzugriff."""
    split = urlsplit(url)
    path = split.path

    if "/maps/dir" not in path and "/dir/" not in path:
        raise RouteInputError(
            "Das ist kein Google-Maps-Routenlink (es fehlt /maps/dir/...). "
            "In Google Maps eine Route berechnen und deren Link kopieren.")

    query = parse_qs(split.query)
    if query.get("api") == ["1"]:
        return _parse_api1(query)

    segments = path.split("/")
    try:
        start = segments.index("dir") + 1
    except ValueError:
        raise RouteInputError(
            "Google-Maps-Link ohne Wegpunkte "
            "(…/maps/dir/<start>/<ziel>/…).") from None

    names: list[str] = []
    blob = ""
    for seg in segments[start:]:
        if seg.startswith("@"):
            continue  # Karten-Viewport, kein Wegpunkt
        if seg.startswith("data="):
            blob = seg
            break
        if _PARAM_SEGMENT.match(seg):
            continue  # Parameter-Segment (z. B. am=t), kein Wegpunkt
        if seg:
            names.append(unquote_plus(seg))

    waypoints = [_waypoint_from_name(n) for n in names]

    # Präzise Koordinaten aus dem data=-Blob: ein !1d<lon>!2d<lat>-Paar
    # je Wegpunkt, in Routen-Reihenfolge (verifiziert 2026-07-12).
    pairs = [(float(lat), float(lon))
             for lon, lat in _BLOB_PAIR.findall(blob)]
    if pairs:
        if len(pairs) == len(waypoints):
            for wp, (lat, lon) in zip(waypoints, pairs, strict=True):
                wp.lat, wp.lon = lat, lon
        elif len(pairs) > len(waypoints) >= 2:
            # Mehr Koordinaten als Namen (z. B. per Drag gesetzte Vias):
            # erstes/letztes Paar den benannten Enden zuordnen, Rest als
            # unbenannte Zwischenpunkte in Reihenfolge.
            first, *mid, last = pairs
            waypoints[0].lat, waypoints[0].lon = first
            waypoints[-1].lat, waypoints[-1].lon = last
            vias = [LinkWaypoint(f"Via {i + 1}", lat, lon)
                    for i, (lat, lon) in enumerate(mid)]
            waypoints = [waypoints[0], *vias, *waypoints[1:]]
        # Weniger Paare als Namen: Blob unvollständig -> Namen später geocodieren

    if len(waypoints) < 2:
        raise RouteInputError(
            "Der Link enthält keine vollständige Route (mindestens Start "
            "und Ziel nötig).")

    modes = _BLOB_MODE.findall(blob)
    mode = _MODE_BY_3E.get(modes[-1]) if modes else None
    _reject_transit(mode)
    return GmapsRoute(waypoints=waypoints, mode=mode)


def _parse_api1(query: dict[str, list[str]]) -> GmapsRoute:
    def q(name: str) -> str:
        return (query.get(name) or [""])[0].strip()

    origin, destination = q("origin"), q("destination")
    if not origin or not destination:
        raise RouteInputError(
            "api=1-Link ohne origin/destination — Route unvollständig.")
    names = [origin]
    names += [w for w in q("waypoints").split("|") if w.strip()]
    names.append(destination)
    mode = _MODE_BY_TRAVELMODE.get(q("travelmode").lower()) or None
    _reject_transit(mode)
    return GmapsRoute(waypoints=[_waypoint_from_name(n) for n in names],
                      mode=mode)


def _waypoint_from_name(name: str) -> LinkWaypoint:
    m = _COORD_SEGMENT.match(name.strip())
    if m:  # Pfadsegment ist bereits "lat,lon"
        lat, lon = float(m.group(1)), float(m.group(2))
        return LinkWaypoint(f"{lat:.5f}, {lon:.5f}", lat, lon)
    return LinkWaypoint(name.strip())


def _reject_transit(mode: str | None) -> None:
    if mode == "transit":
        raise RouteInputError(
            "Der Link ist eine ÖPNV-Route — dafür ist bm-rail zuständig "
            "(bmtools rail).")
