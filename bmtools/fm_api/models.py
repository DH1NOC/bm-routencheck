"""Datenmodelle für analoge FM-Relais aus der DL3EL-Liste."""
from __future__ import annotations

import zlib
from dataclasses import dataclass


def fm_repeater_id(callsign: str, tx_mhz: float) -> int:
    """Stabile synthetische Kennung, immer negativ.

    DL3EL vergibt keine numerischen IDs; BM-Repeater-IDs sind 6-stellig
    positiv. Negative Hashes kollidieren daher nie mit DMR-IDs, und
    derselbe Kanal bekommt über Läufe hinweg dieselbe Kennung.
    """
    key = f"{callsign}:{tx_mhz:.4f}".encode()
    return -(zlib.crc32(key) or 1)


@dataclass(frozen=True)
class FmRepeater:
    id: int              # synthetisch negativ, s. fm_repeater_id()
    callsign: str
    tx_mhz: float        # Sendefrequenz des Relais (= Empfangsfrequenz des Funkgeräts)
    rx_mhz: float        # Empfangsfrequenz des Relais (= Sendefrequenz des Funkgeräts)
    ctcss_hz: float | None
    lat: float
    lng: float
    city: str            # Info-Spalte der DL3EL-Liste, bereinigt
    locator: str

    @property
    def agl(self) -> float | None:
        """DL3EL liefert keine Antennenhöhe; coverage nimmt dann den Default."""
        return None
