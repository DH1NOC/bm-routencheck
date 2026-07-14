"""Geocoding freier Orts-/Adresseingaben über Transitous (MOTIS).

Ohne type-Filter liefert /geocode Adressen, Orte und Haltestellen
gemischt und hausnummerngenau (verifiziert 2026-07-13: „Winkelhaider
Str. 4A, Feucht" traf exakt die Koordinate aus dem Google-Link).
Gleiche API wie bm-rail — keine zusätzliche Abhängigkeit.
"""
from __future__ import annotations

from typing import Any

import httpx

from bmtools.routelib.model import Waypoint

from . import RouteInputError

TRANSITOUS_GEOCODE = "https://api.transitous.org/api/v1/geocode"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"


def _region(hit: dict[str, Any]) -> str:
    """Ortsangabe für die Trefferauswahl: 'PLZ Ort, Bundesland, Land'.

    Die areas-Liste kommt von grob nach fein (Land, Bundesland,
    Bezirk, …, Gemeinde); der eigentliche Ort ist der default-Eintrag
    (Fallback: der letzte, also feinste). Bundesland ist adminLevel 4,
    Land adminLevel 2.
    """
    areas = hit.get("areas") or []
    if not areas:
        return ""
    city = next((a["name"] for a in areas if a.get("default")),
                areas[-1]["name"])
    place = f"{hit.get('zip', '')} {city}".strip()
    levels = {int(a.get("adminLevel", 0)): a["name"] for a in areas}
    parts: list[str] = []
    for part in (place, levels.get(4), levels.get(2)):
        if part and part not in parts:  # Stadtstaaten: Berlin, Berlin, …
            parts.append(part)
    return ", ".join(parts)


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
        seen: set[str] = set()  # API liefert teils label-gleiche Treffer
        for best in results[:limit]:
            wp = Waypoint(name=best["name"], lat=best["lat"],
                          lon=best["lon"], region=_region(best))
            if wp.label not in seen:
                seen.add(wp.label)
                candidates.append(wp)
        return candidates
    finally:
        if own_client:
            http.close()
