"""PyInstaller-Einstieg: startet das bmtools-Menü.

bmtools/cli.py nutzt relative Imports und taugt daher nicht direkt als
PyInstaller-Skript — dieses Mini-Skript importiert das Paket regulär.
"""
import io
import sys

if sys.platform == "win32":
    # Legacy-Windows-Konsolen und Pipes melden oft cp1252 als Encoding —
    # die Emojis im Menü (🚆🚗🚴) führten dort zum UnicodeEncodeError
    # (Rauchtest-Befund 2026-07-17). UTF-8 mit Ersatzzeichen: Auf alten
    # Konsolen erscheint schlimmstenfalls ein Platzhalter, kein Absturz.
    for _strom in (sys.stdout, sys.stderr):
        if isinstance(_strom, io.TextIOWrapper):
            _strom.reconfigure(encoding="utf-8", errors="replace")

from bmtools.cli import main

if __name__ == "__main__":
    sys.exit(main())
