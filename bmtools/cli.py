"""bmtools: gemeinsamer CLI-Einstieg für alle Brandmeister-Tools.

Aufruf:
    bmtools              Menü der verfügbaren Tools
    bmtools rail [...]   Tool direkt starten (Argumente werden durchgereicht)

Neue Tools werden nur in TOOLS registriert; jedes Tool bringt seine
eigene main() mit (inkl. eigener --help und ggf. interaktivem Modus).
"""
from __future__ import annotations

import sys
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt


def _rail_main() -> int:
    from .rail.cli import main
    return main()


# name -> (Kurzbeschreibung, Einstiegsfunktion)
TOOLS: dict[str, tuple[str, Callable[[], int]]] = {
    "rail": ("DMR-Relais entlang einer Bahnstrecke (Frequenzen, "
             "Talkgroups, Bericht, Karte, Codeplug)", _rail_main),
}


def _usage(console: Console) -> None:
    console.print("Aufruf: [bold]bmtools <tool> [Optionen][/bold] "
                  "oder [bold]bmtools[/bold] für das Menü\n")
    console.print("Verfügbare Tools:")
    for name, (desc, _) in TOOLS.items():
        console.print(f"  [cyan]{name:8}[/cyan] {desc}")
    console.print("\nHilfe je Tool: [bold]bmtools <tool> --help[/bold]")


def main() -> int:
    console = Console()

    if len(sys.argv) > 1:
        tool = sys.argv[1]
        if tool in ("-h", "--help"):
            _usage(console)
            return 0
        if tool not in TOOLS:
            console.print(f"[red]Unbekanntes Tool: {tool!r}[/red]\n")
            _usage(console)
            return 2
        # Argumente ans Tool durchreichen (argv[0] für dessen --help-Anzeige)
        sys.argv = [f"bmtools {tool}", *sys.argv[2:]]
        return TOOLS[tool][1]()

    if not sys.stdin.isatty():
        _usage(console)
        return 2

    console.print(Panel.fit(
        "[bold]bmtools[/bold] — Werkzeuge rund um das Brandmeister-Netzwerk",
        border_style="cyan",
    ))
    names = list(TOOLS)
    for i, name in enumerate(names, start=1):
        console.print(f"  [cyan]{i}[/cyan]  [bold]{name}[/bold] — {TOOLS[name][0]}")
    idx = IntPrompt.ask(
        "  [cyan]Welches Tool?[/cyan]",
        choices=[str(i) for i in range(1, len(names) + 1)], default=1)
    console.print()
    sys.argv = [f"bmtools {names[idx - 1]}"]
    return TOOLS[names[idx - 1]][1]()


if __name__ == "__main__":
    sys.exit(main())
