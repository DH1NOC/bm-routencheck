"""Dateien und Ordner mit dem Standardprogramm des Systems öffnen.

webbrowser.open() öffnete unter Windows im PyInstaller-Binary den
Standardbrowser nicht (Beta-Befund 2026-07-17): Die Browser-Erkennung
des Moduls greift dort ins Leere. os.startfile() bzw. open/xdg-open sind
der native „Doppelklick" und nutzen immer die Systemzuordnung — HTML
landet im Standardbrowser, Ordner im Dateimanager.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def system_oeffnen(ziel: Path) -> None:
    """Datei oder Ordner mit dem zugeordneten Standardprogramm öffnen.

    Fehler sind bewusst nicht fatal: Die Ausgaben liegen ja auf der
    Platte, das Öffnen ist nur Komfort."""
    try:
        if sys.platform == "win32":
            os.startfile(ziel)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(ziel)], check=False)
        else:
            subprocess.run(
                ["xdg-open", str(ziel)], check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        # Letzter Versuch (z. B. Linux ohne xdg-utils): webbrowser öffnet
        # file://-URIs meist ebenfalls korrekt.
        webbrowser.open(ziel.resolve().as_uri())
