"""Komoot-Tour-Link -> fertige Routen-Geometrie.

Anders als bei Google zeigt der Link auf eine gespeicherte Tour mit
echter Geometrie — kein Nachrouten nötig. Abruf über die inoffizielle
v007-API (keyless, verifiziert 2026-07-12/13): öffentliche Touren
direkt, private mit dem share_token aus dem „Mit Link teilen"-Link.
Fallback: Koordinaten-JSON aus dem HTML der Tour-Seite (dort
eingebettet). Garantierter dritter Weg außerhalb dieses Moduls:
GPX-Export der Tour (--gpx).

URL-Formen: …/tour/<id>[?share_token=…] und …/smarttour/e<id>/…
(das e-Präfix ist abzuschneiden, die API kennt nur numerische IDs).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx

from . import RouteInputError
from bmtools.routelib.model import Point

API_TOUR = "https://api.komoot.de/v007/tours/{id}"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"
# Die HTML-Seite liefert nur an Browser-Kennungen vollen Inhalt
BROWSER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36")

_TOUR_ID = re.compile(r"/(?:smart)?tour/e?(\d+)")

# Komoot-Sportarten (informativ, für die Anzeige)
SPORT_LABEL = {
    "touringbicycle": "Fahrrad (Touren)", "racebike": "Rennrad",
    "mtb": "Mountainbike", "e_touringbicycle": "E-Bike",
    "hike": "Wandern", "jogging": "Laufen",
}


@dataclass
class KomootRef:
    tour_id: int
    share_token: str | None = None


@dataclass
class KomootTour:
    name: str
    sport: str
    distance_km: float
    points: list[Point]  # (lat, lon)


def is_komoot_url(url: str) -> bool:
    return "komoot." in urlsplit(url).netloc.lower()


def parse_komoot_url(url: str) -> KomootRef:
    split = urlsplit(url)
    m = _TOUR_ID.search(split.path)
    if not m:
        raise RouteInputError(
            "Das ist kein Komoot-Tour-Link (erwartet …/tour/<id> oder "
            "…/smarttour/e<id>/…).")
    token = (parse_qs(split.query).get("share_token") or [None])[0]
    return KomootRef(tour_id=int(m.group(1)), share_token=token)


def fetch_tour(ref: KomootRef, http: httpx.Client | None = None,
               page_url: str | None = None) -> KomootTour:
    """Tour-Metadaten + Geometrie laden (API, Fallback: HTML-Seite)."""
    own_client = http is None
    http = http or httpx.Client(timeout=30,
                                headers={"User-Agent": USER_AGENT})
    try:
        params = {"share_token": ref.share_token} if ref.share_token else {}
        base = API_TOUR.format(id=ref.tour_id)
        meta_r = http.get(base, params=params)
        if meta_r.status_code == 403:
            raise RouteInputError(
                "Komoot verweigert den Zugriff — die Tour ist privat. "
                "In Komoot „Mit Link teilen“ wählen und diesen Link "
                "verwenden (er enthält den share_token), oder die Tour "
                "als GPX exportieren und mit --gpx übergeben.")
        if meta_r.status_code == 404:
            raise RouteInputError(
                f"Komoot kennt keine Tour mit der ID {ref.tour_id} — "
                f"Link prüfen.")
        meta_r.raise_for_status()
        meta = meta_r.json()

        coord_r = http.get(f"{base}/coordinates", params=params)
        if coord_r.status_code == 200:
            items = coord_r.json().get("items") or []
        else:
            items = _items_from_html(http, page_url) if page_url else []
        points = [(it["lat"], it["lng"]) for it in items]
        if len(points) < 2:
            raise RouteInputError(
                "Komoot lieferte keine Tour-Geometrie — als Ausweg die "
                "Tour als GPX exportieren und mit --gpx übergeben.")
        return KomootTour(
            name=meta.get("name") or f"Komoot-Tour {ref.tour_id}",
            sport=meta.get("sport") or "",
            distance_km=(meta.get("distance") or 0.0) / 1000.0,
            points=points,
        )
    except httpx.HTTPError as e:
        raise RouteInputError(
            f"Komoot-Abruf fehlgeschlagen ({e}) — als Ausweg die Tour als "
            f"GPX exportieren und mit --gpx übergeben.")
    finally:
        if own_client:
            http.close()


def _items_from_html(http: httpx.Client, page_url: str) -> list[dict]:
    """Fallback: Koordinaten-Array aus dem eingebetteten (backslash-
    escapten) JSON der Tour-Seite ziehen. Best effort — bei Misserfolg
    leere Liste, der Aufrufer verweist dann auf den GPX-Weg."""
    r = http.get(page_url, follow_redirects=True,
                 headers={"User-Agent": BROWSER_AGENT})
    if r.status_code != 200:
        return []
    text = r.text.replace('\\"', '"')
    start = text.find('"coordinates":{"items":[')
    if start < 0:
        return []
    array_start = text.index("[", start)
    depth = 0
    for i in range(array_start, min(len(text), array_start + 4_000_000)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[array_start:i + 1])
                except ValueError:
                    return []
    return []
