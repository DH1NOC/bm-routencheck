"""Ausgabeort: Fenster-Start schreibt in einen festen Ordner.

Beta-Befund 2026-07-26 (Mint 22.3): Die Ergebnisse landeten unter
/home/<nutzer>/out/, weil out_dir relativ zum Arbeitsverzeichnis gebildet
wurde — und das bestimmt beim Doppelklick der Starter, nicht das
Programm. Der Nutzer suchte sie in seinem eigenen Programmordner.
"""
from __future__ import annotations

from pathlib import Path

from bmtools import ausgabe


def test_fenster_ordner_liegt_unter_dokumenten(monkeypatch, tmp_path):
    monkeypatch.setattr("platformdirs.user_documents_dir",
                        lambda: str(tmp_path / "Dokumente"))
    ziel = ausgabe.fenster_ausgabeordner()
    assert ziel == tmp_path / "Dokumente" / ausgabe.ORDNERNAME
    assert ziel.is_dir()  # wird gleich angelegt


def test_fenster_ordner_haengt_nicht_am_arbeitsverzeichnis(monkeypatch,
                                                           tmp_path):
    """Der Kern des Fehlers: Ein Wechsel des Arbeitsverzeichnisses darf
    das Ergebnis nicht verschieben."""
    monkeypatch.setattr("platformdirs.user_documents_dir",
                        lambda: str(tmp_path / "Dokumente"))
    vorher = ausgabe.fenster_ausgabeordner()
    woanders = tmp_path / "irgendwo"
    woanders.mkdir()
    monkeypatch.chdir(woanders)
    assert ausgabe.fenster_ausgabeordner() == vorher
    assert vorher.is_absolute()


def test_ausweich_ins_home_wenn_dokumente_nicht_gehen(monkeypatch, tmp_path):
    """Kein Dokumente-Ordner anlegbar (gesperrt, Netzlaufwerk weg):
    dann ins Home statt Absturz."""
    gesperrt = tmp_path / "gesperrt"
    gesperrt.write_text("keine Datei-als-Ordner")  # mkdir scheitert daran
    monkeypatch.setattr("platformdirs.user_documents_dir", lambda: str(gesperrt))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "heim"))
    (tmp_path / "heim").mkdir()

    ziel = ausgabe.fenster_ausgabeordner()

    assert ziel == tmp_path / "heim" / ausgabe.ORDNERNAME
    assert ziel.is_dir()


def test_gui_lauf_nutzt_den_festen_ordner(monkeypatch, tmp_path):
    """gui/lauf.py bildet out_dir aus dem festen Ordner, nicht aus »out«."""
    from bmtools.gui import lauf as lauf_mod

    quelle = Path(lauf_mod.__file__).read_text(encoding="utf-8")
    assert "fenster_ausgabeordner() / slug(zone)" in quelle
    assert 'Path("out")' not in quelle, (
        "Fenster-Start darf nicht mehr relativ zum Arbeitsverzeichnis "
        "schreiben")


def test_terminal_bleibt_bei_out():
    """Terminal-Start behält bewusst ./out — dort hat der Nutzer sein
    Arbeitsverzeichnis selbst gewählt."""
    for modul in ("bmtools.rail.cli", "bmtools.road.cli"):
        import importlib
        quelle = Path(importlib.import_module(modul).__file__
                      ).read_text(encoding="utf-8")
        assert 'Path("out")' in quelle, f"{modul} soll bei ./out bleiben"
