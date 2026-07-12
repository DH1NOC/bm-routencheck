"""Konsolentabelle und CSV-Export der Korridor-Treffer."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from bmtools.bm_api.models import DeviceProfile, TalkgroupSub
from .corridor import CorridorHit


@dataclass
class RepeaterResult:
    hit: CorridorHit
    profile: DeviceProfile

    @property
    def device(self):
        return self.hit.device


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
            parts.append(f"{s.talkgroup}⇄{ext}" if ext and ext != "Cluster" else f"{s.talkgroup}(Cluster)")
    return ", ".join(parts)


def print_table(results: list[RepeaterResult], console: Console | None = None) -> None:
    console = console or Console()
    table = Table(
        title="DMR-Relais entlang der Strecke "
              "(RX/TX aus Sicht deines Funkgeräts)",
        caption="⏱ = zeitgeschaltet (Uhrzeiten: Lokalzeit), "
                "⇄ = Cluster (lokale TG ⇄ Cluster-TG)",
    )
    table.add_column("km", justify="right")
    table.add_column("Rufzeichen")
    table.add_column("Standort", max_width=24)
    table.add_column("Abst.", justify="right")
    table.add_column("RX [MHz]", justify="right")
    table.add_column("TX [MHz]", justify="right")
    table.add_column("CC", justify="right")
    table.add_column("TS1", max_width=28)
    table.add_column("TS2", max_width=36)
    for r in results:
        d = r.device
        table.add_row(
            f"{r.hit.chainage_km:.0f}",
            d.callsign,
            d.city,
            f"{r.hit.distance_km:.1f}",
            f"{d.tx_mhz:.5f}",   # Relais-TX = dein RX
            f"{d.rx_mhz:.5f}",   # Relais-RX = dein TX
            str(d.colorcode or ""),
            _fmt_subs(r.profile.for_slot(1)),
            _fmt_subs(r.profile.for_slot(2)),
        )
    console.print(table)


def write_csv(results: list[RepeaterResult], path: Path) -> None:
    fields = [
        "strecken_km", "rufzeichen", "standort", "abstand_km",
        "rx_mhz", "tx_mhz", "colorcode",
        "ts1_statisch", "ts1_zeitgeschaltet",
        "ts2_statisch", "ts2_zeitgeschaltet", "cluster",
        "antenne_agl_m", "leistung_w", "dmr_id", "last_seen",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        for r in results:
            d = r.device

            def tgs(slot: int, kind: str) -> str:
                kinds = ("static", "implicit") if kind == "static" else (kind,)
                items = [s for s in r.profile.for_slot(slot) if s.kind in kinds]
                if kind == "timed":
                    return ", ".join(
                        f"{s.talkgroup} ({s.note})" if s.note else str(s.talkgroup)
                        for s in items
                    )
                return ", ".join(str(s.talkgroup) for s in items)

            w.writerow({
                "strecken_km": f"{r.hit.chainage_km:.1f}",
                "rufzeichen": d.callsign,
                "standort": d.city,
                "abstand_km": f"{r.hit.distance_km:.1f}",
                "rx_mhz": f"{d.tx_mhz:.5f}",  # aus Gerätesicht
                "tx_mhz": f"{d.rx_mhz:.5f}",
                "colorcode": d.colorcode or "",
                "ts1_statisch": tgs(1, "static"),
                "ts1_zeitgeschaltet": tgs(1, "timed"),
                "ts2_statisch": tgs(2, "static"),
                "ts2_zeitgeschaltet": tgs(2, "timed"),
                "cluster": ", ".join(
                    f"TS{s.slot} {s.talkgroup}->{s.note.removeprefix('Cluster-TG ')}"
                    for s in r.profile.subscriptions if s.kind == "cluster"
                ),
                "antenne_agl_m": d.agl or "",
                "leistung_w": d.pep or "",
                "dmr_id": d.id,
                "last_seen": d.last_seen,
            })
