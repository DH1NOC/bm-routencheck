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
    monkeypatch.setattr("bmtools.routelib.oeffnen.system_oeffnen_still",
                        lambda z: geoeffnet.append(z))
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    assert b.oeffne_ordner() == {"ok": False, "pfad": "",
                                 "fehler": "Kein Ergebnis"}
    assert geoeffnet == []

    class _FakeMelder:
        ergebnis_ordner = tmp_path

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    assert b.oeffne_ordner() == {"ok": True, "pfad": str(tmp_path),
                                 "fehler": None}
    assert geoeffnet == [tmp_path]


def test_oeffne_ordner_meldet_fehlschlag_mit_pfad(monkeypatch, tmp_path):
    """Scheitert der Dateimanager, muss die Oberfläche etwas anzeigen
    können — bis 2026-07-26 passierte gar nichts (Mint 22.3). Der Pfad
    geht in jedem Fall zurück, damit der Nutzer trotzdem hinfindet."""
    from bmtools.routelib.oeffnen import OeffnenFehler
    monkeypatch.setattr(
        "bmtools.routelib.oeffnen.system_oeffnen_still",
        lambda z: OeffnenFehler(z, ["xdg-open: Code 4", "nemo: Code 1"]))
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()

    class _FakeMelder:
        ergebnis_ordner = tmp_path

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert b._lauf is not None
    b._lauf.melder = _FakeMelder()  # type: ignore[assignment]
    r = b.oeffne_ordner()

    assert r["ok"] is False
    assert r["pfad"] == str(tmp_path)
    assert "xdg-open: Code 4" in r["fehler"]


def test_lade_ergebnis_liefert_strukturierte_daten(monkeypatch):
    # U4/U5: Karte + Kennzahlen + Relais statt HTML-srcdoc
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    assert b.lade_ergebnis() is None  # noch kein Lauf

    daten = {"karte": {"marker": []},
             "kennzahlen": {"distanz_km": 12},
             "relais": [{"rufzeichen": "DB0XX"}]}

    class _FakeMelder:
        def __init__(self):
            self.lauf_daten = None

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    assert b.lade_ergebnis() is None  # Lauf ohne Ergebnisdaten
    b._lauf.melder.lauf_daten = daten
    assert b.lade_ergebnis() == daten


def test_einstellungen_roundtrip(monkeypatch, tmp_path):
    # U5: Splitter-Position (U6: Theme) landet in gui.json statt
    # localStorage (WKWebView-file://-Persistenz unzuverlässig)
    monkeypatch.setattr("bmtools.gui.einstellungen.user_config_dir",
                        lambda name: str(tmp_path))
    b = Bridge()
    assert b.init_zustand()["einstellungen"] == {}
    b.setze_einstellung("splitter", 0.62)
    assert b.init_zustand()["einstellungen"] == {"splitter": 0.62}
    assert (tmp_path / "gui.json").is_file()


def test_export_csv_kopiert_ueber_speichern_dialog(monkeypatch, tmp_path):
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    b = Bridge()
    assert b.export_csv() is None  # kein Lauf

    quelle_dir = tmp_path / "out"
    quelle_dir.mkdir()
    (quelle_dir / "relais.csv").write_text("a;b\n1;2\n")
    ziel = tmp_path / "export.csv"

    class _FakeMelder:
        def __init__(self):
            self.ergebnis_ordner = quelle_dir

    class _FakeFenster:
        def create_file_dialog(self, art, save_filename=""):
            assert save_filename == "relais.csv"
            return str(ziel)

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    b._fenster = _FakeFenster()
    assert b.export_csv() == {"pfad": str(ziel)}
    assert ziel.read_text() == "a;b\n1;2\n"


def test_oeffne_ergebnis_beide_im_browser(monkeypatch, tmp_path):
    # Wie --oeffnen im Terminal: Bericht UND Karte (Nutzerwunsch
    # 2026-07-19), Bericht zuerst; fehlende Dateien überspringen
    geoeffnet: list[object] = []
    monkeypatch.setattr("bmtools.routelib.oeffnen.system_oeffnen_still",
                        lambda z: geoeffnet.append(z))
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
            self.ergebnis_ordner = tmp_path
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


def test_export_pdf_schreibt_und_oeffnet(monkeypatch, tmp_path):
    # U8: PDF aus den gespeicherten Ergebnisdaten, Ablage im
    # Ausgabeordner, danach öffnen (Spezifikation §4)
    monkeypatch.setattr("bmtools.gui.bridge.Lauf", _FakeLauf)
    geschrieben: list[tuple[object, object]] = []
    geoeffnet: list[object] = []
    monkeypatch.setattr("bmtools.routelib.report_pdf.write_pdf",
                        lambda daten, pfad, **kw:
                        geschrieben.append((daten, pfad)))
    monkeypatch.setattr("bmtools.routelib.oeffnen.system_oeffnen_still",
                        lambda z: geoeffnet.append(z))
    b = Bridge()
    assert b.export_pdf() is None  # kein Lauf

    daten: dict[str, object] = {"karte": {}, "kennzahlen": {},
                                "relais": []}

    class _FakeMelder:
        def __init__(self):
            self.lauf_daten = None
            self.ergebnis_ordner = tmp_path

    b.start_lauf("auto", {"von": "A", "nach": "B"})
    assert isinstance(b._lauf, _FakeLauf)
    b._lauf.melder = _FakeMelder()
    assert b.export_pdf() is None  # noch keine Ergebnisdaten
    b._lauf.melder.lauf_daten = daten
    r = b.export_pdf()
    assert r == {"pfad": str(tmp_path / "bericht.pdf")}
    assert geschrieben == [(daten, tmp_path / "bericht.pdf")]
    assert geoeffnet == [tmp_path / "bericht.pdf"]


# ---------------------------------------------------------------------------
# changelog_nach_update
# ---------------------------------------------------------------------------

def _changelog_umgebung(monkeypatch, tmp_path, *, version="0.4.3",
                        bekannt=True, notes=()):
    """Bridge mit isolierter gui.json, fester Version und gefakter
    Notes-Abfrage; zählt die Netz-Aufrufe mit."""
    aufrufe: list[tuple[str, str]] = []
    monkeypatch.setattr("bmtools.gui.einstellungen.user_config_dir",
                        lambda name: str(tmp_path))
    monkeypatch.setattr("bmtools.version.eigene_version", lambda: version)
    monkeypatch.setattr("bmtools.version.version_bekannt", lambda: bekannt)

    from bmtools.update.changelog import ReleaseNotes

    def fake_notes(von, bis, **kwargs):
        aufrufe.append((von, bis))
        return [ReleaseNotes(v, t) for v, t in notes]

    monkeypatch.setattr("bmtools.update.changelog.notes_zwischen",
                        fake_notes)
    return Bridge(), aufrufe


def test_changelog_erster_start_setzt_nur_den_marker(monkeypatch, tmp_path):
    from bmtools.gui import einstellungen
    b, aufrufe = _changelog_umgebung(monkeypatch, tmp_path)
    assert b.changelog_nach_update() is None
    assert einstellungen.laden()["changelog_stand"] == "0.4.3"
    assert aufrufe == []  # frische Installation: keine Netzabfrage


def test_changelog_nach_update_liefert_notes(monkeypatch, tmp_path):
    from bmtools.gui import einstellungen
    b, aufrufe = _changelog_umgebung(
        monkeypatch, tmp_path,
        notes=[("0.4.3", "Neues"), ("0.4.2", "Älteres")])
    einstellungen.setzen("changelog_stand", "0.4.1")
    assert b.changelog_nach_update() == [
        {"version": "0.4.3", "notes": "Neues"},
        {"version": "0.4.2", "notes": "Älteres"}]
    assert aufrufe == [("0.4.1", "0.4.3")]
    # Marker fortgeschrieben: der nächste Start fragt nicht mehr
    assert einstellungen.laden()["changelog_stand"] == "0.4.3"
    assert b.changelog_nach_update() is None
    assert aufrufe == [("0.4.1", "0.4.3")]


def test_changelog_verfaellt_wenn_abfrage_leer_bleibt(monkeypatch, tmp_path):
    # Ein Versuch pro Update (Nutzerentscheidung 2026-07-30): auch bei
    # leerer Antwort (offline) ist der Marker danach fortgeschrieben
    from bmtools.gui import einstellungen
    b, aufrufe = _changelog_umgebung(monkeypatch, tmp_path)
    einstellungen.setzen("changelog_stand", "0.4.1")
    assert b.changelog_nach_update() is None
    assert len(aufrufe) == 1
    assert einstellungen.laden()["changelog_stand"] == "0.4.3"


def test_changelog_downgrade_zeigt_nichts(monkeypatch, tmp_path):
    from bmtools.gui import einstellungen
    b, aufrufe = _changelog_umgebung(monkeypatch, tmp_path,
                                     notes=[("0.4.3", "x")])
    einstellungen.setzen("changelog_stand", "0.5.0")
    assert b.changelog_nach_update() is None
    assert aufrufe == []
    assert einstellungen.laden()["changelog_stand"] == "0.4.3"


def test_changelog_ohne_bekannte_version_stumm(monkeypatch, tmp_path):
    from bmtools.gui import einstellungen
    b, aufrufe = _changelog_umgebung(monkeypatch, tmp_path, bekannt=False)
    assert b.changelog_nach_update() is None
    assert aufrufe == []
    assert "changelog_stand" not in einstellungen.laden()
