"""Die eigene Programmversion — zur Laufzeit verlässlich ermittelt.

Wird für den Updater gebraucht: Ohne belastbare eigene Version lässt
sich kein Update-Angebot bewerten und keine Downgrade-Sperre bauen.

Zwei Quellen, bewusst in dieser Reihenfolge:

1. **Entwicklungs-Checkout** — `pyproject.toml` oberhalb des Pakets.
   `importlib.metadata` liefert dort die Version des letzten
   `pip install`, nicht die des Arbeitsstands: Im venv dieses Projekts
   meldete sie 0.1.2, während pyproject längst auf 0.3.0 stand
   (Befund 2026-07-27). Für `--version` ist das schlicht falsch.
2. **Installiert oder gefroren** — die Paket-Metadaten. Im
   PyInstaller-Binary liegen die nur vor, wenn der Build sie mitnimmt
   (`--copy-metadata bm-routencheck` in release.yml); genau deshalb
   prüft der Rauchtest dort auf allen drei Plattformen, dass
   `--version` die gebaute Version meldet.
"""
from __future__ import annotations

import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _metadata_version
from pathlib import Path

PAKET = "bm-routencheck"

# Fällt beides aus, ist das kein Grund für einen Absturz — aber der
# Updater muss es merken und still bleiben, statt auf einer erfundenen
# Version Entscheidungen zu treffen.
UNBEKANNT = "0+unbekannt"


def _aus_pyproject() -> str | None:
    """Version aus dem Arbeitsstand, nur im Quellcode-Checkout."""
    if getattr(sys, "frozen", False):
        return None
    pfad = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with pfad.open("rb") as f:
            wert = tomllib.load(f)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return None
    return str(wert) if isinstance(wert, str) else None


def eigene_version() -> str:
    aus_quelle = _aus_pyproject()
    if aus_quelle:
        return aus_quelle
    try:
        return _metadata_version(PAKET)
    except PackageNotFoundError:
        return UNBEKANNT


def version_bekannt() -> bool:
    """False heißt: Es darf kein Update angeboten werden."""
    return eigene_version() != UNBEKANNT
