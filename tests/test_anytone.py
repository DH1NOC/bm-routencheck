"""Tests AnyTone-Codeplug-Export (Channel/TalkGroups/Zone-CSV)."""
import csv
from pathlib import Path

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.codeplug.anytone import (
    CHANNEL_COLUMNS,
    NAME_MAX,
    write_anytone,
)
from tests.conftest import make_device, make_result


def _read(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(encoding="utf-8")))


def test_kanal_je_talkgroup_und_slot(tmp_path: Path):
    subs = [TalkgroupSub(262, 1, "static"),
            TalkgroupSub(262, 2, "static"),      # gleiche TG, anderer Slot
            TalkgroupSub(262, 2, "static"),      # Duplikat -> verworfen
            TalkgroupSub(26220, 2, "timed", "…")]
    results = [make_result(make_device(callsign="DB0XX"), subs)]

    paths = write_anytone(results, tmp_path, "Testzone", {262: "Deutschland"})
    channels = _read(tmp_path / "Channel.CSV")

    assert [p.name for p in paths] == ["Channel.CSV", "TalkGroups.CSV", "Zone.CSV"]
    assert len(channels) == 3
    # Namenskollision gleiche TG auf beiden Slots -> Slot-Suffix
    assert channels[0]["Channel Name"] == "DB0XX 262"
    assert channels[1]["Channel Name"] == "DB0XX 262 S2"
    assert all(len(c["Channel Name"]) <= NAME_MAX for c in channels)
    # Frequenzen aus Gerätesicht (RX = Relais-Ausgabe)
    assert channels[0]["Receive Frequency"] == "439.57500"
    assert channels[0]["Transmit Frequency"] == "431.97500"
    assert channels[0]["Contact"] == "Deutschland"
    assert channels[2]["Contact"] == "TG26220"  # unbenannt -> Fallback
    assert list(channels[0].keys()) == CHANNEL_COLUMNS


def test_simplex_repeater_slot0_wird_ts1_dmrmode0(tmp_path: Path):
    simplex = make_device(tx_mhz=433.45, rx_mhz=433.45)
    results = [make_result(simplex, [TalkgroupSub(262, 0, "static")])]
    write_anytone(results, tmp_path, "Zone", {})
    ch = _read(tmp_path / "Channel.CSV")[0]
    assert ch["Slot"] == "1"
    assert ch["DMR MODE"] == "0"  # Simplex


def test_talkgroups_und_zone(tmp_path: Path):
    subs = [TalkgroupSub(26220, 2, "static"), TalkgroupSub(262, 1, "static")]
    write_anytone([make_result(make_device(), subs)], tmp_path,
                  "Sehr langer Zonenname weit über dem Limit", {})

    tgs = _read(tmp_path / "TalkGroups.CSV")
    assert [t["Radio ID"] for t in tgs] == ["262", "26220"]  # sortiert

    zone = _read(tmp_path / "Zone.CSV")[0]
    assert len(zone["Zone Name"]) <= NAME_MAX
    # Kanäle in Trefferreihenfolge (Streckenkilometer), TGs sortiert
    assert zone["Zone Channel Member"] == "DB0XX 26220|DB0XX 262"


def test_relais_ohne_frequenz_wird_uebersprungen(tmp_path: Path):
    kaputt = make_device(tx_mhz=None)
    write_anytone([make_result(kaputt, [TalkgroupSub(262, 1, "static")])],
                  tmp_path, "Zone", {})
    assert _read(tmp_path / "Channel.CSV") == []
    assert _read(tmp_path / "Zone.CSV") == []  # keine Zone ohne Kanäle
