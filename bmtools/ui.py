"""Gemeinsamer CLI-Look für alle Tools: Banner, Farben, Prompt-Stil,
deutsche argparse-Texte.

Farbwelt = Palette der Karten (CVD-sicher, vgl. mapview.py):
Blau #0072B2/#56B4E9 als Primärfarbe, Orange #E69F00 als Akzent —
bewusst kein Rot/Grün (Farbfehlsichtigkeit des Nutzers).
"""
from __future__ import annotations

import argparse

from questionary import Style
from rich.console import Console
from rich.panel import Panel

BLUE = "#0072B2"
LIGHT_BLUE = "#56B4E9"
ORANGE = "#E69F00"

# Einheitlicher Stil für alle questionary-Prompts
QSTYLE = Style([
    ("qmark", f"fg:{ORANGE} bold"),
    ("question", "bold"),
    ("answer", f"fg:{ORANGE} bold"),
    ("pointer", f"fg:{LIGHT_BLUE} bold"),
    ("highlighted", f"fg:{LIGHT_BLUE} bold"),
    ("selected", f"fg:{LIGHT_BLUE}"),
    ("instruction", "fg:#888888"),
])

POINTER = "❯"
KEYS_HINT = "↑/↓ wählen · Enter bestätigen · Strg-C abbrechen"


def banner(console: Console, title: str, subtitle: str,
           icon: str = "📡", hint: str | None = KEYS_HINT) -> None:
    """Einheitlicher Kopf für Menü und Tool-Assistenten."""
    lines = [f"[bold]{icon} {title}[/bold]",
             f"[{LIGHT_BLUE}]{subtitle}[/{LIGHT_BLUE}]"]
    if hint:
        lines.append(f"[dim]{hint}[/dim]")
    console.print(Panel("\n".join(lines), border_style=BLUE,
                        padding=(0, 2), expand=False))


# argparse holt seine Texte per gettext — hier die deutsche Übersetzung
# der sichtbaren Standardtexte ("Keine Mischung", Nutzerwunsch 2026-07-13).
# Unbekannte Schlüssel bleiben unverändert (graceful fallback).
_ARGPARSE_DE = {
    "usage: ": "Aufruf: ",
    "options": "Optionen",
    "positional arguments": "Argumente",
    "show this help message and exit": "diese Hilfe anzeigen und beenden",
    "unrecognized arguments: %s": "unbekannte Argumente: %s",
    "the following arguments are required: %s":
        "folgende Argumente fehlen: %s",
    "expected one argument": "erwartet einen Wert",
    "expected at most one argument": "erwartet höchstens einen Wert",
    "expected at least one argument": "erwartet mindestens einen Wert",
    "invalid choice: %(value)r (choose from %(choices)s)":
        "ungültige Angabe: %(value)r (möglich: %(choices)s)",
    "invalid %(type)s value: %(value)r":
        "ungültiger Wert für %(type)s: %(value)r",
    "argument %(argument_name)s: %(message)s":
        "Argument %(argument_name)s: %(message)s",
    "not allowed with argument %s": "nicht kombinierbar mit Argument %s",
    "%(prog)s: error: %(message)s\n": "%(prog)s: Fehler: %(message)s\n",
}


def argparse_deutsch() -> None:
    """Vor dem Anlegen des ArgumentParser aufrufen."""
    argparse._ = (  # type: ignore[attr-defined]
        lambda s: _ARGPARSE_DE.get(s, s))
    argparse.ngettext = (  # type: ignore[attr-defined]
        lambda s, p, n: _ARGPARSE_DE.get(s if n == 1 else p, s if n == 1 else p))
