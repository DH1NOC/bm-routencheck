"""Tests Melder-Schnittstelle (G2): TerminalMelder-Verhalten und ein
Pipeline-Integrationslauf mit gefakten API-Clients (kein Netz)."""
from __future__ import annotations

import io
from pathlib import Path

import questionary
from rich.console import Console

from bmtools.bm_api.models import DeviceProfile, TalkgroupSub
from bmtools.routelib import pipeline
from bmtools.routelib.melden import TerminalMelder
from bmtools.routelib.model import Route, Waypoint

from .conftest import make_device, make_fm_repeater


class _Antwort:
    def __init__(self, antwort):
        self._antwort = antwort

    def ask(self):
        return self._antwort


def _melder():
    buf = io.StringIO()
    console = Console(file=buf, width=100, force_terminal=False,
                      highlight=False)
    return TerminalMelder(console), buf


# ---------------------------------------------------------------------------
# TerminalMelder
# ---------------------------------------------------------------------------

def test_ja_nein_abbruch_zaehlt_als_nein(monkeypatch):
    monkeypatch.setattr(questionary, "confirm",
                        lambda *a, **k: _Antwort(None))
    m, _ = _melder()
    assert m.ja_nein("Wirklich?") is False


def test_ja_nein_ja(monkeypatch):
    monkeypatch.setattr(questionary, "confirm",
                        lambda *a, **k: _Antwort(True))
    m, _ = _melder()
    assert m.ja_nein("Wirklich?") is True


def test_frage_ja_abbruch_wirft(monkeypatch):
    monkeypatch.setattr(questionary, "confirm",
                        lambda *a, **k: _Antwort(None))
    m, _ = _melder()
    try:
        m.frage_ja("Weiter?")
        raise AssertionError("KeyboardInterrupt erwartet")
    except KeyboardInterrupt:
        pass


def test_auswahl_liefert_index(monkeypatch):
    erhaltene = {}

    def fake_select(frage, choices, **kwargs):
        erhaltene["labels"] = [c.title for c in choices]
        return _Antwort(choices[1].value)

    monkeypatch.setattr(questionary, "select", fake_select)
    m, _ = _melder()
    assert m.auswahl("Welcher?", ["A", "B", "C"]) == 1
    assert erhaltene["labels"] == ["A", "B", "C"]


def test_auswahl_abbruch_wirft(monkeypatch):
    monkeypatch.setattr(questionary, "select",
                        lambda *a, **k: _Antwort(None))
    m, _ = _melder()
    try:
        m.auswahl("Welcher?", ["A", "B"])
        raise AssertionError("KeyboardInterrupt erwartet")
    except KeyboardInterrupt:
        pass


def test_status_liefert_updater():
    m, _ = _melder()
    with m.status("Strecke auflösen …") as update:
        update("Abschnitt 2 …")  # darf nicht werfen


def test_spur_reicht_elemente_durch():
    m, _ = _melder()
    assert list(m.spur([1, 2, 3], "laden …")) == [1, 2, 3]


def test_balken_task_und_update():
    m, buf = _melder()
    with m.balken() as b:
        t = b.task("Kacheln laden", sichtbar=False)
        b.update(t, fertig=3, gesamt=10, sichtbar=True)
        b.update(t, fertig=10)
    assert "Kacheln laden" in buf.getvalue()


def test_erfolg_rendert_panel():
    m, buf = _melder()
    m.erfolg(["[green]Fertig.[/green] Ausgaben in out/", "  bericht.html"])
    out = buf.getvalue()
    assert "Fertig." in out
    assert "bericht.html" in out


# ---------------------------------------------------------------------------
# Pipeline-Integrationslauf (Fake-Clients, Horizontmodell, tmp-Ausgabe)
# ---------------------------------------------------------------------------

class _FakeBM:
    def __init__(self, refresh=False):
        pass

    def repeaters(self):
        return [make_device(id=262001, callsign="DB0AA", lat=50.05, lng=8.20),
                make_device(id=262002, callsign="DB0BB", lat=50.20, lng=8.40)]

    def profile(self, device_id):
        return DeviceProfile(device_id=device_id, subscriptions=[
            TalkgroupSub(262, 1, "static", "Deutschland")])

    def talkgroup_names(self):
        return {262: "Deutschland", 9: "Lokal"}


class _FakeFM:
    def __init__(self, refresh=False):
        pass

    def repeaters_along(self, points, progress=None):
        if progress:
            progress(1, 1)
        return [make_fm_repeater(callsign="DB0FX", lat=50.12, lng=8.25,
                                 tx_mhz=145.700, rx_mhz=145.100)]


def test_pipeline_laeuft_komplett_ueber_den_melder(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "BrandmeisterClient", _FakeBM)
    monkeypatch.setattr(pipeline, "DL3ELClient", _FakeFM)
    route = Route(
        points=[(50.00 + i * 0.01, 8.20 + i * 0.01) for i in range(25)],
        stations=[Waypoint("Startstadt", 50.00, 8.20),
                  Waypoint("Zielstadt", 50.24, 8.44)],
        legs=["RE 99 Startstadt → Zielstadt"])
    m, buf = _melder()

    code = pipeline.run_pipeline(
        route, melder=m, out_dir=tmp_path / "out", corridor_km=None,
        no_terrain=True, open_browser=False, zone="Start-Ziel",
        modus="beide")

    assert code == 0
    out = buf.getvalue()
    assert "Lade Brandmeister-Geräteliste …" in out
    assert "Stützpunkte abfragen" in out
    assert "Erreichbarkeit berechnen (Horizontmodell)" in out
    assert "Talkgroup-Profile laden …" in out
    assert "DB0AA" in out and "DB0FX" in out
    assert "Fertig." in out
    for datei in ("relais.csv", "bericht.html", "karte.html", "chirp.csv"):
        assert (tmp_path / "out" / datei).exists()


def test_pipeline_meldet_den_absoluten_pfad(monkeypatch, tmp_path):
    """»Ausgaben in out/xyz/« half niemandem, der nicht weiß, was sein
    Arbeitsverzeichnis ist (Beta-Befund 2026-07-26): Ein Tester fand
    seine Ergebnisse nicht wieder. Gemeldet wird deshalb absolut — auch
    wenn der Aufrufer relativ übergibt."""
    monkeypatch.setattr(pipeline, "BrandmeisterClient", _FakeBM)
    monkeypatch.setattr(pipeline, "DL3ELClient", _FakeFM)
    monkeypatch.chdir(tmp_path)
    route = Route(
        points=[(50.00 + i * 0.01, 8.20 + i * 0.01) for i in range(25)],
        stations=[Waypoint("Startstadt", 50.00, 8.20),
                  Waypoint("Zielstadt", 50.24, 8.44)],
        legs=["RE 99 Startstadt → Zielstadt"])
    m, _ = _melder()
    # Direkt den gemeldeten Pfad prüfen statt den gerenderten Text: rich
    # bricht lange Pfade im Panel um, die Textsuche wäre unzuverlässig.
    # Genau dieser Pfad landet auch am Ordner-Knopf der Oberfläche.
    gemeldet: list[Path] = []
    original = m.ergebnis

    def spion(out_dir: Path, bericht: Path, karte: Path) -> None:
        gemeldet.append(out_dir)
        original(out_dir, bericht, karte)

    m.ergebnis = spion

    code = pipeline.run_pipeline(
        route, melder=m, out_dir=Path("out") / "strecke", corridor_km=None,
        no_terrain=True, open_browser=False, zone="Start-Ziel",
        modus="beide")

    assert code == 0
    assert gemeldet == [(tmp_path / "out" / "strecke").resolve()]
    assert gemeldet[0].is_absolute()


def test_pipeline_pdf_flag_erzeugt_bericht_pdf(monkeypatch, tmp_path):
    """U8: pdf=True schreibt bericht.pdf zusätzlich (Kartenbild
    gestubbt — kein Netz) und nennt es im Erfolgs-Panel."""
    from PIL import Image

    from bmtools.routelib import report_pdf

    monkeypatch.setattr(pipeline, "BrandmeisterClient", _FakeBM)
    monkeypatch.setattr(pipeline, "DL3ELClient", _FakeFM)
    monkeypatch.setattr(report_pdf, "render_kartenbild",
                        lambda karte, **kw: Image.new("RGB", (200, 150),
                                                      "#dddddd"))
    route = Route(
        points=[(50.00 + i * 0.01, 8.20 + i * 0.01) for i in range(25)],
        stations=[Waypoint("Startstadt", 50.00, 8.20),
                  Waypoint("Zielstadt", 50.24, 8.44)],
        legs=["RE 99 Startstadt → Zielstadt"])
    m, buf = _melder()

    code = pipeline.run_pipeline(
        route, melder=m, out_dir=tmp_path / "out", corridor_km=None,
        no_terrain=True, open_browser=False, zone="Start-Ziel",
        modus="beide", pdf=True)

    assert code == 0
    assert "Erzeuge PDF-Bericht" in buf.getvalue()
    assert "bericht.pdf" in buf.getvalue()
    pdf = tmp_path / "out" / "bericht.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
