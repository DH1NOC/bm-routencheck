"""Ermittlung der Bahnstrecken-Geometrie über Transitous (MOTIS).

Primär: echte Fahrt-Polyline einer konkreten Verbindung, wählbar nach
Zuggattung, Zeit und Umstiegen. Fallback bei API-Ausfall: Luftlinien-
Interpolation zwischen den Bahnhöfen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import httpx

TRANSITOUS = "https://api.transitous.org/api/v1"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

# Zuggattungs-Filter (MOTIS-Mode-Enum)
MODE_SETS = {
    "alle": "RAIL",  # = HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_RAIL,SUBURBAN,SUBWAY
    "fern": "HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL",
    "nah": "REGIONAL_RAIL,SUBURBAN",
}

Point = tuple[float, float]  # (lat, lon)


class NoItineraryError(RuntimeError):
    """Verbindungssuche lieferte kein (passendes) Ergebnis."""


@dataclass
class PlanOptions:
    modes: str = "alle"              # Schlüssel in MODE_SETS
    time: datetime | None = None     # Abfahrts- bzw. Ankunftszeit
    arrive_by: bool = False          # time = Ankunft statt Abfahrt
    direct_only: bool = False        # nur Verbindungen ohne Umstieg
    num_itineraries: int = 5


@dataclass
class Station:
    name: str
    lat: float
    lon: float
    region: str = ""  # z. B. "Deutschland, Bayern, Mittelfranken"

    @property
    def label(self) -> str:
        return f"{self.name} ({self.region})" if self.region else self.name


@dataclass
class ItineraryOption:
    start: datetime                  # Lokalzeit
    end: datetime
    transfers: int
    trains: list[str]                # z. B. ["ICE 1185"]
    labels: list[str]                # Leg-Beschreibungen
    points: list[Point]

    @property
    def summary(self) -> str:
        dur = self.end - self.start
        h, m = divmod(int(dur.total_seconds()) // 60, 60)
        return (f"ab {self.start:%d.%m. %H:%M} an {self.end:%H:%M} "
                f"({h}:{m:02d} h, {self.transfers} Umstiege): "
                f"{' + '.join(self.trains) or '?'}")


@dataclass
class Route:
    points: list[Point]
    stations: list[Station]
    legs: list[str] = field(default_factory=list)
    is_interpolated: bool = False


# Wählt aus mehreren gefundenen Verbindungen eine aus (interaktiv o. ä.)
Chooser = Callable[[list[ItineraryOption], Station, Station], ItineraryOption]


def decode_polyline(encoded: str, precision: int = 7) -> list[Point]:
    """Google-Encoded-Polyline dekodieren (MOTIS nutzt Präzision 7)."""
    factor = 10 ** precision
    points: list[Point] = []
    index = lat = lon = 0
    while index < len(encoded):
        for is_lon in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        points.append((lat / factor, lon / factor))
    return points


def _local(iso: str) -> datetime:
    """API liefert UTC — für Anzeige in Systemzeitzone wandeln."""
    return datetime.fromisoformat(iso).astimezone()


class RoutePlanner:
    def __init__(self):
        self._http = httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT})

    def geocode_candidates(self, query: str, limit: int = 6) -> list[Station]:
        """Bahnhofs-Kandidaten inkl. Region (für Mehrdeutigkeits-Auswahl)."""
        r = self._http.get(
            f"{TRANSITOUS}/geocode",
            params={"text": query, "type": "STOP", "language": "de"},
        )
        r.raise_for_status()
        results = r.json()
        if not results:
            raise NoItineraryError(f"Bahnhof nicht gefunden: {query!r}")
        stations = []
        for best in results[:limit]:
            region = ", ".join(
                a.get("name", "") for a in (best.get("areas") or [])[:3])
            stations.append(Station(name=best["name"], lat=best["lat"],
                                    lon=best["lon"], region=region))
        return stations

    def geocode_station(self, query: str) -> Station:
        return self.geocode_candidates(query, limit=1)[0]

    def segment_options(
        self, frm: Station, to: Station, opts: PlanOptions
    ) -> list[ItineraryOption]:
        """Verbindungs-Kandidaten für einen Streckenabschnitt."""
        params: dict = {
            "fromPlace": f"{frm.lat},{frm.lon}",
            "toPlace": f"{to.lat},{to.lon}",
            "numItineraries": opts.num_itineraries,
            "transitModes": MODE_SETS[opts.modes],
        }
        if opts.time is not None:
            params["time"] = opts.time.astimezone().isoformat()
            params["arriveBy"] = "true" if opts.arrive_by else "false"
        r = self._http.get(f"{TRANSITOUS}/plan", params=params)
        r.raise_for_status()

        options: list[ItineraryOption] = []
        for it in r.json().get("itineraries") or []:
            points: list[Point] = []
            trains: list[str] = []
            labels: list[str] = []
            for leg in it["legs"]:
                if leg.get("mode") == "WALK":
                    continue
                geometry = leg.get("legGeometry") or {}
                decoded = decode_polyline(
                    geometry.get("points") or "", int(geometry.get("precision") or 7)
                )
                if points and decoded and points[-1] == decoded[0]:
                    decoded = decoded[1:]
                points.extend(decoded)
                label = leg.get("routeShortName") or leg.get("mode") or "?"
                trains.append(label)
                frm_name = (leg.get("from") or {}).get("name", "?")
                to_name = (leg.get("to") or {}).get("name", "?")
                labels.append(f"{label} ({frm_name} -> {to_name})")
            if len(points) < 2:
                continue
            options.append(ItineraryOption(
                start=_local(it["startTime"]), end=_local(it["endTime"]),
                transfers=int(it.get("transfers") or 0),
                trains=trains, labels=labels, points=points,
            ))

        if opts.direct_only:
            # maxTransfers=0 liefert bei Transitous fälschlich nichts ->
            # clientseitig filtern (verifiziert 2026-07-11)
            options = [o for o in options if o.transfers == 0]
        if not options:
            raise NoItineraryError(
                f"Keine passende Verbindung {frm.name} -> {to.name} gefunden "
                f"(Filter: {opts.modes}"
                f"{', nur direkt' if opts.direct_only else ''})."
            )
        return options

    def route_via_journey(
        self, stations: list[Station], opts: PlanOptions,
        chooser: Chooser | None = None,
    ) -> Route:
        """Echte Fahrt-Geometrie; bei Zwischenhalten je Abschnitt eine Wahl."""
        points: list[Point] = []
        legs: list[str] = []
        for frm, to in zip(stations, stations[1:]):
            options = self.segment_options(frm, to, opts)
            chosen = chooser(options, frm, to) if chooser else options[0]
            seg_points = chosen.points
            if points and seg_points and points[-1] == seg_points[0]:
                seg_points = seg_points[1:]
            points.extend(seg_points)
            legs.extend(chosen.labels)
        if len(points) < 2:
            raise NoItineraryError("Verbindung lieferte keine brauchbare Geometrie.")
        return Route(points=points, stations=stations, legs=legs)

    def route_interpolated(self, stations: list[Station]) -> Route:
        """Fallback: Luftlinie zwischen den angegebenen Bahnhöfen."""
        if len(stations) < 2:
            raise NoItineraryError("Fallback braucht mindestens zwei Bahnhöfe.")
        points = [(s.lat, s.lon) for s in stations]
        return Route(points=points, stations=stations, is_interpolated=True)

    def route(
        self, stations: list[Station], opts: PlanOptions | None = None,
        chooser: Chooser | None = None,
    ) -> Route:
        opts = opts or PlanOptions()
        try:
            return self.route_via_journey(stations, opts, chooser)
        except httpx.HTTPError as e:
            # Nur bei API-Ausfall auf Luftlinie ausweichen; "keine Verbindung
            # gefunden" soll der Nutzer sehen und die Filter anpassen.
            print(f"WARNUNG: Verbindungssuche fehlgeschlagen ({e}); "
                  f"nutze Luftlinien-Fallback zwischen den Bahnhöfen.")
            return self.route_interpolated(stations)
