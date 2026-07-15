"""Tests AnyTone-Codeplug-Export (Channel/TalkGroups/Zone-CSV)."""
import csv
from pathlib import Path

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib.codeplug.anytone import (
    CHANNEL_COLUMNS,
    NAME_MAX,
    write_anytone,
)
from tests.conftest import (
    make_device, make_fm_repeater, make_fm_result, make_result)


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


def test_fm_kanal_analog_mit_defaults(tmp_path: Path):
    fm = make_fm_result(make_fm_repeater(
        callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525, ctcss_hz=88.5))
    write_anytone([fm], tmp_path, "Zone", {})
    ch = _read(tmp_path / "Channel.CSV")[0]

    assert ch["Channel Name"] == "DB0FX 70cm"
    assert ch["Channel Type"] == "A-Analog"
    assert ch["Band Width"] == "12.5K"                # Default 12,5 kHz
    assert ch["Receive Frequency"] == "439.12500"     # Relais-Ausgabe
    assert ch["Transmit Frequency"] == "431.52500"
    assert ch["CTCSS/DCS Encode"] == "88.5"
    assert ch["CTCSS/DCS Decode"] == "Off"            # Default: Empfang offen
    assert ch["Contact"] == "" and ch["Contact TG/DMR ID"] == ""
    assert ch["DMR MODE"] == "0"
    assert list(ch.keys()) == CHANNEL_COLUMNS


def test_fm_flags_bandbreite_und_ctcss_decode(tmp_path: Path):
    fm = make_fm_result(make_fm_repeater(ctcss_hz=123.0))
    ohne_ton = make_fm_result(make_fm_repeater(
        callsign="DB0OT", tx_mhz=145.65, rx_mhz=145.05, ctcss_hz=None))
    write_anytone([fm, ohne_ton], tmp_path, "Zone", {},
                  bandbreite="25", ctcss_decode=True)
    chs = _read(tmp_path / "Channel.CSV")

    assert chs[0]["Band Width"] == "25K"
    assert chs[0]["CTCSS/DCS Decode"] == "123"        # Relais-Ton als Decode
    assert chs[1]["CTCSS/DCS Encode"] == "Off"        # kein Ton in den Daten
    assert chs[1]["CTCSS/DCS Decode"] == "Off"        # … auch nicht als Decode


def test_gemischte_zone_und_talkgroups_ohne_fm(tmp_path: Path):
    dmr = make_result(make_device(callsign="DB0XX"),
                      [TalkgroupSub(262, 1, "static")])
    fm = make_fm_result(make_fm_repeater(callsign="DB0FX"))
    write_anytone([dmr, fm], tmp_path, "Zone", {})

    zone = _read(tmp_path / "Zone.CSV")[0]
    assert zone["Zone Channel Member"] == "DB0XX 262|DB0FX 70cm"
    tgs = _read(tmp_path / "TalkGroups.CSV")
    assert [t["Radio ID"] for t in tgs] == ["262"]    # FM erzeugt keine TGs
