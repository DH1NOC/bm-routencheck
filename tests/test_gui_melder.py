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
        zeit["t"] = 2.0
        b.update(t, fertig=2, gesamt=100)    # ETA 98 s -> Anzeige
        zeit["t"] = 3.0
        b.update(t, fertig=95, gesamt=100)   # ETA klein, aber sticky
    updates = [e for e in ereignisse if e["typ"] == "task_update"]
    assert "eta_s" not in updates[0]
    assert updates[1]["eta_s"] == 98
    assert "eta_s" in updates[2]


def test_updates_werden_gedrosselt(monkeypatch):
    # Sample-Callbacks feuern hunderte Male pro Sekunde — gesendet wird
    # höchstens alle SENDETAKT_S, sonst flutet evaluate_js den UI-Thread
    # (Befund 2026-07-19: UI gesperrt, Tabwechsel nur per Doppelklick)
    zeit = {"t": 100.0}
    monkeypatch.setattr("bmtools.gui.melder.time.monotonic",
                        lambda: zeit["t"])
    m, ereignisse, _ = _melder()
    with m.balken() as b:
        t = b.task("Erreichbarkeit berechnen")
        for i in range(1, 51):               # 50 Callbacks, Zeit steht
            b.update(t, fertig=i, gesamt=100)
        zeit["t"] = 100.2                    # Takt abgelaufen
        b.update(t, fertig=60, gesamt=100)
        b.update(t, fertig=61, gesamt=100)   # wieder gedrosselt
        b.update(t, fertig=100, gesamt=100)  # final: geht immer durch
        b.update(t, sichtbar=False)          # strukturell: geht immer
    updates = [e for e in ereignisse if e["typ"] == "task_update"]
    assert [u.get("fertig") for u in updates] == [1, 60, 100, None]


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


def test_ergebnis_merkt_dateien_und_meldet_ereignis(tmp_path):
    m, ereignisse, _ = _melder()
    bericht = tmp_path / "bericht.html"
    karte = tmp_path / "karte.html"
    m.ergebnis(tmp_path, bericht, karte)
    assert m.ergebnis_ordner == tmp_path
    assert m.ergebnis_dateien == {"bericht": bericht, "karte": karte}
    assert ereignisse[0] == {"typ": "ergebnis", "ordner": str(tmp_path)}


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


def test_abbruch_wirft_bei_task_update_im_lauf_thread():
    # G4-Abnahmebefund 2026-07-19: Während der FM-Stützpunkte (2/21)
    # kommen minutenlang nur task-Updates — Abbrechen muss dort greifen.
    m, _, abbruch = _melder()
    m.markiere_lauf_thread()  # dieser Testthread spielt den Lauf-Thread
    with m.balken() as b:
        t = b.task("Stützpunkte abfragen")
        b.update(t, fertig=2, gesamt=21)
        abbruch.set()
        with pytest.raises(KeyboardInterrupt):
            b.update(t, fertig=3, gesamt=21)


def test_abbruch_wirft_nicht_aus_helfer_threads():
    # Kachel-Downloads melden aus eigenen Threads — die dürfen bei
    # Abbruch nicht sterben, sonst hinge estimate_coverage.
    m, ereignisse, abbruch = _melder()
    m.markiere_lauf_thread()
    fehler: list[BaseException] = []
    with m.balken() as b:
        t = b.task("Höhenkacheln laden")
        abbruch.set()

        def helfer():
            try:
                b.update(t, fertig=1, gesamt=4)
            except BaseException as e:
                fehler.append(e)

        th = threading.Thread(target=helfer)
        th.start()
        th.join(2)
    assert fehler == []
    # … aber ihre Ereignisse werden verschluckt: die Oberfläche hat
    # nach dem Abbrechen-Klick schon »fertig« gemeldet
    assert [e["typ"] for e in ereignisse] == ["task_neu"]
