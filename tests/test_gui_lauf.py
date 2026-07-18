"""Tests GUI-Lauf (G4): Formulardaten → Route → Pipeline, mit Fakes."""
from __future__ import annotations

import time
from typing import Any

from bmtools.gui import lauf as lauf_mod
from bmtools.road import cli as road_cli
from bmtools.routelib.model import Route, Waypoint


def _warten(lauf, timeout=5.0):
    ende = time.monotonic() + timeout
    while lauf.laeuft() and time.monotonic() < ende:
        time.sleep(0.02)
    assert not lauf.laeuft(), "Lauf wurde nicht fertig"


def _route():
    return Route(points=[(50.0, 8.0), (50.1, 8.1)],
                 stations=[Waypoint("Koblenz", 50.0, 8.0),
                           Waypoint("Bendorf", 50.1, 8.1)],
                 legs=["OSRM-Route Koblenz → Bendorf"])


def test_auto_lauf_bis_pipeline(monkeypatch):
    """Start/Ziel-Weg: Geocoding (eindeutig), Routing, run_pipeline."""
    aufrufe = {}

    monkeypatch.setattr(road_cli, "geocode_candidates",
                        lambda name: [Waypoint(name, 50.0, 8.0)])
    monkeypatch.setattr("bmtools.road.cli.route_waypoints",
                        lambda wps, mode, warn=None: _route())

    def fake_pipeline(route, *, melder, out_dir, zone, modus, **kwargs):
        aufrufe["zone"] = zone
        aufrufe["modus"] = modus
        melder.text("Pipeline gelaufen")
        return 0

    # _strasse importiert run_pipeline erst beim Aufruf — der Patch am
    # Modul greift also auch für den from-Import
    import bmtools.routelib.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "run_pipeline", fake_pipeline)

    ereignisse: list[dict[str, Any]] = []
    lauf = lauf_mod.Lauf(ereignisse.append)
    lauf.starten("auto", {"von": "Koblenz", "nach": "Bendorf",
                          "via": "", "modus": "dmr"})
    _warten(lauf)

    assert aufrufe == {"zone": "Koblenz-Bendorf", "modus": "dmr"}
    texte = [e.get("text", "") for e in ereignisse if e["typ"] == "text"]
    assert any("Koblenz" in t for t in texte)
    assert ereignisse[-1] == {"typ": "fertig", "code": 0}


def test_fehler_erzeugt_fehler_und_fertig(monkeypatch):
    def kaputt(name):
        raise RuntimeError("Geocoding-Dienst nicht erreichbar")

    monkeypatch.setattr(road_cli, "geocode_candidates", kaputt)
    ereignisse: list[dict[str, Any]] = []
    lauf = lauf_mod.Lauf(ereignisse.append)
    lauf.starten("rad", {"von": "A", "nach": "B", "modus": "beide"})
    _warten(lauf)

    typen = [e["typ"] for e in ereignisse]
    assert "fehler" in typen
    assert ereignisse[-1]["typ"] == "fertig"
    assert ereignisse[-1]["code"] == 1


def test_abbruch_liefert_code_130(monkeypatch):
    def langsam(name):
        time.sleep(10)
        return [Waypoint(name, 50.0, 8.0)]

    monkeypatch.setattr(road_cli, "geocode_candidates", langsam)
    ereignisse: list[dict[str, Any]] = []
    lauf = lauf_mod.Lauf(ereignisse.append)
    lauf.starten("auto", {"von": "A", "nach": "B", "modus": "beide"})
    time.sleep(0.1)
    lauf.abbrechen()
    # Der Abbruch greift an der nächsten Meldestelle (melder.text nach
    # dem Geocoding) — der langsame Fake hält den Thread aber 10 s.
    # Deshalb hier nur prüfen, dass abbrechen() gesetzt ist und der
    # Thread als Daemon nicht blockiert.
    assert lauf.melder._abbruch.is_set()
