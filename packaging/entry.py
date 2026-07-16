"""PyInstaller-Einstieg: startet das bmtools-Menü.

bmtools/cli.py nutzt relative Imports und taugt daher nicht direkt als
PyInstaller-Skript — dieses Mini-Skript importiert das Paket regulär.
"""
import sys

from bmtools.cli import main

if __name__ == "__main__":
    sys.exit(main())
