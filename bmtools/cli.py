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

import questionary
from questionary import Choice, Separator
from rich.console import Console

from . import ui


def _rail_main() -> int:
    from .rail.cli import main
    return main()


def _car_main() -> int:
    from .road.cli import main_car
    return main_car()


def _bike_main() -> int:
    from .road.cli import main_bike
    return main_bike()


# name -> (Icon, Kurzbeschreibung, Einstiegsfunktion)
TOOLS: dict[str, tuple[str, str, Callable[[], int]]] = {
    "rail": ("🚆", "Bahnstrecke — Zugverbindung wählen, Relais entlang "
                   "der Fahrt", _rail_main),
    "car": ("🚗", "Autoroute — Google-Maps-Link einfügen oder "
                  "Start/Ziel eingeben", _car_main),
    "bike": ("🚴", "Radroute — Google-Maps-/Komoot-Link, GPX-Datei oder "
                   "Start/Ziel", _bike_main),
}


def _usage(console: Console) -> None:
    console.print("Aufruf: [bold]bmtools <tool> \\[Optionen][/bold] "
                  "oder [bold]bmtools[/bold] für das Menü\n",
                  highlight=False)
    console.print("Verfügbare Tools:")
    for name, (icon, desc, _) in TOOLS.items():
        console.print(f"  {icon} [{ui.LIGHT_BLUE} bold]{name:<5}[/] {desc}",
                      highlight=False)
    console.print("\nHilfe je Tool: [bold]bmtools <tool> --help[/bold]",
                  highlight=False)


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
        return TOOLS[tool][2]()

    if not sys.stdin.isatty():
        _usage(console)
        return 2

    console.print()
    ui.banner(console, "BrandmeisterTools",
              "Welche DMR-Relais erreichst du unterwegs? — Bericht, "
              "Karte, CSV und Codeplug je Route")
    choices = [
        Choice(f"{icon}  {name:<5} {desc}", value=name)
        for name, (icon, desc, _) in TOOLS.items()
    ]
    choices += [Separator(), Choice("🚪  Beenden", value=None)]
    tool = questionary.select(
        "Welches Tool?", choices=choices,
        style=ui.QSTYLE, pointer=ui.POINTER, qmark="",
    ).ask()
    if tool is None:
        console.print("[dim]Bis zum nächsten Mal — 73![/dim]")
        return 0
    console.print()
    sys.argv = [f"bmtools {tool}"]
    return TOOLS[tool][2]()


if __name__ == "__main__":
    sys.exit(main())
