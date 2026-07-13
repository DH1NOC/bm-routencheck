"""Tests Brandmeister-Datenmodelle (Device- und Profil-Parsing)."""
from bmtools.bm_api.models import Device, DeviceProfile, _timed_note


def _api_device(**over: object) -> dict[str, object]:
    d: dict[str, object] = {
        "id": 262001, "callsign": "DB0XX Teststadt",
        "tx": "439.57500", "rx": "431.97500", "colorcode": 1,
        "lat": "50.1", "lng": "7.5", "city": " Teststadt ",
        "pep": "25", "agl": "30", "status": 3,
        "last_seen": "2026-07-13 12:00:00",
    }
    d.update(over)
    return d


def test_device_parsing_und_rufzeichen():
    d = Device.from_api(_api_device())
    assert d.callsign == "DB0XX"          # ohne Standort-Zusatz
    assert d.tx_mhz == 439.575
    assert (d.lat, d.lng) == (50.1, 7.5)
    assert d.city == "Teststadt"          # getrimmt
    assert d.is_repeater


def test_unbrauchbare_frequenzen_werden_none():
    d = Device.from_api(_api_device(tx="0.00000", rx=None))
    assert d.tx_mhz is None and d.rx_mhz is None
    assert not d.is_repeater


def test_hotspots_und_positionslose_sind_keine_repeater():
    assert not Device.from_api(_api_device(id=2620012)).is_repeater  # 7-stellig
    assert not Device.from_api(_api_device(lat=None)).is_repeater
    assert not Device.from_api(_api_device(lat="0.0", lng="0.0")).is_repeater


def test_profil_statisch_und_cluster():
    p = DeviceProfile.from_api(262001, {
        "staticSubscriptions": [
            {"talkgroup": 262, "slot": 1},
            {"talkgroup": 8, "slot": 2},
        ],
        "clusters": [{"talkgroup": 9, "slot": 2, "extTalkgroup": 26212}],
    })
    assert [(s.talkgroup, s.slot, s.kind) for s in p.subscriptions] == [
        (262, 1, "static"), (8, 2, "static"), (9, 2, "cluster")]
    assert p.subscriptions[-1].note == "Cluster-TG 26212"


def test_profil_buendelt_zeitschaltung_ueber_wochentage():
    # API liefert je Wochentag einen Datensatz -> ein Eintrag "Mo,Fr …"
    eintrag = {"talkgroup": 26220, "slot": 2,
               "data": {"start": 64800, "stop": 70200, "monday": True}}
    freitag = {"talkgroup": 26220, "slot": 2,
               "data": {"start": 64800, "stop": 70200, "friday": True}}
    p = DeviceProfile.from_api(262001, {"timedSubscriptions": [eintrag, freitag]})
    assert len(p.subscriptions) == 1
    assert p.subscriptions[0].note == "Mo,Fr 18:00–19:30"


def test_zeitschaltungs_notation():
    assert _timed_note(set(range(7)), 0, 86400) == "täglich ganztägig"
    assert _timed_note({0}, None, None) == "Mo"
    assert _timed_note({5, 6}, 28800, 61200) == "Sa,So 08:00–17:00"


def test_slot_0_zaehlt_zu_ts1():
    p = DeviceProfile.from_api(262001, {
        "staticSubscriptions": [{"talkgroup": 262, "slot": 0}]})
    assert [s.talkgroup for s in p.for_slot(1)] == [262]
    assert p.for_slot(2) == []
