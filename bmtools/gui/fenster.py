"""Das GUI-Fenster (pywebview).

G3: Lädt das lokal gebündelte Frontend (static/: HTML/CSS/JS ohne
CDN-Zugriffe — Keyless/offlinefähig) und verbindet es über die
JS-Bridge (bridge.py). pywebview wird erst hier importiert — der
Terminal-Modus bleibt frei von GUI-Importen (und deren Startzeit).
"""
from __future__ import annotations

from pathlib import Path

from . import GuiStartFehler
from .bridge import Bridge

FENSTER_TITEL = "BM-Routencheck"
STATIC = Path(__file__).parent / "static"


def gui_starten(tool: str | None = None) -> int:
    """Fenster öffnen und die pywebview-Hauptschleife laufen lassen.

    tool ('bahn'/'auto'/'rad') wählt den Start-Tab vor. Wirft
    GuiStartFehler statt ImportError/Backend-Exceptions, damit die
    Aufrufer (start_oder_none) sauber ins Terminal zurückfallen."""
    try:
        import webview
    except ImportError as e:
        raise GuiStartFehler(
            "pywebview ist nicht installiert — nachrüsten mit "
            "'pip install pywebview'") from e
    bridge = Bridge(tool)
    fenster = webview.create_window(
        FENSTER_TITEL, url=str(STATIC / "index.html"), js_api=bridge,
        width=1100, height=780, min_size=(880, 600))
    bridge._fenster = fenster
    try:
        webview.start()
    except Exception as e:
        # Typischer Fall: Linux ohne Webview-Backend (GTK/WebKit2 oder
        # QtWebEngine) — pywebview meldet das erst beim Start.
        raise GuiStartFehler(str(e)) from e
    return 0
