"""Ausgabeort: Fenster-Start schreibt in einen festen Ordner.

Beta-Befund 2026-07-26 (Mint 22.3): Die Ergebnisse landeten unter
/home/<nutzer>/out/, weil out_dir relativ zum Arbeitsverzeichnis gebildet
wurde — und das bestimmt beim Doppelklick der Starter, nicht das
Programm. Der Nutzer suchte sie in seinem eigenen Programmordner.
"""
from __future__ import annotations

import time
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


def test_basis_faellt_ohne_feld_auf_out_zurueck():
    """Terminal-Namespace kennt ausgabe_basis nicht — dann ./out."""
    import argparse

    assert ausgabe.ausgabe_basis(argparse.Namespace()) == Path("out")
    assert ausgabe.ausgabe_basis(
        argparse.Namespace(ausgabe_basis=None)) == Path("out")
    assert ausgabe.ausgabe_basis(
        argparse.Namespace(ausgabe_basis=Path("/x"))) == Path("/x")


def test_nur_ausgabe_py_kennt_den_out_ordner():
    """»out« darf nur an EINER Stelle im Code stehen.

    Der erste Anlauf setzte den festen Ordner je out_dir-Stelle einzeln
    und übersah dabei rail/cli._pipeline — der Bahn-Modus schrieb weiter
    relativ zum Arbeitsverzeichnis (Befund 2026-07-26, Windows). Ein
    zweiter Ort für dieselbe Entscheidung IST der Fehler.
    """
    treffer = sorted(p for p in Path("bmtools").rglob("*.py")
                     if 'Path("out")' in p.read_text(encoding="utf-8"))
    assert treffer == [Path("bmtools/ausgabe.py")], (
        f"Ausgabeort außerhalb von ausgabe.py festgelegt: {treffer}")


def test_bahn_im_fenster_schreibt_in_den_festen_ordner(monkeypatch, tmp_path):
    """Bahn baut sein out_dir NICHT in der GUI, sondern tief in
    rail/cli._pipeline — genau deshalb fiel der Modus beim ersten Anlauf
    durchs Raster. Hier komplett durchgefahren bis run_pipeline."""
    from bmtools.gui import lauf as lauf_mod
    from bmtools.rail import cli as rail_cli
    from bmtools.routelib.model import Route, Waypoint

    monkeypatch.setattr("platformdirs.user_documents_dir",
                        lambda: str(tmp_path / "Dokumente"))
    # Arbeitsverzeichnis woandershin — eine relative Ablage fiele auf
    (tmp_path / "woanders").mkdir()
    monkeypatch.chdir(tmp_path / "woanders")

    route = Route(points=[(50.0, 8.0), (50.1, 8.1)],
                  stations=[Waypoint("Koblenz Hbf", 50.0, 8.0),
                            Waypoint("Bonn Hbf", 50.1, 8.1)],
                  legs=["RE 99"])
    monkeypatch.setattr(rail_cli, "RoutePlanner", lambda *a, **k: object())
    monkeypatch.setattr(rail_cli, "_resolve_stations",
                        lambda planner, names, m, interactive=False:
                        route.stations)
    monkeypatch.setattr(rail_cli, "_run",
                        lambda stations, args, melder, planner, **kw:
                        rail_cli._pipeline(route, args, melder, **kw))

    gesehen: dict[str, Path] = {}

    def fake_pipeline(route, *, melder, out_dir, **kwargs):
        gesehen["out_dir"] = out_dir
        return 0

    # An rail.cli patchen, nicht am Pipeline-Modul: rail/cli bindet
    # run_pipeline beim Modulimport, ein Patch an der Quelle käme zu spät
    monkeypatch.setattr(rail_cli, "run_pipeline", fake_pipeline)

    ereignisse: list[dict[str, object]] = []
    lauf = lauf_mod.Lauf(ereignisse.append)
    lauf.starten("bahn", {"von": "Koblenz Hbf", "nach": "Bonn Hbf",
                          "via": "", "modus": "dmr"})
    ende = time.monotonic() + 5.0
    while lauf.laeuft() and time.monotonic() < ende:
        time.sleep(0.02)
    assert not lauf.laeuft()

    assert "out_dir" in gesehen, [e for e in ereignisse
                                  if e["typ"] == "fehler"]
    ziel = gesehen["out_dir"]
    assert ziel.is_absolute(), f"Bahn schreibt relativ: {ziel}"
    assert ziel.parent == tmp_path / "Dokumente" / ausgabe.ORDNERNAME
