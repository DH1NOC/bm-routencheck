"""bm-rail: DMR-Relais entlang einer Bahnstrecke finden.

Beispiel:
    bm-rail --from "Koblenz Hbf" --to "Nürnberg Hbf" --corridor 15
    bm-rail --from Koblenz --via "Frankfurt Hbf" --to Nürnberg
    bm-rail --stations "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --straight-line
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import track

from bmtools.bm_api import BrandmeisterClient, DeviceProfile, TalkgroupSub
from .codeplug.anytone import write_anytone
from .corridor import find_in_corridor
from .mapview import write_map
from .report import RepeaterResult, print_table, write_csv
from .report_html import write_html_report
from .route import RoutePlanner


def _with_local_tg(profile: DeviceProfile, simplex: bool) -> DeviceProfile:
    """TG9 'Lokal' ist auf jedem Relais implizit verfügbar, fehlt aber in
    der API — hier als Standard-Eintrag ergänzen (TS2; Simplex: Slot 0)."""
    if not any(s.talkgroup == 9 for s in profile.subscriptions):
        profile.subscriptions.append(
            TalkgroupSub(9, 0 if simplex else 2, "implicit", "Lokal"))
        profile.subscriptions.sort(key=lambda s: (s.slot, s.talkgroup))
    return profile


def _slug(text: str) -> str:
    text = text.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="bm-rail",
        description="Findet Brandmeister-DMR-Relais entlang einer Bahnstrecke.",
    )
    ap.add_argument("--from", dest="origin", help="Startbahnhof, z. B. 'Koblenz Hbf'")
    ap.add_argument("--to", dest="destination", help="Zielbahnhof")
    ap.add_argument("--via", action="append", default=[],
                    help="Zwischenhalt (mehrfach möglich)")
    ap.add_argument("--stations", help="Alternativ: kommagetrennte Bahnhofsliste")
    ap.add_argument("--corridor", type=float, default=15.0,
                    help="Korridorbreite in km (Default: 15)")
    ap.add_argument("--straight-line", action="store_true",
                    help="Keine Verbindungssuche, Luftlinie zwischen Bahnhöfen")
    ap.add_argument("--out", type=Path, default=None,
                    help="Ausgabeverzeichnis (Default: out/<start>-<ziel>)")
    args = ap.parse_args()

    if args.stations:
        names = [s.strip() for s in args.stations.split(",") if s.strip()]
    elif args.origin and args.destination:
        names = [args.origin, *args.via, args.destination]
    else:
        ap.error("Entweder --from/--to oder --stations angeben.")

    console = Console()
    out_dir = args.out or Path("out") / f"{_slug(names[0])}-{_slug(names[-1])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    planner = RoutePlanner()
    console.print(f"[bold]Route:[/bold] {' → '.join(names)}")
    route = (planner.route_interpolated(names) if args.straight_line
             else planner.route(names))
    console.print(f"  Verbindung: {', '.join(route.legs) or 'Luftlinie'}"
                  f" ({len(route.points)} Streckenpunkte)")

    client = BrandmeisterClient()
    console.print("[bold]Lade Brandmeister-Geräteliste …[/bold]")
    repeaters = client.repeaters()
    hits = find_in_corridor(repeaters, route.points, args.corridor)
    console.print(f"  {len(repeaters)} Repeater im Netz, "
                  f"{len(hits)} im {args.corridor:g}-km-Korridor")
    if not hits:
        console.print("[red]Keine Relais im Korridor gefunden.[/red]")
        return 1

    results = [
        RepeaterResult(hit=h, profile=_with_local_tg(
            client.profile(h.device.id),
            simplex=h.device.tx_mhz == h.device.rx_mhz))
        for h in track(hits, description="Talkgroup-Profile laden …")
    ]

    print_table(results, console)

    tg_names = client.talkgroup_names()
    csv_path = out_dir / "relais.csv"
    html_path = out_dir / "bericht.html"
    map_path = out_dir / "karte.html"
    write_csv(results, csv_path)
    write_html_report(results, route, html_path, tg_names)
    write_map(results, route, args.corridor, map_path)
    zone = f"{names[0].removesuffix(' Hbf')}-{names[-1].removesuffix(' Hbf')}"
    anytone_files = write_anytone(results, out_dir / "anytone", zone, tg_names)
    console.print(f"\n[green]Geschrieben:[/green] {csv_path}, {html_path}, {map_path}")
    console.print(f"[green]AnyTone-CPS (Format vorläufig = D878UV!):[/green] "
                  f"{', '.join(str(p) for p in anytone_files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
