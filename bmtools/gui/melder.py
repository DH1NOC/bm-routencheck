"""GuiMelder: die Melder-Implementierung des Fensters (G4).

Statt rich/questionary schickt er JSON-Ereignisse über einen
sende-Callback (Bridge → evaluate_js → bmEreignis() im Frontend) und
blockiert bei Rückfragen den Pipeline-Thread, bis die Antwort über
Bridge.antwort() eintrifft. rich-Markup wird zu Klartext gestrippt —
die Texte selbst bleiben dieselben wie im Terminal.

Abbruch: Das Abbruch-Event setzt die Bridge; geprüft wird an allen
Melder-Aufrufen, die im Pipeline-Thread laufen — auch task-Updates,
denn lange Schritte (FM-Stützpunkte, Erreichbarkeit) melden zwischen
zwei Texten minutenlang nur Fortschritt (G4-Abnahmebefund 2026-07-19:
Abbrechen bei 2/21 wirkte tot). Updates aus Helfer-Threads (Kachel-
Downloads) werfen bewusst NICHT — ein Raise dort würde nur den
Download-Thread töten; darum merkt sich der Melder den Lauf-Thread
(markiere_lauf_thread) und wirft nur in diesem.
"""
from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from rich.text import Text

from bmtools.routelib.melden import Balken

T = TypeVar("T")

Ereignis = dict[str, Any]

# Ab dieser geschätzten Restzeit zeigt das Frontend eine ETA an
# (gleiche Regel wie ui.EtaSpalte im Terminal; sticky macht sie das JS)
ETA_AB_SEKUNDEN = 10.0


def _plain(markup: str) -> str:
    return Text.from_markup(markup).plain


class _GuiBalken:
    """Balken-Implementierung: Task-Ereignisse mit ETA-Schätzung."""

    def __init__(self, melder: GuiMelder) -> None:
        self._melder = melder
        self._sende = melder._sende_aktiv
        self._ids = melder._task_ids
        self._lock = threading.Lock()
        self._start: dict[int, float] = {}
        # Sticky-Regel wie ui.EtaSpalte: einmal über der Schwelle,
        # bleibt die ETA bis zum Task-Ende sichtbar (kein Flackern)
        self._eta_sichtbar: set[int] = set()

    def task(self, beschreibung: str, *, sichtbar: bool = True) -> int:
        task_id = next(self._ids)
        with self._lock:
            self._start[task_id] = time.monotonic()
        self._sende({"typ": "task_neu", "task": task_id,
                     "beschreibung": beschreibung, "sichtbar": sichtbar})
        return task_id

    def update(self, task: int, *, fertig: int | None = None,
               gesamt: int | None = None, sichtbar: bool | None = None,
               beschreibung: str | None = None) -> None:
        # Abbruch greift auch zwischen zwei Fortschrittsschritten —
        # aber nur im Lauf-Thread (Download-Threads laufen weiter)
        self._melder._pruefe_abbruch_im_lauf_thread()
        eta_s: float | None = None
        if fertig is not None and gesamt:
            with self._lock:
                start = self._start.get(task)
                if beschreibung is not None:
                    # Neustart des Balkens (z. B. Fallback Horizontmodell)
                    self._start[task] = time.monotonic()
                    start = None
            if start is not None and 0 < fertig < gesamt:
                laufzeit = time.monotonic() - start
                eta_s = laufzeit / fertig * (gesamt - fertig)
        ereignis: Ereignis = {"typ": "task_update", "task": task}
        if fertig is not None:
            ereignis["fertig"] = fertig
        if gesamt is not None:
            ereignis["gesamt"] = gesamt
        if sichtbar is not None:
            ereignis["sichtbar"] = sichtbar
        if beschreibung is not None:
            ereignis["beschreibung"] = beschreibung
        if eta_s is not None:
            with self._lock:
                if eta_s > ETA_AB_SEKUNDEN:
                    self._eta_sichtbar.add(task)
                if task in self._eta_sichtbar:
                    ereignis["eta_s"] = round(eta_s)
        self._sende(ereignis)


class _BalkenKontext:
    def __init__(self, melder: GuiMelder) -> None:
        self._m = melder

    def __enter__(self) -> Balken:
        self._m._pruefe_abbruch()
        return _GuiBalken(self._m)

    def __exit__(self, *exc: object) -> None:
        self._m._sende_aktiv({"typ": "balken_ende"})


class _StatusKontext:
    def __init__(self, melder: GuiMelder, text: str) -> None:
        self._m = melder
        self._text = text

    def __enter__(self) -> Callable[[str], None]:
        self._m._pruefe_abbruch()
        self._m._sende_aktiv({"typ": "status", "text": self._text})
        return lambda neu: self._m._sende_aktiv({"typ": "status",
                                                 "text": neu})

    def __exit__(self, *exc: object) -> None:
        self._m._sende_aktiv({"typ": "status", "text": None})


class GuiMelder:
    """Erfüllt melden.Melder; läuft im Pipeline-Hintergrund-Thread."""

    def __init__(self, sende: Callable[[Ereignis], None],
                 abbruch: threading.Event) -> None:
        self._sende = sende
        self._abbruch = abbruch
        self._task_ids = itertools.count(1)
        self._frage_ids = itertools.count(1)
        self._antworten: dict[int, Any] = {}
        self._antwort_da: dict[int, threading.Event] = {}
        self._lauf_thread: threading.Thread | None = None
        # Vom letzten erfolgreichen Lauf: Ordner für »Ausgabeordner
        # öffnen«, Dateien für Bridge.lade_ergebnis (srcdoc-Anzeige)
        self.ergebnis_ordner: Path | None = None
        self.ergebnis_dateien: dict[str, Path] = {}

    # ------------------------------------------------------ Abbruch

    def markiere_lauf_thread(self) -> None:
        """Vom Lauf-Thread bei Start aufrufen: nur er darf bei Abbruch
        aus task-Updates heraus KeyboardInterrupt bekommen."""
        self._lauf_thread = threading.current_thread()

    def _pruefe_abbruch(self) -> None:
        if self._abbruch.is_set():
            raise KeyboardInterrupt

    def _pruefe_abbruch_im_lauf_thread(self) -> None:
        if (self._abbruch.is_set()
                and threading.current_thread() is self._lauf_thread):
            raise KeyboardInterrupt

    def _sende_aktiv(self, ereignis: Ereignis) -> None:
        """Senden, solange nicht abgebrochen — nach dem Abbruch hat die
        Oberfläche bereits »fertig« gemeldet (Lauf.abbrechen), der
        auslaufende Arbeiter-Thread darf sie nicht mehr übermalen."""
        if not self._abbruch.is_set():
            self._sende(ereignis)

    # ------------------------------------------------------- Melder

    def text(self, markup: str) -> None:
        self._pruefe_abbruch()
        self._sende_aktiv({"typ": "text", "text": _plain(markup)})

    def balken(self) -> _BalkenKontext:
        return _BalkenKontext(self)

    def status(self, text: str) -> _StatusKontext:
        return _StatusKontext(self, text)

    def spur(self, elemente: Iterable[T], beschreibung: str) -> Iterator[T]:
        liste = list(elemente)
        with self.balken() as b:
            task = b.task(beschreibung)
            for i, element in enumerate(liste, 1):
                self._pruefe_abbruch()
                yield element
                b.update(task, fertig=i, gesamt=len(liste))

    def tabelle(self, results: list[Any]) -> None:
        # Interim bis G5 (Ergebnisansicht im Fenster): nur die Anzahl —
        # die vollständige Tabelle steht in bericht.html.
        self._sende_aktiv({"typ": "text",
                           "text": f"{len(results)} Relais im Ergebnis — "
                                   f"Details in bericht.html."})

    def erfolg(self, zeilen: list[str]) -> None:
        self._sende_aktiv({"typ": "erfolg",
                           "zeilen": [_plain(z) for z in zeilen]})

    def ergebnis(self, out_dir: Path, bericht: Path, karte: Path) -> None:
        """Fertige Dateien ans Fenster melden (G5-Ergebnisansicht).

        Die Inhalte holt sich das Frontend über Bridge.lade_ergebnis
        und zeigt sie per iframe.srcdoc — file-URLs im iframe blockiert
        WKWebView außerhalb des static-Verzeichnisses (Befund E2E-Test
        2026-07-19)."""
        self.ergebnis_ordner = out_dir
        self.ergebnis_dateien = {"bericht": bericht, "karte": karte}
        self._sende_aktiv({"typ": "ergebnis", "ordner": str(out_dir)})

    # ------------------------------------------------------- Fragen

    def ja_nein(self, frage: str) -> bool:
        # Die Abschluss-Rückfrage (»Ausgabeordner öffnen?«) hat im
        # Fenster keinen Platz als Dialog — G5 ersetzt sie durch Buttons.
        return False

    def frage_ja(self, frage: str, default: bool = True) -> bool:
        return bool(self._frage({"typ": "frage", "art": "ja_nein",
                                 "frage": frage, "default": default}))

    def auswahl(self, frage: str, optionen: list[str],
                default: int | None = None) -> int:
        return int(self._frage({"typ": "frage", "art": "auswahl",
                                "frage": frage, "optionen": optionen,
                                "default": default}))

    def _frage(self, ereignis: Ereignis) -> Any:
        self._pruefe_abbruch()
        frage_id = next(self._frage_ids)
        da = threading.Event()
        self._antwort_da[frage_id] = da
        self._sende_aktiv({**ereignis, "id": frage_id})
        # Polling statt blockem wait: Abbrechen muss die Frage lösen
        while not da.wait(0.2):
            self._pruefe_abbruch()
        antwort = self._antworten.pop(frage_id)
        del self._antwort_da[frage_id]
        if antwort is None:  # Dialog abgebrochen
            raise KeyboardInterrupt
        return antwort

    def antwort(self, frage_id: int, wert: Any) -> None:
        """Von der Bridge aufgerufen (JS-Thread): Antwort zustellen."""
        if frage_id in self._antwort_da:
            self._antworten[frage_id] = wert
            self._antwort_da[frage_id].set()
