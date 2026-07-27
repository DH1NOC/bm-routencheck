"""Gibt es eine neuere Version? — Abfrage, Verifikation, Entscheidung.

Der sicherheitskritische Teil ist die Reihenfolge (UPDATER.md §1):
Die GitHub-Antwort sagt nur, WO ein Manifest liegen könnte. Was danach
geschieht, richtet sich ausschließlich nach dem signierten Manifest.
Insbesondere kommt die Version, gegen die verglichen wird, NIE aus der
API — sonst könnte ein Angreifer mit gefälschter Antwort eine ältere,
echt signierte Fassung als „neu" ausgeben.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

from bmtools.version import eigene_version, version_bekannt

from .manifest import (
    MANIFEST_DATEI,
    SIGNATUR_DATEI,
    Artefakt,
    ManifestFehler,
    pruefe_manifest,
)
from .ziel import plattform

API = "https://api.github.com/repos/DH1NOC/bm-routencheck/releases"
ZEITLIMIT = 10.0
# Ein manipuliertes Gegenüber darf uns nicht mit Gigabytes zumüllen.
MANIFEST_MAX = 64 * 1024


@dataclass(frozen=True)
class Angebot:
    """Eine verifiziert neuere Version für diese Plattform."""
    version: str
    artefakt: Artefakt
    basis_url: str          # Ordner-URL, aus der das Artefakt kommt
    vorabversion: bool

    @property
    def datei_url(self) -> str:
        return f"{self.basis_url}/{self.artefakt.datei}"


def ist_neuer(kandidat: str, laufend: str) -> bool:
    """Streng größer nach PEP 440 — Downgrade-Sperre.

    `0.4.0b2 < 0.4.0` und `0.4.0 < 0.4.1b1`; unlesbare Versionen gelten
    nie als neuer (lieber kein Update als ein falsches).
    """
    try:
        return Version(kandidat) > Version(laufend)
    except InvalidVersion:
        return False


def ist_vorabversion(version: str) -> bool:
    """Ist das eine Beta? — beantwortet aus der Versionsnummer selbst.

    Absichtlich NICHT aus dem `prerelease`-Flag der GitHub-Antwort: Die
    ist unbeglaubigt. Wer sie fälschen kann, schöbe einem Nutzer mit
    abgeschaltetem Beta-Kanal sonst eine (echte, signierte) Vorabversion
    unter — kein Downgrade, aber eine Kanalwahl, die dem Nutzer gehört
    und nicht dem Netzweg. Unlesbares gilt sicherheitshalber als Beta.
    """
    try:
        return Version(version).is_prerelease
    except InvalidVersion:
        return True


def _release_urls(eintrag: dict[str, Any]) -> tuple[str, str, str] | None:
    """(manifest_url, signatur_url, basis_url) aus einem Release-Eintrag."""
    namen = {a.get("name"): a.get("browser_download_url")
             for a in eintrag.get("assets", []) or []
             if isinstance(a, dict)}
    manifest, signatur = namen.get(MANIFEST_DATEI), namen.get(SIGNATUR_DATEI)
    if not isinstance(manifest, str) or not isinstance(signatur, str):
        return None
    return manifest, signatur, manifest.rsplit("/", 1)[0]


def suche_update(*, mit_vorabversionen: bool = False,
                 client: httpx.Client | None = None) -> Angebot | None:
    """Neueres, verifiziertes Angebot für diese Plattform — oder None.

    None heißt in jedem Zweifelsfall »nichts anbieten«: kein Netz,
    keine bekannte eigene Version, keine Plattformunterstützung,
    Manifest fehlt oder ist nicht echt.
    """
    if not version_bekannt():
        return None
    ziel_plattform = plattform()
    if ziel_plattform is None:
        return None
    laufend = eigene_version()

    eigener_client = client is None
    # verify=True ist httpx-Vorgabe; hier nur zur Deutlichkeit, weil es
    # die erste Verteidigungslinie ist (die zweite ist die Signatur).
    client = client or httpx.Client(timeout=ZEITLIMIT, verify=True,
                                    follow_redirects=True)
    try:
        antwort = client.get(API, params={"per_page": 20},
                             headers={"Accept": "application/vnd.github+json"})
        antwort.raise_for_status()
        eintraege = antwort.json()
        if not isinstance(eintraege, list):
            return None

        bestes: Angebot | None = None
        for eintrag in eintraege:
            if not isinstance(eintrag, dict) or eintrag.get("draft"):
                continue
            # Nur eine Vorsortierung, um uns unnötige Abrufe zu sparen —
            # die verbindliche Antwort steht weiter unten im Manifest.
            if eintrag.get("prerelease") and not mit_vorabversionen:
                continue
            urls = _release_urls(eintrag)
            if urls is None:
                continue          # Release ohne Manifest — älter als 0.4.0
            manifest_url, signatur_url, basis = urls
            try:
                roh = client.get(manifest_url).content[:MANIFEST_MAX]
                signatur = client.get(signatur_url).content[:MANIFEST_MAX]
                geprueft = pruefe_manifest(roh, signatur)
            except (httpx.HTTPError, ManifestFehler):
                continue          # nicht echt oder nicht erreichbar
            # Ab hier zählt NUR noch das Manifest — auch für die Frage,
            # ob das eine Vorabversion ist.
            if not ist_neuer(geprueft.version, laufend):
                continue
            vorab = ist_vorabversion(geprueft.version)
            if vorab and not mit_vorabversionen:
                continue
            artefakt = geprueft.fuer(ziel_plattform)
            if artefakt is None:
                continue
            angebot = Angebot(version=geprueft.version, artefakt=artefakt,
                              basis_url=basis, vorabversion=vorab)
            if bestes is None or ist_neuer(angebot.version, bestes.version):
                bestes = angebot
        return bestes
    except (httpx.HTTPError, ValueError):
        return None               # offline zu sein ist kein Fehlerfall
    finally:
        if eigener_client:
            client.close()
