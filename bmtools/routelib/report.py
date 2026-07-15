"""Konsolentabelle und CSV-Export der Korridor-Treffer."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from bmtools.bm_api.models import Device, DeviceProfile, TalkgroupSub
from bmtools.fm_api.models import FmRepeater

from .corridor import CorridorHit
from .model import RepeaterLike

# Titel-/Textbausteine je Modus (auch von Pipeline und HTML-Bericht genutzt):
# MODUS_LABEL für "…-Relais"-Titel, FUNK_LABEL für "ohne …(-Abdeckung)"
MODUS_LABEL = {"dmr": "DMR", "fm": "FM", "beide": "DMR- und FM"}
FUNK_LABEL = {"dmr": "DMR", "fm": "FM", "beide": "Relais"}


@dataclass
class RepeaterResult:
    hit: CorridorHit
    # None bei FM-Relais: Talkgroup-Profile sind ein reines DMR-Konzept.
    # Ein Typ für beide Modi (statt FmResult-Hierarchie), damit Tabelle,
    # CSV und Karte eine Liste mit gemeinsamer Sortierung verarbeiten.
    profile: DeviceProfile | None = None
    # True: erreicht die Strecke nur im Grenzbereich (Beugung), nie mit
    # freier Sicht — wird überall mitgeführt, damit Karte, Bericht und
    # CSV dieselben Relais zeigen (Konsistenz-Zusage)
    marginal_only: bool = False
    modus: str = "dmr"  # "dmr" | "fm"

    @property
    def device(self) -> RepeaterLike:
        return self.hit.device

    # Typisierte Sichten für modus-spezifische Attribute (colorcode,
    # ctcss_hz, …) — Aufrufer verzweigen vorher über self.modus.
    @property
    def dmr(self) -> Device:
        assert isinstance(self.hit.device, Device)
        return self.hit.device

    @property
    def fm(self) -> FmRepeater:
        assert isinstance(self.hit.device, FmRepeater)
        return self.hit.device

    @property
    def tg_profile(self) -> DeviceProfile:
        assert self.profile is not None  # nur DMR-Results haben Profile
        return self.profile


def _fmt_subs(subs: list[TalkgroupSub]) -> str:
    parts = []
    for s in subs:
        if s.kind == "static":
            parts.append(str(s.talkgroup))
        elif s.kind == "implicit":
            parts.append(f"{s.talkgroup}(Lokal)")
        elif s.kind == "timed":
            parts.append(f"{s.talkgroup}⏱({s.note})" if s.note else f"{s.talkgroup}⏱")
        else:  # cluster
            ext = s.note.removeprefix("Cluster-TG ").strip()
            parts.append(f"{s.talkgroup}⇄{ext}" if ext and ext != "Cluster"
                         else f"{s.talkgroup}(Cluster)")
    return ", ".join(parts)


def _fmt_ctcss(hz: float | None) -> str:
    return f"{hz:g}" if hz else ""


def print_table(results: list[RepeaterResult], console: Console | None = None) -> None:
    console = console or Console()
    has_dmr = any(r.modus == "dmr" for r in results)
    has_fm = any(r.modus == "fm" for r in results)
    mixed = has_dmr and has_fm
    caption_parts = []
    if has_dmr:
        caption_parts += ["⏱ = zeitgeschaltet (Uhrzeiten: Lokalzeit)",
                          "⇄ = Cluster (lokale TG ⇄ Cluster-TG)"]
    if has_fm:
        caption_parts.append("CTCSS = Pilotton (Subaudio), wird dauerhaft "
                             "mitgesendet — viele Relais öffnen nur damit")
    caption_parts.append("gedimmt = nur Grenzbereich (Beugung)")
    modus = "beide" if mixed else ("fm" if has_fm else "dmr")
    table = Table(
        title=f"{MODUS_LABEL[modus]}-Relais entlang der Strecke "
              "(RX/TX aus Sicht deines Funkgeräts)",
        caption=", ".join(caption_parts),
    )
    table.add_column("km", justify="right")
    table.add_column("Rufzeichen")
    table.add_column("Standort", max_width=24)
    table.add_column("Abst.", justify="right")
    if mixed:
        table.add_column("Modus")
    table.add_column("RX [MHz]", justify="right")
    table.add_column("TX [MHz]", justify="right")
    if has_dmr:
        table.add_column("CC", justify="right")
        table.add_column("TS1", max_width=28)
        table.add_column("TS2", max_width=36)
    if has_fm:
        table.add_column("CTCSS", justify="right")
    for r in results:
        d = r.device
        fm = r.modus == "fm"
        row = [
            f"{r.hit.chainage_km:.0f}",
            d.callsign,
            d.city,
            f"{r.hit.distance_km:.1f}",
        ]
        if mixed:
            row.append(MODUS_LABEL[r.modus])
        row += [
            f"{d.tx_mhz:.5f}",   # Relais-TX = dein RX
            f"{d.rx_mhz:.5f}",   # Relais-RX = dein TX
        ]
        if has_dmr:
            row += ["" if fm else str(r.dmr.colorcode or ""),
                    "" if fm else _fmt_subs(r.tg_profile.for_slot(1)),
                    "" if fm else _fmt_subs(r.tg_profile.for_slot(2))]
        if has_fm:
            row.append(_fmt_ctcss(r.fm.ctcss_hz) if fm else "")
        table.add_row(*row, style="dim" if r.marginal_only else None)
    console.print(table)


def _tgs(profile: DeviceProfile, slot: int, kind: str) -> str:
    kinds = ("static", "implicit") if kind == "static" else (kind,)
    items = [s for s in profile.for_slot(slot) if s.kind in kinds]
    if kind == "timed":
        return ", ".join(
            f"{s.talkgroup} ({s.note})" if s.note else str(s.talkgroup)
            for s in items
        )
    return ", ".join(str(s.talkgroup) for s in items)


def write_csv(results: list[RepeaterResult], path: Path) -> None:
    fields = [
        "strecken_km", "rufzeichen", "standort", "abstand_km",
        "erreichbarkeit", "modus",
        "rx_mhz", "tx_mhz", "colorcode", "ctcss_hz",
        "ts1_statisch", "ts1_zeitgeschaltet",
        "ts2_statisch", "ts2_zeitgeschaltet", "cluster",
        "antenne_agl_m", "leistung_w", "dmr_id", "last_seen",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        for r in results:
            d = r.device
            row: dict[str, str | int | float] = {
                "strecken_km": f"{r.hit.chainage_km:.1f}",
                "rufzeichen": d.callsign,
                "standort": d.city,
                "abstand_km": f"{r.hit.distance_km:.1f}",
                "erreichbarkeit": "Grenzbereich" if r.marginal_only else "Sicht",
                "modus": MODUS_LABEL[r.modus],
                "rx_mhz": f"{d.tx_mhz:.5f}",  # aus Gerätesicht
                "tx_mhz": f"{d.rx_mhz:.5f}",
            }
            if r.modus == "fm":
                # TG-/CC-Spalten bleiben leer; die DL3EL-Daten haben weder
                # Antennenhöhe noch Leistung, die synthetische ID bleibt
                # ein Internum
                row["ctcss_hz"] = _fmt_ctcss(r.fm.ctcss_hz)
            else:
                profile = r.tg_profile
                row.update({
                    "colorcode": r.dmr.colorcode or "",
                    "ts1_statisch": _tgs(profile, 1, "static"),
                    "ts1_zeitgeschaltet": _tgs(profile, 1, "timed"),
                    "ts2_statisch": _tgs(profile, 2, "static"),
                    "ts2_zeitgeschaltet": _tgs(profile, 2, "timed"),
                    "cluster": ", ".join(
                        f"TS{s.slot} {s.talkgroup}->"
                        f"{s.note.removeprefix('Cluster-TG ')}"
                        for s in profile.subscriptions if s.kind == "cluster"
                    ),
                    "antenne_agl_m": d.agl or "",
                    "leistung_w": r.dmr.pep or "",
                    "dmr_id": d.id,
                    "last_seen": r.dmr.last_seen,
                })
            w.writerow(row)
