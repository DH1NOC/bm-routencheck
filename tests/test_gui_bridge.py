"""Tests JS-Bridge (G3): Startzustand, Feld- und Formular-Validierung."""
from __future__ import annotations

from bmtools.gui.bridge import FORMULAR, Bridge, pruefe_formular

VBID_LINK = ("https://www.bahn.de/buchung/start?vbid="
             "12345678-1234-1234-1234-123456789abc")


# ---------------------------------------------------------------------------
# init_zustand
# ---------------------------------------------------------------------------

def test_init_zustand_default_tab_bahn():
    assert Bridge().init_zustand()["tab"] == "bahn"


def test_init_zustand_vorauswahl():
    assert Bridge("rad").init_zustand()["tab"] == "rad"


# ---------------------------------------------------------------------------
# pruefe_formular: Bahn
# ---------------------------------------------------------------------------

def test_bahn_ohne_alles_verlangt_link_oder_strecke():
    fehler = pruefe_formular("bahn", {})
    assert FORMULAR in fehler


def test_bahn_mit_start_und_ziel_ok():
    assert pruefe_formular("bahn", {"von": "Koblenz Hbf",
                                    "nach": "Nürnberg Hbf"}) == {}


def test_bahn_mit_vbid_link_ok():
    assert pruefe_formular("bahn", {"link": VBID_LINK}) == {}


def test_bahn_link_ohne_vbid_wird_beanstandet():
    fehler = pruefe_formular("bahn", {"link": "https://www.bahn.de/"})
    assert "vbid" in fehler["bahn-link"]


def test_bahn_kaputte_zeit_wird_beanstandet():
    fehler = pruefe_formular("bahn", {"von": "A", "nach": "B",
                                      "zeit": "morgen früh"})
    assert "bahn-zeit" in fehler


def test_bahn_gueltige_zeiten():
    for zeit in ("2026-07-19 08:00", "19.07.2026 08:00", "08:00"):
        assert pruefe_formular("bahn", {"von": "A", "nach": "B",
                                        "zeit": zeit}) == {}


# ---------------------------------------------------------------------------
# pruefe_formular: Auto/Rad
# ---------------------------------------------------------------------------

def test_auto_ohne_alles_verlangt_eingabe():
    assert FORMULAR in pruefe_formular("auto", {})


def test_auto_mit_link_ok():
    assert pruefe_formular("auto", {"link": "https://maps.app.goo.gl/x"}) == {}


def test_rad_link_ohne_protokoll_wird_beanstandet():
    fehler = pruefe_formular("rad", {"link": "www.komoot.com/tour/1"})
    assert "rad-link" in fehler


def test_rad_gpx_datei_muss_existieren(tmp_path):
    fehlt = pruefe_formular("rad", {"gpx": str(tmp_path / "fehlt.gpx")})
    assert "rad-gpx" in fehlt
    gpx = tmp_path / "tour.gpx"
    gpx.write_text("<gpx/>")
    assert pruefe_formular("rad", {"gpx": str(gpx)}) == {}


def test_unbekanntes_tool():
    assert FORMULAR in pruefe_formular("boot", {})


# ---------------------------------------------------------------------------
# Bridge-Methoden
# ---------------------------------------------------------------------------

def test_pruefe_feld_zeit():
    b = Bridge()
    assert b.pruefe_feld("bahn", "zeit", "08:00")["ok"] is True
    r = b.pruefe_feld("bahn", "zeit", "irgendwann")
    assert r["ok"] is False and "Format" in r["fehler"]


def test_pruefe_feld_leer_ist_ok():
    # Leere optionale Felder erzeugen kein Fehler-Feedback
    assert Bridge().pruefe_feld("bahn", "link", "  ")["ok"] is True


def test_start_lauf_meldet_formularfehler():
    r = Bridge().start_lauf("bahn", {})
    assert r["ok"] is False and FORMULAR in r["fehler"]


def test_start_lauf_gueltig_meldet_g4_hinweis():
    r = Bridge().start_lauf("auto", {"von": "Koblenz", "nach": "Bonn"})
    assert r["ok"] is False and "G4" in r["hinweis"]


def test_waehle_gpx_ohne_fenster_ist_none():
    assert Bridge().waehle_gpx() is None
