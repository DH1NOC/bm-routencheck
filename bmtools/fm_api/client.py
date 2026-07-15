"""HTTP-Client für relaislisten.darc.de (DL3EL, FM-Relais).

Anders als die BM-API gibt es keinen Volldump, nur eine Umkreissuche:
zurück kommen die `maxgateways` nächsten Relais um einen Punkt. Für
eine Route wird daher alle STEP_KM ein Stützpunkt abgefragt und über
(Call, QRG) dedupliziert. Je Stützpunkt sind es zwei Abrufe derselben
Query: CSV (Frequenzen, CTCSS) und GPX (dezimale Koordinaten).

Kein SLA, Hobby-Projekt — deshalb Disk-Cache (Rohantworten, Key =
auf 0,1° gerastete Stützpunkte, damit ähnliche Routen Treffer teilen)
und eine höhere Grundpause als bei der BM-API. Abgefragt wird der
geradezu gerasterte Punkt selbst; die Verschiebung von maximal ~7 km
ist gegen den 129-km-Radius der 200er-Antwort (F0-Dichte-Check)
unerheblich.
"""
from __future__ import annotations

import time

import httpx

from bmtools.bm_api.cache import Cache
from bmtools.routelib.corridor import Point, cumulative_km

from .models import FmRepeater
from .parser import dedupe, merge_gpx_coords, parse_csv, parse_gpx_coords

BASE_URL = "https://relaislisten.darc.de/cgi-bin/relais.pl"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

# httpx erwartet für params diesen Werttyp (list ist invariant)
QueryParams = list[tuple[str, "str | int | float | bool | None"]]

FM_LIST_TTL = 24 * 3600   # wie BM-Geräteliste: 1 Tag reicht
REQUEST_DELAY = 1.0       # Grundpause; Hobby-CGI, bewusst > BM-API
MAX_GATEWAYS = 200        # F0-Dichte-Check: 100 reicht im Ballungsraum nicht
STEP_KM = 50.0            # Stützpunkt-Raster entlang der Route
GRID_DEG = 0.1            # Cache-/Abfrage-Raster für Stützpunkte


def query_points(points: list[Point]) -> list[tuple[float, float]]:
    """Stützpunkte fürs Abfrage-Raster: alle STEP_KM plus Ziel, auf
    GRID_DEG gerundet und dedupliziert (kurze Routen → 1–2 Punkte)."""
    cum = cumulative_km(points)
    grid: list[tuple[float, float]] = []
    next_km = 0.0
    for p, k in zip(points, cum, strict=True):
        if k >= next_km or k == cum[-1]:
            cell = (round(p[0] / GRID_DEG) * GRID_DEG,
                    round(p[1] / GRID_DEG) * GRID_DEG)
            if cell not in grid:
                grid.append(cell)
            next_km = k + STEP_KM
    return grid


def _latlon_params(lat: float, lng: float) -> QueryParams:
    """Dezimalgrad → Formularfelder (Grad/Minuten, Halbkugel-Wörter).

    Auf dem GRID_DEG-Raster sind die Minuten ganzzahlig (0,1° = 6')."""
    lat_deg, lat_min = divmod(round(abs(lat) * 60), 60)
    lon_deg, lon_min = divmod(round(abs(lng) * 60), 60)
    return [
        ("sel", "latlon"),
        ("lat_deg", str(lat_deg)), ("lat_min", str(lat_min)),
        ("lat_NS", "Nord" if lat >= 0 else "South"),
        ("lon_deg", str(lon_deg)), ("lon_min", str(lon_min)),
        ("lon_EW", "Ost" if lng >= 0 else "West"),
        ("dxcc", "all"),  # Nachbarländer mitnehmen (Festlegung 2026-07-15)
        ("maxgateways", str(MAX_GATEWAYS)),
        ("type", "DL3EL"), ("type", "fr"),  # F0: FM-Basisliste + FM-Funknetz
        ("kmmls", "km"),
    ]


class DL3ELClient:
    def __init__(self, refresh: bool = False):
        """refresh=True ignoriert vorhandene Cache-Einträge (schreibt
        aber neue) — für einen erzwungenen Datenrefresh."""
        self._refresh = refresh
        self._http = httpx.Client(timeout=60,
                                  headers={"User-Agent": USER_AGENT})
        self._cache = Cache(FM_LIST_TTL, "bmtools/fm")
        self._delay = REQUEST_DELAY

    def _fetch_text(self, params: QueryParams) -> str:
        """Wie bm_api._fetch_json, nur Text- statt JSON-Antwort und ohne
        Retry-After-Logik (das CGI kennt kein Rate-Limit)."""
        last_error: Exception | None = None
        for attempt in range(5):
            if attempt:
                time.sleep(2 ** attempt)
            try:
                response = self._http.get(BASE_URL, params=params)
                response.raise_for_status()
            except httpx.HTTPError as e:
                last_error = e
                continue
            time.sleep(self._delay)
            # Content-Type nennt kein Charset — Antworten sind ISO-8859-1
            return response.content.decode("iso-8859-1")
        raise RuntimeError(
            f"relaislisten.darc.de nicht erreichbar: {last_error}")

    def repeaters_near(self, lat: float, lng: float) -> list[FmRepeater]:
        """FM-Relais um einen Punkt (die MAX_GATEWAYS nächsten).

        Der Punkt wird auf GRID_DEG gerastet — Cache-Key und Abfrage
        sind damit identisch."""
        glat = round(lat / GRID_DEG) * GRID_DEG
        glng = round(lng / GRID_DEG) * GRID_DEG
        key = f"latlon-{glat:.1f}-{glng:.1f}-{MAX_GATEWAYS}-DL3EL+fr"
        raw = None if self._refresh else self._cache.get(key)
        if raw is None:
            params = _latlon_params(glat, glng)
            raw = {"csv": self._fetch_text([*params, ("printas", "csv")]),
                   "gpx": self._fetch_text([*params, ("printas", "gpx")])}
            self._cache.set(key, raw)
        repeaters = parse_csv(raw["csv"])
        return merge_gpx_coords(repeaters, parse_gpx_coords(raw["gpx"]))

    def repeaters_along(self, points: list[Point]) -> list[FmRepeater]:
        """Alle FM-Relais entlang einer Route (STEP_KM-Raster, dedupliziert)."""
        found: list[FmRepeater] = []
        for lat, lng in query_points(points):
            found.extend(self.repeaters_near(lat, lng))
        return dedupe(found)
