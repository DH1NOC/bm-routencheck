"""HTTP-Client für die Brandmeister-API (Halligan, v2).

Nur Lese-Endpunkte, kein API-Key nötig. Antworten werden auf Platte
gecacht (Geräteliste kurz, Profile länger), Profilabfragen werden
gedrosselt, um die API nicht zu belasten.
"""
from __future__ import annotations

import time

import httpx

from .cache import Cache
from .models import Device, DeviceProfile

BASE_URL = "https://api.brandmeister.network/v2"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"

# Der Relais-Bestand ändert sich selten — ein Datenstand von 1–2 Tagen
# reicht (Nutzerentscheidung 2026-07-13). TG-Profile ändern sich am
# ehesten und bleiben bewusst bei 12 h (Nutzerentscheidung ebenfalls
# 2026-07-13); --refresh erzwingt bei Bedarf frische Daten.
DEVICE_LIST_TTL = 24 * 3600       # Geräteliste: 1 Tag
PROFILE_TTL = 12 * 3600           # Talkgroup-Profile: 12 h
TALKGROUP_TTL = 7 * 24 * 3600     # TG-Namensliste: 7 Tage
REQUEST_DELAY = 0.25              # Pause zwischen echten API-Requests


class BrandmeisterClient:
    def __init__(self, refresh: bool = False):
        """refresh=True ignoriert vorhandene Cache-Einträge (schreibt
        aber neue) — für einen erzwungenen Datenrefresh."""
        self._refresh = refresh
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=60,
            headers={"User-Agent": USER_AGENT},
        )
        self._device_cache = Cache(DEVICE_LIST_TTL, "bmtools/devices")
        self._profile_cache = Cache(PROFILE_TTL, "bmtools/profiles")
        self._misc_cache = Cache(TALKGROUP_TTL, "bmtools/misc")

    def _fetch_json(self, path: str, cache: Cache, key: str):
        cached = None if self._refresh else cache.get(key)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(3):
            if attempt:
                time.sleep(2 ** attempt)
            try:
                response = self._http.get(path)
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as e:
                last_error = e
                continue
            cache.set(key, data)
            time.sleep(REQUEST_DELAY)
            return data
        raise RuntimeError(f"Brandmeister-API nicht erreichbar ({path}): {last_error}")

    def devices(self) -> list[Device]:
        """Alle in den letzten 24 h gesehenen Geräte des Netzes."""
        raw = self._fetch_json("/device", self._device_cache, "device-list")
        return [Device.from_api(d) for d in raw]

    def repeaters(self) -> list[Device]:
        return [d for d in self.devices() if d.is_repeater]

    def talkgroup_names(self) -> dict[int, str]:
        """Weltweite TG-Namensliste, z. B. {262: 'Deutschland', ...}."""
        raw = self._fetch_json("/talkgroup", self._misc_cache, "talkgroup-names")
        return {int(k): str(v) for k, v in (raw or {}).items()}

    def profile(self, device_id: int) -> DeviceProfile:
        raw = self._fetch_json(
            f"/device/{device_id}/profile", self._profile_cache, f"profile-{device_id}"
        )
        return DeviceProfile.from_api(device_id, raw or {})
