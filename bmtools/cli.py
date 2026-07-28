"""bmtools: gemeinsamer CLI-Einstieg für den BM-Routencheck.

Aufruf:
    bmtools              Menü der verfügbaren Tools
    bmtools rail [...]   Tool direkt starten (Argumente werden durchgereicht)

Neue Tools werden nur in TOOLS registriert; jedes Tool bringt seine
eigene main() mit (inkl. eigener --help und ggf. interaktivem Modus).
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

import questionary
from questionary import Choice, Separator
from rich.console import Console

from . import cache_admin, gui, ui


def _rail_main(gui_start: bool = True) -> int:
    from .rail.cli import main
    return main(gui_start=gui_start)


def _car_main(gui_start: bool = True) -> int:
    from .road.cli import main_car
    return main_car(gui_start=gui_start)


def _bike_main(gui_start: bool = True) -> int:
    from .road.cli import main_bike
    return main_bike(gui_start=gui_start)


# name -> (Icon, Kurzbeschreibung, Einstiegsfunktion); das bool-Argument
# der Einstiegsfunktion: darf das Tool die GUI automatisch öffnen?
TOOLS: dict[str, tuple[str, str, Callable[[bool], int]]] = {
    "bahn": ("🚆", "Bahnstrecke — Zugverbindung wählen, Relais entlang "
                   "der Fahrt", _rail_main),
    "auto": ("🚗", "Autoroute — Google-Maps-Link einfügen oder "
                   "Start/Ziel eingeben", _car_main),
    "rad": ("🚴", "Radroute — Google-Maps-/Komoot-Link, GPX-Datei oder "
                  "Start/Ziel", _bike_main),
}

# Englische Namen bleiben als stille Aliasse gültig (Skript-Kompatibilität)
ALIASES = {"rail": "bahn", "car": "auto", "bike": "rad"}


def _usage(console: Console) -> None:
    console.print("Aufruf: [bold]bmtools <tool> \\[Optionen][/bold] "
                  "oder [bold]bmtools[/bold] für das Menü\n",
                  highlight=False)
    console.print("Verfügbare Tools:")
    for name, (icon, desc, _) in TOOLS.items():
        console.print(f"  {icon} [{ui.LIGHT_BLUE} bold]{name:<5}[/] {desc}",
                      highlight=False)
    console.print(f"  🧹 [{ui.LIGHT_BLUE} bold]{'cache':<5}[/] "
                  "Cache-Übersicht anzeigen; --leeren löscht alle "
                  "gecachten Daten", highlight=False)
    console.print("\nHilfe je Tool: [bold]bmtools <tool> --help[/bold]",
                  highlight=False)
    console.print("Ohne Argumente öffnet sich auf dem Desktop die "
                  "grafische Oberfläche;\n"
                  "[bold]--terminal[/bold] erzwingt das Terminal-Menü, "
                  "[bold]--gui[/bold] das Fenster.", highlight=False)


def _cache_uebersicht(console: Console) -> tuple[list[cache_admin.CacheBereich], int]:
    """Belegten Cache je Bereich ausgeben; (Bereiche, Gesamtbytes)."""
    liste = cache_admin.bereiche()
    gesamt = sum(b.groesse_bytes for b in liste)
    console.print("[bold]Belegter Disk-Cache:[/bold]")
    for b in liste:
        console.print(
            f"  {b.name:<44} {b.dateien:>5} "
            f"{'Dateien' if b.dateien != 1 else 'Datei  '} "
            f"{cache_admin.groesse_mensch(b.groesse_bytes):>10}",
            highlight=False)
    console.print(
        f"  [bold]{'Gesamt':<44} {sum(b.dateien for b in liste):>5} "
        f"Dateien {cache_admin.groesse_mensch(gesamt):>10}[/bold]",
        highlight=False)
    return liste, gesamt


def _cache_main() -> int:
    """bmtools cache [--leeren]: Übersicht anzeigen bzw. alles löschen."""
    ui.argparse_deutsch()
    ap = argparse.ArgumentParser(
        prog=sys.argv[0],
        description="Zeigt den belegten Disk-Cache (API-Antworten, "
                    "Höhenkacheln) und leert ihn auf Wunsch. Der nächste "
                    "Lauf lädt gelöschte Daten automatisch neu.")
    ap.add_argument("--leeren", "--clear", dest="leeren",
                    action="store_true",
                    help="alle gecachten Daten löschen (ohne Rückfrage)")
    args = ap.parse_args(sys.argv[1:])
    console = Console()
    liste, gesamt = _cache_uebersicht(console)
    if not args.leeren:
        console.print("\n[dim]Leeren mit: bmtools cache --leeren[/dim]")
        return 0
    if gesamt == 0:
        console.print("\nDer Cache ist bereits leer.")
        return 0
    frei = cache_admin.leeren(liste)
    console.print(f"\n[green]Cache geleert[/green] — "
                  f"{cache_admin.groesse_mensch(frei)} freigegeben.")
    return 0


def _cache_leeren_interaktiv(console: Console) -> None:
    """Menüpunkt »Cache leeren«: Übersicht, Rückfrage (Default Nein),
    löschen. Ctrl-C/ESC zählt als Nein."""
    liste, gesamt = _cache_uebersicht(console)
    if gesamt == 0:
        console.print("\nDer Cache ist bereits leer.")
        return
    console.print("[dim]Der nächste Lauf lädt Relais-Daten und "
                  "Höhenkacheln neu herunter.[/dim]")
    if not questionary.confirm(
            f"Alle gecachten Daten löschen "
            f"({cache_admin.groesse_mensch(gesamt)})?",
            default=False, style=ui.QSTYLE).ask():
        console.print("[dim]Nichts gelöscht.[/dim]")
        return
    frei = cache_admin.leeren(liste)
    console.print(f"[green]Cache geleert[/green] — "
                  f"{cache_admin.groesse_mensch(frei)} freigegeben.")


def _update_pruefung_starten() -> Any:
    """Hintergrundprüfung anwerfen — oder None, wenn abgeschaltet.

    Darf den Start unter keinen Umständen aufhalten oder zum Scheitern
    bringen; im Zweifel passiert einfach nichts.
    """
    try:
        from bmtools.gui import einstellungen
        from bmtools.update.terminal import Hintergrundpruefung
        werte = einstellungen.laden()
        if not werte.get("update_pruefen", True):
            return None
        return Hintergrundpruefung(
            mit_vorabversionen=bool(werte.get("update_vorab", False))
        ).starten()
    except Exception:
        return None


def main() -> int:
    console = Console()

    argv = sys.argv[1:]
    # --gui/--terminal vor dem Toolnamen (GUI-UMBAU.md, 2026-07-18):
    # --terminal erzwingt Menü bzw. Tool-Assistent im Terminal, --gui
    # das Fenster. Hinter dem Toolnamen übernehmen die Tools die Flags
    # selbst (bmtools bahn --gui wird durchgereicht).
    gui_erzwungen = terminal_erzwungen = False
    if argv and argv[0] in ("--gui", "--terminal"):
        gui_erzwungen = argv[0] == "--gui"
        terminal_erzwungen = not gui_erzwungen
        argv = argv[1:]
    if gui_erzwungen and argv:
        console.print("[red]--gui bitte hinter dem Toolnamen angeben, "
                      "z. B. 'bmtools bahn --gui'.[/red]")
        return 2

    if argv:
        tool = ALIASES.get(argv[0], argv[0])
        if tool in ("-h", "--help"):
            _usage(console)
            return 0
        # Kein argparse-Parser auf dieser Ebene (reiner Dispatcher) —
        # --version daher von Hand. Der Rauchtest im Release-Workflow
        # prüft darüber, dass das gebaute Binary seine Version kennt.
        if tool in ("-V", "--version"):
            from bmtools.version import eigene_version, version_anzeige
            console.print(
                f"BM-Routencheck {version_anzeige(eigene_version())}")
            return 0
        if tool == "--update":
            from bmtools.update.terminal import update_ausfuehren
            return update_ausfuehren(
                console,
                mit_vorabversionen="--mit-vorabversionen" in argv[1:])
        if tool == "cache":
            sys.argv = ["bmtools cache", *argv[1:]]
            return _cache_main()
        if tool not in TOOLS:
            console.print(f"[red]Unbekanntes Tool: {tool!r}[/red]\n")
            _usage(console)
            return 2
        # Argumente ans Tool durchreichen (argv[0] für dessen --help-Anzeige)
        sys.argv = [f"bmtools {tool}", *argv[1:]]
        # Update-Prüfung nebenher: startet jetzt, meldet sich erst nach
        # dem Lauf und nur auf einer echten Konsole — Skripte und Pipes
        # bleiben unbehelligt (DEVELOPER.md „Selbst-Updater“).
        pruefung = _update_pruefung_starten()
        tool_code = TOOLS[tool][2](not terminal_erzwungen)
        if pruefung is not None:
            pruefung.hinweis_ausgeben(console)
        return tool_code

    if not terminal_erzwungen:
        code = gui.start_oder_none(console, None, erzwungen=gui_erzwungen)
        if code is not None:
            return code

    if not sys.stdin.isatty():
        _usage(console)
        return 2

    console.print()
    ui.banner(console, "BM-Routencheck",
              "Welche DMR- und FM-Relais erreichst du unterwegs? — "
              "Bericht, Karte, CSV und Codeplug je Route")
    choices = [
        Choice(f"{icon}  {name:<5} {desc}", value=name)
        for name, (icon, desc, _) in TOOLS.items()
    ]
    choices += [
        Separator(),
        Choice("🧹  Cache leeren — gespeicherte API-Antworten und "
               "Höhenkacheln löschen", value="cache"),
        # Achtung: value=None hieße bei questionary "Titel als Wert" —
        # deshalb Sentinel "ende"; echtes None kommt nur von Ctrl-C/ESC
        Choice("🚪  Beenden", value="ende"),
    ]
    code = 0
    # Beta-Wunsch 2026-07-17: Nach einem Lauf nicht sofort beenden,
    # sondern zurück zur Tool-Auswahl anbieten (Ctrl-C/ESC = beenden).
    while True:
        tool = questionary.select(
            "Welches Tool?", choices=choices,
            style=ui.QSTYLE, pointer=ui.POINTER, qmark="",
        ).ask()
        if tool is None or tool == "ende":
            console.print("[dim]Bis zum nächsten Mal — 73![/dim]")
            return code
        if tool == "cache":
            console.print()
            _cache_leeren_interaktiv(console)
            console.print()
            continue
        console.print()
        sys.argv = [f"bmtools {tool}"]
        # Menü läuft schon im Terminal — das Tool darf kein Fenster öffnen
        code = TOOLS[tool][2](False)
        console.print()
        weiter = questionary.select(
            "Und jetzt?",
            choices=[
                Choice("🔁  Neuer Lauf — zurück zur Tool-Auswahl", "nochmal"),
                Choice("🚪  Beenden", "ende"),
            ],
            style=ui.QSTYLE, pointer=ui.POINTER, qmark="",
        ).ask()
        if weiter != "nochmal":
            return code
        console.print()


if __name__ == "__main__":
    sys.exit(main())
