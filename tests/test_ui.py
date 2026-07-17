"""Tests CLI-Look: Banner, deutsche argparse-Texte, Fortschrittsbalken."""
import argparse
import io

import pytest
from rich.console import Console
from rich.progress import Progress

from bmtools import ui


def _lauf_mit_uhr():
    """Progress mit steuerbarer Uhr: (clock, progress, task_id, task)."""
    clock = [0.0]
    progress = Progress(console=Console(file=io.StringIO()),
                        get_time=lambda: clock[0], auto_refresh=False)
    task_id = progress.add_task("Test", total=100)
    return clock, progress, task_id, progress.tasks[0]


def test_banner_zeigt_titel_und_tastenhinweis():
    console = Console(record=True, width=100)
    ui.banner(console, "Titel", "Untertitel", icon="🚆")
    text = console.export_text()
    assert "Titel" in text and "Untertitel" in text
    assert "Enter bestätigen" in text


def test_eta_bleibt_leer_ohne_schaetzung_und_unter_10s_restzeit():
    spalte = ui.EtaSpalte()
    clock, progress, task_id, task = _lauf_mit_uhr()
    assert spalte.render(task).plain == ""  # noch keine Schätzung
    clock[0] = 1.0
    progress.update(task_id, advance=45)
    clock[0] = 2.0
    progress.update(task_id, advance=45)  # ~45/s → Restzeit ~1 s
    assert task.time_remaining <= ui.ETA_AB_SEKUNDEN
    assert spalte.render(task).plain == ""


def test_eta_erscheint_ab_10s_und_bleibt_bis_zum_ende():
    spalte = ui.EtaSpalte()
    clock, progress, task_id, task = _lauf_mit_uhr()
    clock[0] = 1.0
    progress.update(task_id, advance=2)
    clock[0] = 2.0
    progress.update(task_id, advance=2)  # 2/s → Restzeit ~48 s
    assert task.time_remaining > ui.ETA_AB_SEKUNDEN
    assert spalte.render(task).plain == "noch 00:48"
    # Schätzung fällt unter die Schwelle → Anzeige bleibt (kein Flackern)
    clock[0] = 3.0
    progress.update(task_id, advance=90)
    assert task.time_remaining <= ui.ETA_AB_SEKUNDEN
    assert spalte.render(task).plain.startswith("noch ")
    # Fertig → Anzeige verschwindet
    progress.update(task_id, completed=100)
    assert spalte.render(task).plain == ""


def test_fortschritt_zeigt_beschreibung_x_von_y_und_prozent():
    console = Console(record=True, width=100)
    with ui.fortschritt(console) as progress:
        task_id = progress.add_task("Stützpunkte abfragen", total=8)
        progress.update(task_id, advance=2)
    text = console.export_text()
    assert "Stützpunkte abfragen" in text
    assert "2/8" in text
    assert "25%" in text


def test_argparse_spricht_deutsch(capsys):
    ui.argparse_deutsch()
    ap = argparse.ArgumentParser(prog="bm-test")
    ap.add_argument("--x")
    assert "Aufruf:" in ap.format_help()
    assert "Optionen" in ap.format_help()
    with pytest.raises(SystemExit):
        ap.parse_args(["--unbekannt"])
    assert "unbekannte Argumente" in capsys.readouterr().err
