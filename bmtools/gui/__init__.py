"""GUI-Start: Desktop-Erkennung und die Entscheidung GUI vs. Terminal.

Festlegung 2026-07-18 (GUI-UMBAU.md): Aufruf ohne Argumente öffnet auf
einem Desktop das Fenster, jeder Aufruf mit Argumenten und jede Umgebung
ohne Desktop bleibt Terminal; --gui/--terminal erzwingen das jeweilige
Verhalten. Die Entscheidung treffen die Kommando-Einstiege (bmtools,
bm-bahn, bm-auto, bm-rad) über start_oder_none(); das Fenster selbst
lebt in fenster.py, damit pywebview nur bei Bedarf importiert wird.
"""
from __future__ import annotations

import os
import sys

from rich.console import Console


class GuiStartFehler(RuntimeError):
    """GUI kann nicht starten (pywebview fehlt oder Backend-Problem)."""


def desktop_verfuegbar() -> bool:
    """Grobe Erkennung, ob ein grafisches Fenster möglich ist.

    SSH-Sitzungen zählen als Terminal (auch auf macOS/Windows wäre das
    Fenster dort unsichtbar); unter Linux/BSD entscheidet, ob ein X- oder
    Wayland-Display gesetzt ist. macOS und Windows haben sonst immer
    einen Desktop."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform == "darwin" or os.name == "nt":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def start_oder_none(console: Console, tool: str | None = None, *,
                    erzwungen: bool = False) -> int | None:
    """GUI starten, wenn angebracht; None heißt: im Terminal fortfahren.

    erzwungen (--gui): Ein Startfehler ist dann ein harter Fehler statt
    stillem Fallback — der Nutzer hat die GUI ausdrücklich verlangt.
    Ohne --gui fällt ein fehlgeschlagener Start (z. B. Linux ohne
    Webview-Backend) mit Hinweis auf den Terminal-Modus zurück."""
    if not (erzwungen or desktop_verfuegbar()):
        return None
    try:
        from .fenster import gui_starten
        return gui_starten(tool)
    except GuiStartFehler as e:
        if erzwungen:
            console.print(f"[red]GUI konnte nicht starten: {e}[/red]")
            return 1
        console.print(f"[yellow]GUI nicht verfügbar ({e}) — "
                      f"weiter im Terminal.[/yellow]")
        return None
