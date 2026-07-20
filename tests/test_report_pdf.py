"""Tests PDF-Bericht (U8): Aufbau, Seitenumbrüche, Karten-Fallback —
Kartenbild gestubbt (kein Netz)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from bmtools.routelib import report_pdf
from bmtools.routelib.mapimage import KartenbildFehler
from bmtools.routelib.report_pdf import _tg_text, write_pdf


def _payload(anzahl: int = 3) -> dict[str, Any]:
    relais = []
    for i in range(anzahl):
        fm = i % 3 == 2
        relais.append({
            "index": i, "km": i * 3.5, "rufzeichen": f"DB0X{i:02d}",
            "standort": "Teststadt", "abstand_km": 5.0,
            "modus": "FM" if fm else "DMR",
            "rx": "439.57500", "tx": "431.97500",
            "ton": "88.5 Hz" if fm else "CC1",
            "status": "Grenzbereich" if i % 4 == 3 else "Sicht",
            "talkgroups": None if fm else [
                {"ts": 1, "tg": 262, "name": "Deutschland",
                 "art": "static", "hinweis": ""},
                {"ts": 2, "tg": 9, "name": "Lokal",
                 "art": "implicit", "hinweis": ""}],
        })
    return {
        "karte": {
            "bounds": [[50.0, 8.0], [50.2, 8.2]],
            "route_label": "Bahnstrecke",
            "stationen": [{"name": "Start", "lat": 50.0, "lon": 8.0},
                          {"name": "Ziel", "lat": 50.2, "lon": 8.2}],
            "legende": {"modus_label": "DMR+FM",
                        "marker_note": "blau = DMR, orange = FM"},
        },
        "kennzahlen": {"distanz_km": 96, "terrain": True,
                       "sicht_pct": 78, "grenz_pct": 12,
                       "schatten_pct": 10, "anzahl": anzahl,
                       "stand": "20.07.2026"},
        "relais": relais,
    }


def _stub_karte(monkeypatch):
    monkeypatch.setattr(report_pdf, "render_kartenbild",
                        lambda karte, **kw: Image.new("RGB", (400, 300),
                                                      "#dddddd"))


def _seiten(pfad: Path) -> int:
    return pfad.read_bytes().count(b"/Type /Page\n")


def test_pdf_mit_deckblatt_und_tabelle(monkeypatch, tmp_path):
    _stub_karte(monkeypatch)
    pfad = tmp_path / "bericht.pdf"
    write_pdf(_payload(), pfad)
    inhalt = pfad.read_bytes()
    assert inhalt.startswith(b"%PDF")
    assert _seiten(pfad) == 2  # Deckblatt + eine Tabellenseite


def test_lange_tabelle_bricht_sauber_um(monkeypatch, tmp_path):
    _stub_karte(monkeypatch)
    pfad = tmp_path / "bericht.pdf"
    write_pdf(_payload(80), pfad)
    assert _seiten(pfad) >= 3  # Abnahme-Kriterium: Seitenumbrüche


def test_pdf_ohne_kacheln_mit_hinweis(monkeypatch, tmp_path):
    def kaputt(karte, **kw):
        raise KartenbildFehler("Kartenkachel 13/1/2 nicht ladbar")
    monkeypatch.setattr(report_pdf, "render_kartenbild", kaputt)
    pfad = tmp_path / "bericht.pdf"
    write_pdf(_payload(), pfad)  # darf nicht scheitern (offline)
    assert pfad.read_bytes().startswith(b"%PDF")


def test_tg_text_je_timeslot():
    text = _tg_text([
        {"ts": 2, "tg": 9, "name": "Lokal", "art": "implicit",
         "hinweis": ""},
        {"ts": 1, "tg": 262, "name": "Deutschland", "art": "static",
         "hinweis": ""},
        {"ts": 2, "tg": 8, "name": "", "art": "timed",
         "hinweis": "18-20 Uhr"},
        {"ts": 2, "tg": 26231, "name": "", "art": "cluster",
         "hinweis": "Cluster-TG 26230"},
    ])
    assert text == ("TS1: 262 Deutschland — "
                    "TS2: 9 Lokal, 8 (zeitgeschaltet 18-20 Uhr), "
                    "26231 (Cluster-TG 26230)")


def test_km_bereich_formatierung():
    from bmtools.routelib.report_pdf import _km_bereich
    assert _km_bereich({"km": 8.0, "km_von": 2.0, "km_bis": 47.5}) \
        == "2–48"
    assert _km_bereich({"km": 8.0, "km_von": 8.2, "km_bis": 8.4}) == "8"
    assert _km_bereich({"km": 8.0}) == "8"  # altes Payload: Fallback
