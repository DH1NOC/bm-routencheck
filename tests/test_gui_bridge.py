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


class _FakeLauf:
    def __init__(self, sende):
        self.gestartet = None
        self._laeuft = False
        self._abgebrochen = False

    def laeuft(self):
        return self._laeuft

    def abgebrochen(self):
        return self._abgebrochen

    def starten(self, tool, daten):
        self.gestartet = (tool, daten)
        self._laeuft = True


def test_start_lauf_gueltig_startet_hintergrundlauf(monkeypatch):
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    r = b.start_lauf("auto", {"von": "Koblenz", "nach": "Bonn"})
    assert r == {"ok": True}
    assert isinstance(b._lauf, _FakeLauf)
    assert b._lauf.gestartet[0] == "auto"


def test_start_lauf_verweigert_zweiten_lauf(monkeypatch):
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    assert b.start_lauf("auto", {"von": "A", "nach": "B"})["ok"] is True
    r = b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert r["ok"] is False and "bereits" in r["hinweis"]


def test_start_lauf_erlaubt_neue_suche_nach_abbruch(monkeypatch):
    # Der abgebrochene Alt-Thread darf noch auslaufen — die Oberfläche
    # ist trotzdem sofort wieder frei (Nutzererwartung 2026-07-19)
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    assert b.start_lauf("auto", {"von": "A", "nach": "B"})["ok"] is True
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf._abgebrochen = True  # laeuft() bleibt True
    assert b.start_lauf("auto", {"von": "A", "nach": "B"})["ok"] is True


def test_waehle_gpx_ohne_fenster_ist_none():
    assert Bridge().waehle_gpx() is None


# ---------------------------------------------------------------------------
# G5: Ausgabeordner öffnen und Cache leeren
# ---------------------------------------------------------------------------

def test_oeffne_ordner_nur_mit_ergebnis(monkeypatch, tmp_path):
    geoeffnet: list[object] = []
    monkeypatch.setattr("bmtools.routelib.oeffnen.system_oeffnen",
                        geoeffnet.append)
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    b.oeffne_ordner()  # kein Lauf -> kein Aufruf
    assert geoeffnet == []

    class _FakeMelder:
        ergebnis_ordner = tmp_path

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    b.oeffne_ordner()
    assert geoeffnet == [tmp_path]


def test_lade_ergebnis_liefert_kartendaten(monkeypatch):
    # U4: strukturierte Daten für die Leaflet-Ansicht statt HTML-srcdoc
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    assert b.lade_ergebnis() is None  # noch kein Lauf

    daten = {"marker": [], "bounds": [[50.0, 8.0], [50.2, 8.2]]}

    class _FakeMelder:
        def __init__(self):
            self.karten_daten = None

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    assert b.lade_ergebnis() is None  # Lauf ohne Kartendaten
    b._lauf.melder.karten_daten = daten
    assert b.lade_ergebnis() == {"karte": daten}


def test_oeffne_ergebnis_beide_im_browser(monkeypatch, tmp_path):
    # Wie --oeffnen im Terminal: Bericht UND Karte (Nutzerwunsch
    # 2026-07-19), Bericht zuerst; fehlende Dateien überspringen
    geoeffnet: list[object] = []
    monkeypatch.setattr("bmtools.routelib.oeffnen.system_oeffnen",
                        geoeffnet.append)
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    b.oeffne_ergebnis()  # kein Lauf -> kein Aufruf
    assert geoeffnet == []

    bericht = tmp_path / "bericht.html"
    bericht.write_text("<p>Bericht</p>")
    karte = tmp_path / "karte.html"
    karte.write_text("<p>Karte</p>")

    class _FakeMelder:
        def __init__(self):
            self.ergebnis_dateien = {"bericht": bericht, "karte": karte,
                                     "fehlt": tmp_path / "fehlt.html"}

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    b.oeffne_ergebnis()
    assert geoeffnet == [bericht, karte]


def test_cache_info_und_leeren(monkeypatch):
    from bmtools import cache_admin

    class _Bereich:
        def __init__(self, groesse, dateien):
            self.groesse_bytes = groesse
            self.dateien = dateien

    monkeypatch.setattr(cache_admin, "bereiche",
                        lambda: [_Bereich(1024, 2), _Bereich(2048, 3)])
    monkeypatch.setattr(cache_admin, "leeren",
                        lambda liste: sum(b.groesse_bytes for b in liste))
    b = Bridge()
    info = b.cache_info()
    assert info["dateien"] == 5 and info["leer"] is False
    assert b.cache_leeren()["frei"] == cache_admin.groesse_mensch(3072)


def test_cache_info_leer(monkeypatch):
    from bmtools import cache_admin
    monkeypatch.setattr(cache_admin, "bereiche", lambda: [])
    assert Bridge().cache_info()["leer"] is True
