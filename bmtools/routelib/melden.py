"""Melde-/Fortschritts-Schnittstelle der Pipeline (G2, GUI-UMBAU.md).

run_pipeline() spricht nicht mehr direkt mit rich/questionary, sondern
mit einem Melder: text() für Zeilen (rich-Markup), balken() für Gruppen
von Fortschrittsbalken, status() für kurze Wartephasen, spur() für
Schleifen mit Balken, tabelle()/erfolg() für die Ergebnisdarstellung
und ja_nein() für Rückfragen. Der TerminalMelder reproduziert die
bisherige Konsolen-Ausgabe unverändert; die GUI bringt in G4 ihren
eigenen Melder mit (Events über die pywebview-Bridge).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

import questionary
from questionary import Choice
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TaskID, track

from bmtools import ui

if TYPE_CHECKING:
    from .report import RepeaterResult

T = TypeVar("T")


class Balken(Protocol):
    """Eine Gruppe gleichzeitig laufender Fortschrittsbalken (im
    Terminal: ein rich-Progress mit mehreren Tasks)."""

    def task(self, beschreibung: str, *, sichtbar: bool = True) -> int:
        """Neuen Balken anlegen; Gesamtzahl kommt später per update()."""

    def update(self, task: int, *, fertig: int | None = None,
               gesamt: int | None = None, sichtbar: bool | None = None,
               beschreibung: str | None = None) -> None:
        """Threadsicher (wird aus Download-Threads aufgerufen)."""


class Melder(Protocol):
    """Alles, was die Pipeline dem Nutzer mitteilt oder von ihm wissen
    will — Texte sind rich-Markup (eine GUI rendert oder strippt es)."""

    def text(self, markup: str) -> None: ...

    def balken(self) -> AbstractContextManager[Balken]: ...

    def status(self, text: str) -> AbstractContextManager[Callable[[str], None]]:
        """Kurze Wartephase; der gelieferte Updater ersetzt den Text."""

    def spur(self, elemente: Iterable[T], beschreibung: str) -> Iterator[T]:
        """Elemente durchreichen und dabei einen Balken zeigen."""

    def tabelle(self, results: list[RepeaterResult]) -> None:
        """Ergebnistabelle (Terminal: report.print_table)."""

    def erfolg(self, zeilen: list[str]) -> None:
        """Abschlussmeldung (Terminal: grünes Panel)."""

    def ergebnis(self, out_dir: Path, bericht: Path, karte: Path) -> None:
        """Fertige Ausgabedateien melden (G5): Das Terminal nennt sie
        schon im erfolg()-Panel (No-op), die GUI zeigt Bericht und
        Karte damit direkt im Fenster an."""

    def schritt(self, nummer: int, gesamt: int, text: str) -> None:
        """Pipeline-Schritt nummer/gesamt beginnt (U2-Befund
        2026-07-20): Die GUI speist daraus ihren Gesamt-Balken; das
        Terminal zeigt mit Texten und Balken schon genug (No-op)."""

    def ja_nein(self, frage: str) -> bool:
        """Rückfrage mit Default Nein; Abbruch (Ctrl-C/ESC) zählt als Nein."""

    def frage_ja(self, frage: str, default: bool = True) -> bool:
        """Verbindliche Rückfrage im Ablauf (z. B. »Route so berechnen?«);
        Abbruch wirft KeyboardInterrupt — wie _q im Assistenten."""

    def auswahl(self, frage: str, optionen: list[str],
                default: int | None = None) -> int:
        """Eine Option wählen lassen (Verbindungs-/Geocoding-Auswahl);
        liefert den Index. Abbruch wirft KeyboardInterrupt."""


class _TerminalBalken:
    def __init__(self, progress: Progress) -> None:
        self._p = progress

    def task(self, beschreibung: str, *, sichtbar: bool = True) -> int:
        return int(self._p.add_task(beschreibung, total=None,
                                    visible=sichtbar))

    def update(self, task: int, *, fertig: int | None = None,
               gesamt: int | None = None, sichtbar: bool | None = None,
               beschreibung: str | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if fertig is not None:
            kwargs["completed"] = fertig
        if gesamt is not None:
            kwargs["total"] = gesamt
        if sichtbar is not None:
            kwargs["visible"] = sichtbar
        if beschreibung is not None:
            kwargs["description"] = beschreibung
        self._p.update(TaskID(task), **kwargs)


class TerminalMelder:
    """Bisheriges Terminal-Verhalten: rich-Konsole, ui.fortschritt-Balken
    (inkl. ETA-Regel), questionary-Rückfragen."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def text(self, markup: str) -> None:
        self.console.print(markup)

    @contextmanager
    def balken(self) -> Iterator[Balken]:
        with ui.fortschritt(self.console) as p:
            yield _TerminalBalken(p)

    @contextmanager
    def status(self, text: str) -> Iterator[Callable[[str], None]]:
        with self.console.status(text) as s:
            yield s.update

    def spur(self, elemente: Iterable[T], beschreibung: str) -> Iterator[T]:
        yield from track(elemente, description=beschreibung,
                         console=self.console)

    def tabelle(self, results: list[RepeaterResult]) -> None:
        from .report import print_table
        print_table(results, self.console)

    def erfolg(self, zeilen: list[str]) -> None:
        self.console.print(Panel.fit("\n".join(zeilen),
                                     border_style="green"))

    def ergebnis(self, out_dir: Path, bericht: Path, karte: Path) -> None:
        pass  # das erfolg()-Panel nennt die Dateien bereits

    def schritt(self, nummer: int, gesamt: int, text: str) -> None:
        pass  # Terminal: Texte und Balken zeigen den Fortschritt schon

    def ja_nein(self, frage: str) -> bool:
        return bool(questionary.confirm(frage, default=False,
                                        style=ui.QSTYLE).ask())

    def frage_ja(self, frage: str, default: bool = True) -> bool:
        antwort = questionary.confirm(frage, default=default,
                                      style=ui.QSTYLE).ask()
        if antwort is None:
            raise KeyboardInterrupt
        return bool(antwort)

    def auswahl(self, frage: str, optionen: list[str],
                default: int | None = None) -> int:
        choices = [Choice(text, value=i) for i, text in enumerate(optionen)]
        antwort = questionary.select(
            frage, choices=choices,
            default=None if default is None else choices[default],
            style=ui.QSTYLE, pointer=ui.POINTER).ask()
        if antwort is None:
            raise KeyboardInterrupt
        return int(antwort)
