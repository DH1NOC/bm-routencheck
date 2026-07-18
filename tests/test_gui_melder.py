"""Tests GuiMelder (G4): Ereignisse, Fragen über Threads, Abbruch."""
from __future__ import annotations

import threading
from typing import Any

import pytest

from bmtools.gui.melder import GuiMelder


def _melder():
    ereignisse: list[dict[str, Any]] = []
    abbruch = threading.Event()
    return GuiMelder(ereignisse.append, abbruch), ereignisse, abbruch


def test_text_strippt_markup():
    m, ereignisse, _ = _melder()
    m.text("[bold]Lade Brandmeister-Geräteliste …[/bold]")
    assert ereignisse == [{"typ": "text",
                           "text": "Lade Brandmeister-Geräteliste …"}]


def test_balken_task_und_ende():
    m, ereignisse, _ = _melder()
    with m.balken() as b:
        t = b.task("Höhenkacheln laden", sichtbar=False)
        b.update(t, fertig=2, gesamt=4, sichtbar=True)
    typen = [e["typ"] for e in ereignisse]
    assert typen == ["task_neu", "task_update", "balken_ende"]
    assert ereignisse[0]["sichtbar"] is False
    assert ereignisse[1] == {"typ": "task_update", "task": t,
                             "fertig": 2, "gesamt": 4, "sichtbar": True}


def test_eta_erst_ab_schwelle_dann_sticky(monkeypatch):
    zeit = {"t": 0.0}
    monkeypatch.setattr("bmtools.gui.melder.time.monotonic",
                        lambda: zeit["t"])
    m, ereignisse, _ = _melder()
    with m.balken() as b:
        t = b.task("rechnen")
        zeit["t"] = 1.0
        b.update(t, fertig=50, gesamt=100)   # ETA 1 s -> keine Anzeige
        b.update(t, fertig=2, gesamt=100)    # ETA 49 s -> Anzeige
        b.update(t, fertig=95, gesamt=100)   # ETA klein, aber sticky
    updates = [e for e in ereignisse if e["typ"] == "task_update"]
    assert "eta_s" not in updates[0]
    assert updates[1]["eta_s"] == 49
    assert "eta_s" in updates[2]


def test_spur_sendet_fortschritt():
    m, ereignisse, _ = _melder()
    assert list(m.spur(["a", "b"], "laden …")) == ["a", "b"]
    updates = [e for e in ereignisse if e["typ"] == "task_update"]
    assert [(e["fertig"], e["gesamt"]) for e in updates] == [(1, 2), (2, 2)]


def test_status_meldet_anfang_update_ende():
    m, ereignisse, _ = _melder()
    with m.status("Karte erzeugen …") as update:
        update("Abschnitt 2 …")
    assert [e["text"] for e in ereignisse] == [
        "Karte erzeugen …", "Abschnitt 2 …", None]


def test_erfolg_strippt_markup():
    m, ereignisse, _ = _melder()
    m.erfolg(["[green]Fertig.[/green] Ausgaben in [bold]out/[/bold]"])
    assert ereignisse[0]["zeilen"] == ["Fertig. Ausgaben in out/"]


def test_ja_nein_im_fenster_immer_nein():
    m, ereignisse, _ = _melder()
    assert m.ja_nein("Ausgabeordner im Dateimanager öffnen?") is False
    assert ereignisse == []


# ---------------------------------------------------------------------------
# Fragen: blockieren den Pipeline-Thread, Antwort kommt aus der Bridge
# ---------------------------------------------------------------------------

def _frage_im_thread(aufruf):
    ergebnis = {}

    def ziel():
        try:
            ergebnis["wert"] = aufruf()
        except BaseException as e:  # KeyboardInterrupt mitfangen
            ergebnis["fehler"] = e

    t = threading.Thread(target=ziel)
    t.start()
    return t, ergebnis


def test_auswahl_wartet_auf_antwort():
    m, ereignisse, _ = _melder()
    t, ergebnis = _frage_im_thread(lambda: m.auswahl("Welcher?", ["A", "B"]))
    for _ in range(50):
        if ereignisse:
            break
        t.join(0.05)
    frage = ereignisse[0]
    assert frage["typ"] == "frage" and frage["art"] == "auswahl"
    m.antwort(frage["id"], 1)
    t.join(2)
    assert ergebnis["wert"] == 1


def test_frage_ja_dialog_abbruch_wirft():
    m, ereignisse, _ = _melder()
    t, ergebnis = _frage_im_thread(lambda: m.frage_ja("Verwenden?"))
    for _ in range(50):
        if ereignisse:
            break
        t.join(0.05)
    m.antwort(ereignisse[0]["id"], None)  # Dialog abgebrochen
    t.join(2)
    assert isinstance(ergebnis["fehler"], KeyboardInterrupt)


def test_abbruch_loest_wartende_frage():
    m, ereignisse, abbruch = _melder()
    t, ergebnis = _frage_im_thread(lambda: m.auswahl("Welcher?", ["A"]))
    for _ in range(50):
        if ereignisse:
            break
        t.join(0.05)
    abbruch.set()
    t.join(2)
    assert isinstance(ergebnis["fehler"], KeyboardInterrupt)


def test_abbruch_wirft_bei_text():
    m, _, abbruch = _melder()
    abbruch.set()
    with pytest.raises(KeyboardInterrupt):
        m.text("weiter")
