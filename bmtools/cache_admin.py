"""Verwaltung des Disk-Caches: Bereiche auflisten, Größe ermitteln, leeren.

Alle Caches liegen unter dem platformdirs-Cache-Verzeichnis: die
API-Antworten der Clients (JSON je Schlüssel, siehe bm_api.cache.Cache)
und die Höhenkacheln des Geländemodells (terrain/<zoom>/*.png).
Gelöscht wird je Bereich der konkrete Ordner — die Clients legen ihn
beim nächsten Lauf neu an und laden die Daten frisch.

Die Pfade werden mit denselben user_cache_dir-Aufrufen gebildet wie in
den Clients selbst; die Namespace-Liste hier muss zu den Cache(...)-
Aufrufen in bm_api/client.py und fm_api/client.py passen.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir

_BM_NAMESPACES = ("bmtools/devices", "bmtools/profiles", "bmtools/misc")
_FM_NAMESPACE = "bmtools/fm"


@dataclass(frozen=True)
class CacheBereich:
    name: str
    pfade: tuple[Path, ...]
    dateien: int
    groesse_bytes: int


def _bereich(name: str, pfade: tuple[Path, ...]) -> CacheBereich:
    dateien = 0
    groesse = 0
    for pfad in pfade:
        if not pfad.is_dir():
            continue
        for datei in pfad.rglob("*"):
            if datei.is_file():
                dateien += 1
                groesse += datei.stat().st_size
    return CacheBereich(name, pfade, dateien, groesse)


def bereiche() -> list[CacheBereich]:
    """Die drei Cache-Bereiche mit aktueller Dateizahl und Größe."""
    return [
        _bereich("Brandmeister-API (Geräte, Talkgroup-Profile)",
                 tuple(Path(user_cache_dir(ns)) for ns in _BM_NAMESPACES)),
        _bereich("FM-Relaisliste (relaislisten.darc.de)",
                 (Path(user_cache_dir(_FM_NAMESPACE)),)),
        _bereich("Höhenkacheln (Geländemodell)",
                 (Path(user_cache_dir("bmtools")) / "terrain",)),
    ]


def leeren(liste: list[CacheBereich] | None = None) -> int:
    """Alle Cache-Bereiche löschen; Rückgabe: freigegebene Bytes.

    ignore_errors: eine parallel laufende Instanz oder Windows-Locks
    sollen das Leeren nicht abbrechen — was gerade nicht löschbar ist,
    verfällt spätestens über die TTL."""
    if liste is None:
        liste = bereiche()
    for bereich in liste:
        for pfad in bereich.pfade:
            if pfad.is_dir():
                shutil.rmtree(pfad, ignore_errors=True)
    return sum(b.groesse_bytes for b in liste)


def groesse_mensch(n: int) -> str:
    """Bytes menschenlesbar mit deutschem Dezimalkomma (»3,4 MB«)."""
    wert = float(n)
    einheit = "B"
    for einheit in ("B", "kB", "MB", "GB"):
        if wert < 1000 or einheit == "GB":
            break
        wert /= 1000.0
    if einheit == "B":
        return f"{int(wert)} B"
    return f"{wert:.1f}".replace(".", ",") + f" {einheit}"
