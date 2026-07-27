"""Gemeinsamer CLI-Look für alle Tools: Banner, Farben, Prompt-Stil,
deutsche argparse-Texte.

Farbwelt = Palette der Karten (CVD-sicher, vgl. mapview.py):
Blau #0072B2/#56B4E9 als Primärfarbe, Orange #E69F00 als Akzent —
bewusst kein Rot/Grün (Farbfehlsichtigkeit des Nutzers).
"""
from __future__ import annotations

import argparse

import questionary
from questionary import Choice, Style
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

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


def add_fm_arguments(ap: argparse.ArgumentParser) -> None:
    """Gemeinsame FM-Umbau-Flags aller Tools: --modus plus die beiden
    Codeplug-Festlegungen (FM-UMBAU.md, 2026-07-15)."""
    ap.add_argument("--modus", "--mode", dest="modus",
                    choices=["dmr", "fm", "beide"], default="beide",
                    help="dmr = nur Brandmeister-DMR, fm = nur analoge "
                         "FM-Relais (relaislisten.darc.de), beide = "
                         "gemeinsam in Bericht/Karte/CSV (Default: beide)")
    ap.add_argument("--bandbreite", "--bandwidth", dest="bandbreite",
                    choices=["12.5", "25"], default="12.5", metavar="KHZ",
                    help="Bandbreite analoger FM-Kanäle im Codeplug: 12.5 "
                         "oder 25 kHz (Default: 12.5 — das Kanalraster "
                         "steht nicht in den DL3EL-Daten)")
    ap.add_argument("--ctcss-decode", dest="ctcss_decode",
                    action="store_true",
                    help="CTCSS auch als Empfangston setzen (Squelch öffnet "
                         "nur beim Relais-Ton); Default: Empfang offen, "
                         "Ton wird nur gesendet")


def add_version_argument(ap: argparse.ArgumentParser) -> None:
    """`--version` in allen Tools — der Updater braucht eine belastbare
    eigene Version, und der Rauchtest im Release-Workflow prüft über
    genau dieses Flag, dass das gebaute Binary sie auch kennt."""
    from bmtools.version import eigene_version, version_anzeige

    ap.add_argument("--version", action="version",
                    version=f"BM-Routencheck "
                            f"{version_anzeige(eigene_version())}",
                    help="Programmversion ausgeben und beenden")


def add_start_arguments(ap: argparse.ArgumentParser) -> None:
    """--gui/--terminal in allen Tools (GUI-UMBAU.md, 2026-07-18):
    Ohne Argumente entscheidet die Desktop-Erkennung, diese Flags
    erzwingen das jeweilige Verhalten."""
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--gui", action="store_true",
                   help="grafische Oberfläche öffnen (Standard bei Aufruf "
                        "ohne Argumente, wenn eine Desktop-Umgebung "
                        "erkannt wird)")
    g.add_argument("--terminal", action="store_true",
                   help="im Terminal bleiben (Assistent wie bisher, auch "
                        "auf dem Desktop)")


def modus_frage(default: str = "beide") -> questionary.Question:
    """Interaktive Modus-Auswahl (Aufrufer wickelt Abbruch via _q ab)."""
    return questionary.select(
        "Welche Relais?",
        choices=[
            Choice("beide — DMR und analoge FM-Relais", "beide"),
            Choice("dmr   — nur Brandmeister-DMR", "dmr"),
            Choice("fm    — nur analoge FM-Relais", "fm"),
        ],
        default=default, style=QSTYLE, pointer=POINTER)


# Ab dieser geschätzten Restzeit wird im Fortschrittsbalken eine ETA
# eingeblendet (Nutzerwunsch 2026-07-17: kurze Läufe ohne ETA-Rauschen)
ETA_AB_SEKUNDEN = 10.0


class EtaSpalte(TimeRemainingColumn):
    """Restzeit-Spalte, die erst ab ETA_AB_SEKUNDEN geschätzter Restzeit
    erscheint. Einmal sichtbar, bleibt sie bis zum Task-Ende stehen —
    sonst flackerte sie, sobald die Schätzung um die Schwelle pendelt."""

    def __init__(self) -> None:
        super().__init__(compact=True)
        self._sichtbar: set[TaskID] = set()

    def render(self, task: Task) -> Text:
        remaining = task.time_remaining
        if task.finished or remaining is None:
            return Text("")
        if remaining > ETA_AB_SEKUNDEN:
            self._sichtbar.add(task.id)
        if task.id not in self._sichtbar:
            return Text("")
        return Text.assemble(("noch ", "progress.remaining"),
                             super().render(task))


def fortschritt(console: Console) -> Progress:
    """Einheitlicher Fortschrittsbalken aller Tools: Beschreibung, Balken,
    X/Y, Prozent und ETA ab >10 s Restzeit (EtaSpalte).

    Verwendung: with ui.fortschritt(console) as p: t = p.add_task(...)"""
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style=LIGHT_BLUE, finished_style=BLUE,
                  pulse_style=ORANGE),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        EtaSpalte(),
        console=console)


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
