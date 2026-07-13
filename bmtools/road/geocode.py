"""Geocoding freier Orts-/Adresseingaben über Transitous (MOTIS).

Ohne type-Filter liefert /geocode Adressen, Orte und Haltestellen
gemischt und hausnummerngenau (verifiziert 2026-07-13: „Winkelhaider
Str. 4A, Feucht" traf exakt die Koordinate aus dem Google-Link).
Gleiche API wie bm-rail — keine zusätzliche Abhängigkeit.
"""
from __future__ import annotations

import httpx

from bmtools.routelib.model import Waypoint

from . import RouteInputError

TRANSITOUS_GEOCODE = "https://api.transitous.org/api/v1/geocode"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"


def geocode_candidates(query: str, http: httpx.Client | None = None,
                       limit: int = 6) -> list[Waypoint]:
    own_client = http is None
    http = http or httpx.Client(timeout=30,
                                headers={"User-Agent": USER_AGENT})
    try:
        r = http.get(TRANSITOUS_GEOCODE,
                     params={"text": query, "language": "de"})
        r.raise_for_status()
        results = r.json()
        if not results:
            raise RouteInputError(f"Ort nicht gefunden: {query!r}")
        candidates = []
        for best in results[:limit]:
            region = ", ".join(
                a.get("name", "") for a in (best.get("areas") or [])[:3])
            candidates.append(Waypoint(name=best["name"], lat=best["lat"],
                                       lon=best["lon"], region=region))
        return candidates
    finally:
        if own_client:
            http.close()
