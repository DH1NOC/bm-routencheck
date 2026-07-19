"""Das GUI-Fenster (pywebview).

G3: Lädt das lokal gebündelte Frontend (static/: HTML/CSS/JS ohne
CDN-Zugriffe — Keyless/offlinefähig) und verbindet es über die
JS-Bridge (bridge.py). pywebview wird erst hier importiert — der
Terminal-Modus bleibt frei von GUI-Importen (und deren Startzeit).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import GuiStartFehler
from .bridge import Bridge

FENSTER_TITEL = "BM-Routencheck"
STATIC = Path(__file__).parent / "static"


def _macos_erster_klick_zaehlt() -> None:
    """WKWebView schluckt standardmäßig den App-aktivierenden Klick
    (acceptsFirstMouse = NO): Nach jedem Wechsel aus einer anderen App
    brauchte jede Bedienung einen Doppelklick, und der erste Klick in
    ein Textfeld setzte keinen Fokus — die Tastendrücke landeten in der
    vorherigen App (Abnahmebefund 2026-07-19, per CGEventPost
    reproduziert). Die Override lässt den ersten Klick normal wirken,
    wie es native macOS-Controls auch tun."""
    if sys.platform != "darwin":
        return
    try:
        import objc
        import WebKit

        def acceptsFirstMouse_(self: object, event: object) -> bool:
            return True

        objc.classAddMethod(
            WebKit.WKWebView, b"acceptsFirstMouse:",
            objc.selector(acceptsFirstMouse_,
                          selector=b"acceptsFirstMouse:",
                          signature=objc._C_NSBOOL + b"@:@"))
    except Exception:
        pass  # reine Bedienkomfort-Härtung — darf den Start nie verhindern


def _macos_aktivierung_nachfassen() -> None:
    """App-Aktivierung nach dem Start mehrfach nachfassen (nur macOS).

    Die Aktivierung ist auf neueren macOS-Versionen ein kooperativer
    Vorgang und scheitert aus Terminal-Kindprozessen sporadisch — dann
    ist das Fenster vorn, aber die App inaktiv: kein Hover-Cursor,
    kein Tastaturfokus (Befund 2026-07-19: »~50 % der Starts gesperrt,
    Neustart hilft«). Mehrfaches Nachaktivieren ist harmlos und
    gewinnt das Rennen; läuft als webview.start-Funktion im
    Hintergrund-Thread, Fehler bleiben folgenlos."""
    if sys.platform != "darwin":
        return
    try:
        import AppKit
        optionen = getattr(AppKit, "NSApplicationActivateIgnoringOtherApps",
                           1 << 1)
        app = AppKit.NSRunningApplication.currentApplication()
        for _ in range(3):
            time.sleep(0.4)
            app.activateWithOptions_(optionen)
    except Exception:
        pass


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
    _macos_erster_klick_zaehlt()
    bridge = Bridge(tool)
    fenster = webview.create_window(
        FENSTER_TITEL, url=str(STATIC / "index.html"), js_api=bridge,
        width=1100, height=780, min_size=(880, 600))
    bridge._fenster = fenster
    try:
        webview.start(_macos_aktivierung_nachfassen)
    except Exception as e:
        # Typischer Fall: Linux ohne Webview-Backend (GTK/WebKit2 oder
        # QtWebEngine) — pywebview meldet das erst beim Start.
        raise GuiStartFehler(str(e)) from e
    return 0
