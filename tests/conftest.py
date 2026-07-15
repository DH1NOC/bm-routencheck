"""Gemeinsame Test-Fabriken (Device/FmRepeater/Profil/Ergebnis)."""
from __future__ import annotations

import pytest

from bmtools.bm_api.models import Device, DeviceProfile, TalkgroupSub
from bmtools.fm_api.models import FmRepeater, fm_repeater_id
from bmtools.routelib.corridor import CorridorHit
from bmtools.routelib.report import RepeaterResult


def make_device(
    id: int = 262001,
    callsign: str = "DB0XX",
    lat: float | None = 50.0,
    lng: float | None = 8.5,
    tx_mhz: float | None = 439.575,
    rx_mhz: float | None = 431.975,
    agl: float | None = 30.0,
    colorcode: int | None = 1,
    city: str = "Teststadt",
) -> Device:
    return Device(
        id=id, callsign_raw=f"{callsign} {city}", tx_mhz=tx_mhz, rx_mhz=rx_mhz,
        colorcode=colorcode, lat=lat, lng=lng, city=city,
        pep=25.0, agl=agl, status=None, last_seen="2026-07-13 12:00:00")


def make_result(
    device: Device,
    subs: list[TalkgroupSub] | None = None,
    distance_km: float = 5.0,
    chainage_km: float = 10.0,
    marginal_only: bool = False,
) -> RepeaterResult:
    profile = DeviceProfile(device_id=device.id, subscriptions=subs or [])
    return RepeaterResult(
        hit=CorridorHit(device, distance_km, chainage_km),
        profile=profile, marginal_only=marginal_only)


def make_fm_repeater(
    callsign: str = "DB0FX",
    tx_mhz: float = 439.125,
    rx_mhz: float = 431.525,
    ctcss_hz: float | None = 88.5,
    lat: float = 50.0,
    lng: float = 8.5,
    city: str = "Teststadt",
    locator: str = "JO40AA",
) -> FmRepeater:
    return FmRepeater(
        id=fm_repeater_id(callsign, tx_mhz), callsign=callsign,
        tx_mhz=tx_mhz, rx_mhz=rx_mhz, ctcss_hz=ctcss_hz,
        lat=lat, lng=lng, city=city, locator=locator)


def make_fm_result(
    repeater: FmRepeater,
    distance_km: float = 5.0,
    chainage_km: float = 10.0,
    marginal_only: bool = False,
) -> RepeaterResult:
    return RepeaterResult(
        hit=CorridorHit(repeater, distance_km, chainage_km),
        profile=None, marginal_only=marginal_only, modus="fm")


@pytest.fixture
def device() -> Device:
    return make_device()
