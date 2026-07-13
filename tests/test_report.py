"""Tests Bericht (Konsolentabelle, CSV) — v. a. die RX/TX-Perspektive:
Der Bericht zeigt Frequenzen aus Sicht des Funkgeräts, also vertauscht
gegenüber dem Relais (Relais-TX = Geräte-RX)."""
import csv
from pathlib import Path

from rich.console import Console

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.report import _fmt_subs, print_table, write_csv
from tests.conftest import make_device, make_result


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
