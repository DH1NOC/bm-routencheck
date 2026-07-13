"""bahn.de-Verbindungslink (vbid) -> konkrete Zugverbindung.

Der Teilen-Link von bahn.de (https://www.bahn.de/buchung/start?vbid=<uuid>)
verweist auf eine serverseitig gespeicherte Verbindung. Ein inoffizieller,
frei zugänglicher JSON-Endpunkt löst sie auf (verifiziert 2026-07-13):

    GET https://www.bahn.de/web/api/angebote/verbindung/<vbid>

Die Antwort enthält keine Streckengeometrie, aber im Feld hinfahrtRecon
einen HAFAS-Recon-String: je Fahrtabschnitt beide Bahnhöfe (Name,
Koordinaten in Mikrograd, EVA-Nummer), Abfahrt/Ankunft (deutsche
Lokalzeit) und die Zugnummer. Die Geometrie ermittelt danach
RoutePlanner.route_fixed abschnittsweise über Transitous.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from bmtools.routelib.model import Station

VERBINDUNG_API = "https://www.bahn.de/web/api/angebote/verbindung"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"
TZ = ZoneInfo("Europe/Berlin")

_VBID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

# Halt im Recon-String: A=1@O=<name>@X=<lon Mikrograd>@Y=<lat Mikrograd>@L=<eva>
_STOP = re.compile(r"A=1@O=([^@]+)@X=(-?\d+)@Y=(-?\d+)@L=(\d+)")
# Zeiten-/Zugblock eines Abschnitts: $<ab JJJJMMTTHHMM>$<an>$<zugname>$
_TIMES_TRAIN = re.compile(r"\$(\d{12})\$(\d{12})\$([^$]*)\$")


class BahnLinkError(RuntimeError):
    """bahn.de-Link unbrauchbar oder abgelaufen — Meldung ist nutzerfertig."""


@dataclass
class BahnLeg:
    """Ein Fahrtabschnitt (ein Zug, keine Umstiege)."""
    frm: Station
    to: Station
    dep: datetime                    # Lokalzeit (Europe/Berlin)
    arr: datetime
    train: str                       # z. B. "ICE 514"


@dataclass
class BahnVerbindung:
    vbid: str
    start_ort: str
    ziel_ort: str
    datum: datetime                  # Abfahrt laut bahn.de
    legs: list[BahnLeg]


def is_bahn_url(text: str) -> bool:
    return "bahn.de" in text and "vbid" in text


def extract_vbid(text: str) -> str:
    """vbid aus Link (oder direkt eingefügter UUID) ziehen."""
    m = _VBID.search(text)
    if not m:
        raise BahnLinkError(
            "Im Link steckt keine Verbindungs-ID (…?vbid=…). Auf bahn.de "
            "die Verbindung öffnen und den Teilen-Link kopieren.")
    return m.group(0).lower()


def _local_time(raw: str) -> datetime:
    return datetime.strptime(raw, "%Y%m%d%H%M").replace(tzinfo=TZ)


def parse_recon(recon: str) -> list[BahnLeg]:
    """Fahrtabschnitte aus dem HAFAS-Recon-String ziehen.

    Aufbau: '¶HKI¶<abschnitt>§<abschnitt>§…¶KC¶…'; Zugabschnitte beginnen
    mit 'T$', Fußwege u. ä. anders — die sind für die Strecke egal."""
    try:
        section = recon.split("¶HKI¶", 1)[1].split("¶", 1)[0]
    except IndexError:
        raise BahnLinkError(
            "bahn.de lieferte die Verbindung in einem unbekannten Format "
            "(kein HKI-Recon) — vermutlich hat sich die API geändert.") from None
    legs: list[BahnLeg] = []
    for part in section.split("§"):
        if not part.startswith("T$"):
            continue
        stops = _STOP.findall(part)
        times = _TIMES_TRAIN.search(part)
        if len(stops) != 2 or not times:
            continue
        frm, to = (Station(name=name, lat=int(y) / 1e6, lon=int(x) / 1e6)
                   for name, x, y, _eva in stops)
        legs.append(BahnLeg(
            frm=frm, to=to,
            dep=_local_time(times.group(1)), arr=_local_time(times.group(2)),
            train=" ".join(times.group(3).split()),
        ))
    if not legs:
        raise BahnLinkError(
            "Im bahn.de-Datensatz war kein Zugabschnitt erkennbar — "
            "vermutlich hat sich das Recon-Format geändert.")
    return legs


def fetch_verbindung(vbid: str, http: httpx.Client | None = None) -> BahnVerbindung:
    """Verbindung zur vbid von bahn.de laden und in Abschnitte zerlegen."""
    own_client = http is None
    http = http or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})
    try:
        r = http.get(f"{VERBINDUNG_API}/{vbid}",
                     headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise BahnLinkError(f"bahn.de nicht erreichbar: {e}") from e
    finally:
        if own_client:
            http.close()
    if r.status_code != 200:
        # Ungültige/abgelaufene IDs quittiert bahn.de mit 500 (getestet
        # 2026-07-13), daher keine Statuscode-Feinunterscheidung.
        raise BahnLinkError(
            f"bahn.de kennt die Verbindungs-ID nicht (HTTP {r.status_code}) "
            f"— der Link ist vermutlich abgelaufen. Auf bahn.de neu suchen "
            f"und einen frischen Teilen-Link erzeugen.")
    data = r.json()
    recon = data.get("hinfahrtRecon")
    if not recon:
        raise BahnLinkError(
            "bahn.de lieferte zu diesem Link keinen Fahrtverlauf "
            "(hinfahrtRecon fehlt).")
    return BahnVerbindung(
        vbid=vbid,
        start_ort=data.get("startOrt", "?"),
        ziel_ort=data.get("zielOrt", "?"),
        datum=datetime.fromisoformat(data["hinfahrtDatum"]),
        legs=parse_recon(recon),
    )
