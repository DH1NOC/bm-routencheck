"""Gemeinsamer CLI-Look für alle Tools: Banner, Farben, Prompt-Stil.

Farbwelt = Palette der Karten (CVD-sicher, vgl. mapview.py):
Blau #0072B2/#56B4E9 als Primärfarbe, Orange #E69F00 als Akzent —
bewusst kein Rot/Grün (Farbfehlsichtigkeit des Nutzers).
"""
from __future__ import annotations

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
