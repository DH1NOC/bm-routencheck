"""Tests Bericht (Konsolentabelle, CSV) — v. a. die RX/TX-Perspektive:
Der Bericht zeigt Frequenzen aus Sicht des Funkgeräts, also vertauscht
gegenüber dem Relais (Relais-TX = Geräte-RX)."""
import csv
from pathlib import Path

from rich.console import Console

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.report import _fmt_subs, print_table, relais_daten, write_csv
from tests.conftest import make_device, make_fm_repeater, make_fm_result, make_result


def test_talkgroup_formatierung():
    subs = [
        TalkgroupSub(262, 1, "static"),
        TalkgroupSub(9, 2, "implicit"),
        TalkgroupSub(26220, 2, "timed", "Mo 18:00–19:30"),
        TalkgroupSub(8, 2, "cluster", "Cluster-TG 26212"),
        TalkgroupSub(9, 2, "cluster", ""),
    ]
    assert _fmt_subs(subs) == ("262, 9(Lokal), 26220⏱(Mo 18:00–19:30), "
                               "8⇄26212, 9(Cluster)")


def test_csv_vertauscht_rx_tx_und_markiert_grenzbereich(tmp_path: Path):
    device = make_device(tx_mhz=439.575, rx_mhz=431.975)
    subs = [TalkgroupSub(262, 1, "static"),
            TalkgroupSub(26220, 2, "timed", "täglich 18:00–19:30"),
            TalkgroupSub(8, 2, "cluster", "Cluster-TG 26212")]
    results = [make_result(device, subs),
               make_result(make_device(id=262002), marginal_only=True)]

    out = tmp_path / "relais.csv"
    write_csv(results, out)
    rows = list(csv.DictReader(out.open(encoding="utf-8"), delimiter=";"))

    assert rows[0]["rx_mhz"] == "439.57500"   # Relais-TX = Geräte-RX
    assert rows[0]["tx_mhz"] == "431.97500"
    assert rows[0]["ts1_statisch"] == "262"
    assert rows[0]["ts2_zeitgeschaltet"] == "26220 (täglich 18:00–19:30)"
    assert rows[0]["cluster"] == "TS2 8->26212"
    assert rows[0]["erreichbarkeit"] == "Sicht"
    assert rows[1]["erreichbarkeit"] == "Grenzbereich"


def test_tabelle_rendert_rufzeichen_und_frequenz():
    console = Console(record=True, width=250)
    print_table([make_result(make_device(), [TalkgroupSub(262, 1, "static")])],
                console)
    text = console.export_text()
    assert "DB0XX" in text
    assert "439.57500" in text
    assert "CTCSS" not in text     # reines DMR: keine FM-Spalten
    assert "Modus" not in text


def test_tabelle_gemischt_zeigt_modus_und_ctcss():
    console = Console(record=True, width=250)
    results = [make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
               make_fm_result(make_fm_repeater(callsign="DB0FX"))]
    print_table(results, console)
    text = console.export_text()
    assert "DMR- und FM-Relais" in text
    assert "Modus" in text and "CTCSS" in text
    assert "DB0FX" in text and "88.5" in text


def test_tabelle_nur_fm_ohne_dmr_spalten():
    console = Console(record=True, width=250)
    print_table([make_fm_result(make_fm_repeater())], console)
    text = console.export_text()
    assert "FM-Relais entlang der Strecke" in text
    assert "CTCSS" in text
    assert "TS1" not in text and "CC" not in text
    assert "zeitgeschaltet" not in text  # DMR-Legende entfällt


def test_csv_fm_zeile_mit_ctcss_und_leeren_tg_spalten(tmp_path: Path):
    results = [make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
               make_fm_result(make_fm_repeater(tx_mhz=145.6375,
                                               rx_mhz=145.0375))]
    out = tmp_path / "relais.csv"
    write_csv(results, out)
    rows = list(csv.DictReader(out.open(encoding="utf-8"), delimiter=";"))

    assert rows[0]["modus"] == "DMR"
    assert rows[0]["ctcss_hz"] == ""
    fm = rows[1]
    assert fm["modus"] == "FM"
    assert fm["rx_mhz"] == "145.63750"     # Relais-Ausgabe = Geräte-RX
    assert fm["tx_mhz"] == "145.03750"
    assert fm["ctcss_hz"] == "88.5"
    assert fm["colorcode"] == "" and fm["ts1_statisch"] == ""
    assert fm["dmr_id"] == ""              # synthetische ID bleibt intern


def test_relais_daten_fuers_datagrid():
    """U5: dieselben Werte wie Tabelle/CSV als JSON-fähige Zeilen;
    RX/TX aus Geräte-Sicht, Status-Wortlaut wie in der CSV."""
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static"),
                                    TalkgroupSub(9, 2, "implicit")]),
        make_fm_result(make_fm_repeater(tx_mhz=145.6375,
                                        rx_mhz=145.0375)),
        make_result(make_device(id=262002, callsign="DB0YY"),
                    [TalkgroupSub(8, 2, "timed", "18-20 Uhr")],
                    marginal_only=True),
    ]

    zeilen = relais_daten(results, {262: "Deutschland"})

    dmr = zeilen[0]
    assert dmr["index"] == 0 and dmr["rufzeichen"] == "DB0XX"
    assert dmr["rx"] == "439.57500" and dmr["tx"] == "431.97500"
    assert dmr["ton"] == "CC1" and dmr["status"] == "Sicht"
    assert dmr["talkgroups"] == [
        {"ts": 1, "tg": 262, "name": "Deutschland", "art": "static",
         "hinweis": ""},
        {"ts": 2, "tg": 9, "name": "Lokal", "art": "implicit",
         "hinweis": ""},
    ]

    fm = zeilen[1]
    assert fm["modus"] == "FM" and fm["talkgroups"] is None
    assert fm["rx"] == "145.63750" and fm["tx"] == "145.03750"
    assert fm["ton"] == "88.5 Hz"

    grenz = zeilen[2]
    assert grenz["status"] == "Grenzbereich"
    assert grenz["talkgroups"] == [
        {"ts": 2, "tg": 8, "name": "", "art": "timed",
         "hinweis": "18-20 Uhr"}]


def test_km_empfangsbereiche_aus_samples():
    from types import SimpleNamespace as S

    from bmtools.routelib.report import km_empfangsbereiche
    samples = [
        S(km=0.0, los=("DB0XX",), marginal=()),
        S(km=5.0, los=("DB0XX",), marginal=("DB0YY",)),
        S(km=12.0, los=(), marginal=("DB0YY",)),
    ]
    assert km_empfangsbereiche(samples) == {
        "DB0XX": (0.0, 5.0), "DB0YY": (5.0, 12.0)}


def test_relais_daten_mit_km_bereich():
    # U8-Befund: Empfangsabschnitt von-bis statt nur nächster km
    results = [make_result(make_device(), [])]
    zeilen = relais_daten(results, km_bereiche={"DB0XX": (2.0, 47.5)})
    assert zeilen[0]["km_von"] == 2.0 and zeilen[0]["km_bis"] == 47.5
    # Ohne Bereich: Fallback auf den nächstgelegenen Strecken-km
    zeilen = relais_daten(results)
    assert zeilen[0]["km_von"] == zeilen[0]["km_bis"] == 10.0
