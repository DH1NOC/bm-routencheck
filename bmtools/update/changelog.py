"""Release-Notes für den »Was ist neu«-Dialog nach einem Update.

Reine Anzeige-Daten: Die Notes kommen unbeglaubigt von der GitHub-API
und treffen — anders als beim Updater (pruefen.py) — keine Entscheidung.
Die GUI stellt sie ausschließlich als escapten Text dar. Deshalb darf
hier auch die Version aus dem Tag-Namen gelesen werden, die beim
Update-Angebot tabu ist.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from packaging.version import InvalidVersion, Version

from .pruefen import API, ZEITLIMIT

NOTES_MAX = 20_000  # Zeichen je Release — Anzeige-Deckel gegen Müll-Antworten


@dataclass(frozen=True)
class ReleaseNotes:
    version: str
    notes: str


def notes_zwischen(von: str, bis: str, *,
                   client: httpx.Client | None = None) -> list[ReleaseNotes]:
    """Notes aller Releases mit von < Version <= bis, neueste zuerst.

    Betas erscheinen nur, wenn sie selbst die installierte Version
    (bis) sind — wer über Betas hinweg auf die nächste stabile Version
    aktualisiert, bekommt deren Roh-Commit-Listen nicht vorgesetzt.
    Jeder Fehler (kein Netz, kaputte Antwort, unlesbare Versionen)
    ergibt schlicht [] — der Dialog entfällt dann.
    """
    try:
        v_von, v_bis = Version(von), Version(bis)
    except InvalidVersion:
        return []

    def behalten(v: Version) -> bool:
        return v_von < v <= v_bis and (not v.is_prerelease or v == v_bis)

    return _abrufen(behalten, client)


def notes_zu(version: str, *,
             client: httpx.Client | None = None) -> list[ReleaseNotes]:
    """Nur die Notes dieser einen Version.

    Für den ersten Lauf nach einem Update aus einer Fassung ohne
    changelog_stand-Marker: Welche Version vorher lief, weiß da niemand
    mehr — wenigstens das Neue der jetzt laufenden Version gehört
    gezeigt (Nutzerentscheidung 2026-07-30). Fehlertoleranz wie bei
    notes_zwischen: im Zweifel [].
    """
    try:
        v = Version(version)
    except InvalidVersion:
        return []
    return _abrufen(lambda kandidat: kandidat == v, client)


def _abrufen(behalten: Callable[[Version], bool],
             client: httpx.Client | None) -> list[ReleaseNotes]:
    """Die Releases holen und die behaltenen liefern, neueste zuerst."""
    eigener_client = client is None
    client = client or httpx.Client(timeout=ZEITLIMIT, verify=True,
                                    follow_redirects=True)
    try:
        antwort = client.get(API, params={"per_page": 30},
                             headers={"Accept": "application/vnd.github+json"})
        antwort.raise_for_status()
        eintraege = antwort.json()
        if not isinstance(eintraege, list):
            return []
        gefunden: list[tuple[Version, ReleaseNotes]] = []
        for eintrag in eintraege:
            if not isinstance(eintrag, dict) or eintrag.get("draft"):
                continue
            tag = eintrag.get("tag_name")
            if not isinstance(tag, str):
                continue
            try:
                v = Version(tag.removeprefix("v"))
            except InvalidVersion:
                continue
            if not behalten(v):
                continue
            body = eintrag.get("body")
            if not isinstance(body, str) or not body.strip():
                continue
            gefunden.append((v, ReleaseNotes(str(v), body[:NOTES_MAX])))
        gefunden.sort(key=lambda paar: paar[0], reverse=True)
        return [notes for _, notes in gefunden]
    except (httpx.HTTPError, ValueError):
        return []  # offline zu sein ist kein Fehlerfall
    finally:
        if eigener_client:
            client.close()
