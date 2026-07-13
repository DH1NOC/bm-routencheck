"""Datenmodelle für Brandmeister-API-Objekte."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _to_mhz(value: Any) -> float | None:
    """Frequenzfeld der API ("438.2000") → MHz; 0/leer = unbekannt."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _to_coord(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Device:
    id: int
    callsign_raw: str
    tx_mhz: float | None  # Sendefrequenz des Relais (= Empfangsfrequenz des Funkgeräts)
    rx_mhz: float | None  # Empfangsfrequenz des Relais (= Sendefrequenz des Funkgeräts)
    colorcode: int | None
    lat: float | None
    lng: float | None
    city: str
    pep: float | None
    agl: float | None
    status: int | None
    last_seen: str

    @classmethod
    def from_api(cls, d: dict[str, Any]) -> Device:
        return cls(
            id=int(d["id"]),
            callsign_raw=(d.get("callsign") or "").strip(),
            tx_mhz=_to_mhz(d.get("tx")),
            rx_mhz=_to_mhz(d.get("rx")),
            colorcode=d.get("colorcode"),
            lat=_to_coord(d.get("lat")),
            lng=_to_coord(d.get("lng")),
            city=(d.get("city") or "").strip(),
            pep=_to_mhz(d.get("pep")),
            agl=_to_mhz(d.get("agl")),
            status=d.get("status"),
            last_seen=d.get("last_seen") or "",
        )

    @property
    def callsign(self) -> str:
        """Reines Rufzeichen (erste Token, ohne Standort-Zusatz)."""
        return self.callsign_raw.split()[0] if self.callsign_raw else ""

    @property
    def is_repeater(self) -> bool:
        """Repeater haben 6-stellige DMR-IDs; Hotspots 7+ Stellen.

        Zusätzlich: Position und beide Frequenzen müssen vorhanden sein,
        sonst ist der Eintrag für die Streckensuche unbrauchbar.
        """
        return (
            100000 <= self.id <= 999999
            and self.lat is not None
            and self.lng is not None
            and abs(self.lat) > 0.001
            and abs(self.lng) > 0.001
            and self.tx_mhz is not None
            and self.rx_mhz is not None
        )


_WEEKDAYS = [
    ("monday", "Mo"), ("tuesday", "Di"), ("wednesday", "Mi"),
    ("thursday", "Do"), ("friday", "Fr"), ("saturday", "Sa"), ("sunday", "So"),
]


def _hhmm(sec: Any) -> str:
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return "?"
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"


def _timed_note(day_indices: set[int], start: Any, stop: Any) -> str:
    """Zeitschaltung menschenlesbar: 'Mo,Fr 18:00–19:30'."""
    if not day_indices or len(day_indices) >= 7:
        day_str = "täglich"
    else:
        day_str = ",".join(
            de for i, (_, de) in enumerate(_WEEKDAYS) if i in day_indices)
    if start is None or stop is None:
        return day_str
    if (start, stop) == (0, 86400):
        return f"{day_str} ganztägig"
    return f"{day_str} {_hhmm(start)}–{_hhmm(stop)}"


@dataclass(frozen=True)
class TalkgroupSub:
    talkgroup: int
    slot: int
    kind: str  # "static" | "timed" | "cluster"
    note: str = ""  # z. B. Zeitfenster oder aufgelöste Cluster-TG


@dataclass
class DeviceProfile:
    device_id: int
    subscriptions: list[TalkgroupSub] = field(default_factory=list)

    @classmethod
    def from_api(cls, device_id: int, p: dict[str, Any]) -> DeviceProfile:
        subs: list[TalkgroupSub] = []
        for s in p.get("staticSubscriptions") or []:
            subs.append(TalkgroupSub(int(s["talkgroup"]), int(s["slot"]), "static"))
        # Die API liefert je Wochentag einen eigenen Datensatz; gleiche
        # Zeitfenster derselben TG werden hier zu einem Eintrag gebündelt.
        timed: dict[tuple[int, int, Any, Any], set[int]] = {}
        for s in p.get("timedSubscriptions") or []:
            data = s.get("data") if isinstance(s.get("data"), dict) else {}
            key = (int(s["talkgroup"]), int(s["slot"]),
                   data.get("start"), data.get("stop"))
            timed.setdefault(key, set()).update(
                i for i, (en, _) in enumerate(_WEEKDAYS) if data.get(en)
            )
        for (tg, slot, start, stop), days in timed.items():
            subs.append(TalkgroupSub(tg, slot, "timed", _timed_note(days, start, stop)))
        for c in p.get("clusters") or []:
            ext = c.get("extTalkgroup")
            note = f"Cluster-TG {ext}" if ext else "Cluster"
            subs.append(TalkgroupSub(
                int(c["talkgroup"]), int(c["slot"]), "cluster", note))
        subs.sort(key=lambda s: (s.slot, s.talkgroup))
        return cls(device_id=device_id, subscriptions=subs)

    def for_slot(self, slot: int) -> list[TalkgroupSub]:
        """Slot 0 (Simplex-Repeater ohne TDMA-Slots) wird TS1 zugeordnet."""
        return [s for s in self.subscriptions
                if s.slot == slot or (slot == 1 and s.slot == 0)]
