"""Update im Terminal: Hintergrund-Hinweis und `--update`.

Zwei Regeln, die den Zuschnitt bestimmen:

* **Nie blockieren.** Die Prüfung läuft in einem Daemon-Thread, der
  Hinweis kommt erst NACH dem Lauf und nur, wenn die Antwort da ist.
  Ohne Netz wartet niemand.
* **Nie in Skripten stören.** Ist die Ausgabe keine Konsole (Pipe,
  Cronjob), bleibt der Hinweis aus.
"""
from __future__ import annotations

import sys
import threading

from rich.console import Console

from bmtools.version import version_anzeige

from . import ablauf
from .pruefen import Angebot
from .ziel import eigenes_programm


class Hintergrundpruefung:
    """Sucht nebenher nach Updates; das Ergebnis holt man am Ende ab."""

    def __init__(self, *, mit_vorabversionen: bool = False) -> None:
        self._angebot: Angebot | None = None
        self._thread = threading.Thread(
            target=self._arbeiten, args=(mit_vorabversionen,),
            daemon=True, name="bm-update-pruefung")

    def starten(self) -> Hintergrundpruefung:
        self._thread.start()
        return self

    def _arbeiten(self, mit_vorabversionen: bool) -> None:
        try:
            self._angebot = ablauf.suche(mit_vorabversionen=mit_vorabversionen)
        except Exception:
            self._angebot = None

    def hinweis_ausgeben(self, console: Console) -> None:
        """Am Ende aufrufen. Wartet höchstens kurz — wer offline ist,
        soll nicht sekundenlang auf einen Hinweis warten, den es nicht
        gibt."""
        if not sys.stdout.isatty():
            return
        self._thread.join(timeout=1.5)
        if self._angebot is None:
            return
        console.print()
        for zeile in ablauf.hinweis_zeilen(self._angebot):
            console.print(f"[cyan]{zeile}[/cyan]")


def update_ausfuehren(console: Console, *,
                      mit_vorabversionen: bool = False) -> int:
    """`bmtools --update`: suchen, laden, tauschen, neu starten."""
    # Zuerst der Fall, der gar keiner ist: Aus dem Quellcode gestartet
    # gibt es nichts zu tauschen. Ohne diese Abfrage liefe man in
    # suche() -> None und bekäme „Bereits aktuell" zu lesen — eine
    # Auskunft, die hier schlicht nicht stimmt.
    if eigenes_programm() is None:
        console.print("Das läuft aus dem Quellcode — hier aktualisiert "
                      "[bold]git pull[/bold] (danach ggf. "
                      "[bold]pip install -e .[/bold]).")
        return 0

    console.print("Suche nach Updates …")
    try:
        angebot = ablauf.suche(mit_vorabversionen=mit_vorabversionen)
    except Exception as e:
        console.print(f"[red]Update-Prüfung fehlgeschlagen: {e}[/red]")
        return 1
    if angebot is None:
        console.print("[green]Bereits aktuell.[/green] (Vorabversionen "
                      "gegebenenfalls mit --mit-vorabversionen einbeziehen.)")
        return 0

    for zeile in ablauf.hinweis_zeilen(angebot)[:1]:
        console.print(zeile)
    console.print(f"Lade {angebot.artefakt.datei} …")
    with console.status("Herunterladen …") as status:
        def fortschritt(geladen: int, gesamt: int) -> None:
            if gesamt:
                status.update(f"Herunterladen … {geladen * 100 // gesamt} %")

        try:
            sofort = ablauf.durchfuehren(angebot, fortschritt)
        except ablauf.UpdateFehler as e:
            console.print(f"[red]Update abgebrochen:[/red] {e}")
            console.print("Die installierte Version ist unverändert.")
            return 1

    console.print(f"[green]Aktualisiert auf "
                  f"{version_anzeige(angebot.version)}.[/green]")
    if sofort:
        console.print("Beim nächsten Start läuft die neue Fassung.")
    else:
        # Windows: Der Helfer wartet auf unser Prozessende.
        console.print("Der Tausch erfolgt, sobald dieses Programm endet.")
    return 0
