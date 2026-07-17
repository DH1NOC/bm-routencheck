"""PyInstaller-Einstieg: startet das bmtools-Menü.

bmtools/cli.py nutzt relative Imports und taugt daher nicht direkt als
PyInstaller-Skript — dieses Mini-Skript importiert das Paket regulär.
"""
import io
import multiprocessing
import sys

if sys.platform == "win32":
    # Legacy-Windows-Konsolen und Pipes melden oft cp1252 als Encoding —
    # die Emojis im Menü (🚆🚗🚴) führten dort zum UnicodeEncodeError
    # (Rauchtest-Befund 2026-07-17). UTF-8 mit Ersatzzeichen: Auf alten
    # Konsolen erscheint schlimmstenfalls ein Platzhalter, kein Absturz.
    for _strom in (sys.stdout, sys.stderr):
        if isinstance(_strom, io.TextIOWrapper):
            _strom.reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    # Muss vor dem App-Start stehen: Windows/macOS starten multiprocessing-
    # Kindprozesse (Sichtfeld-Rendering, mapview.py) per Neuaufruf des
    # Binarys mit --multiprocessing-fork. Ohne freeze_support landete das
    # im bmtools-Menü statt im Worker (Beta-Befund 2026-07-17: Menü-Spam
    # und "process pool was terminated abruptly").
    multiprocessing.freeze_support()

    from bmtools.cli import main
    sys.exit(main())
