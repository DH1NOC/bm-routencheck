"""Welche Plattform läuft hier, und darf überhaupt aktualisiert werden?

Die Plattformnamen sind der Vertrag zwischen `release.yml` (dort werden
die Manifest-Einträge benannt) und dem Client. Weichen sie voneinander
ab, findet der Client sein Artefakt nicht — ein Test hält beide Seiten
zusammen.
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

# Genau die Schlüssel, unter denen release.yml die Artefakte einträgt.
WINDOWS = "windows-x64"
MACOS = "macos-arm64"
LINUX = "linux-x64"


def plattform() -> str | None:
    """Kennung dieser Plattform, oder None, wenn nichts gebaut wird.

    Für Intel-Macs gibt es bewusst kein Binary (PROJEKTPLAN §3) — dort
    darf auch kein Update angeboten werden, sonst schöben wir einem
    Nutzer ein arm64-Bundle unter.
    """
    maschine = platform.machine().lower()
    if sys.platform == "win32":
        return WINDOWS if maschine in ("amd64", "x86_64") else None
    if sys.platform == "darwin":
        return MACOS if maschine == "arm64" else None
    if sys.platform.startswith("linux"):
        return LINUX if maschine == "x86_64" else None
    return None


def eigenes_programm() -> Path | None:
    """Was ersetzt werden müsste — None, wenn nicht gefroren.

    Aus dem Quellcode gestartet gibt es nichts zu tauschen; dort ist
    `git pull` der Weg. Auf macOS ist das Ziel das .app-Bundle, nicht
    das Binary tief darin.
    """
    if not getattr(sys, "frozen", False):
        return None
    pfad = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        # …/BM-Routencheck.app/Contents/MacOS/BM-Routencheck
        for eltern in pfad.parents:
            if eltern.suffix == ".app":
                return eltern
    return pfad


def beschreibbar(ziel: Path) -> bool:
    """Ließe sich `ziel` an Ort und Stelle ersetzen?

    Geprüft wird der ENTHALTENDE Ordner: Ersetzt wird über Umbenennen,
    und dafür zählt das Schreibrecht am Verzeichnis, nicht an der Datei.
    Fehlt es (Programme-Ordner, fremder Eigentümer), zeigen wir den
    Download-Link statt einen halben Tausch zu versuchen — Elevation
    fragen wir bewusst nie ab.
    """
    return os.access(ziel.parent, os.W_OK | os.X_OK)
