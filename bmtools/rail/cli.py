"""bm-rail: DMR-Relais entlang einer Bahnstrecke finden.

Ohne Argumente startet ein interaktiver Assistent; alle Angaben lassen
sich auch als Flags übergeben (für Skripte/Wiederholläufe).
"""
from __future__ import annotations

import argparse
import re
import sys
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, Prompt
from rich.progress import track

from bmtools.bm_api import BrandmeisterClient, DeviceProfile, TalkgroupSub
from .codeplug.anytone import write_anytone
from .corridor import find_in_corridor
from .mapview import write_map
from .report import RepeaterResult, print_table, write_csv
from .report_html import write_html_report
from .route import RoutePlanner

EXAMPLES = """\
Beispiele:
  bm-rail                                          interaktiver Assistent
  bm-rail --from "Koblenz Hbf" --to "Nürnberg Hbf"
  bm-rail --from Koblenz --via "Frankfurt Hbf" --to Nürnberg --corridor 20
  bm-rail --stations "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --straight-line
  bm-rail --from Koblenz --to Nürnberg --open      Bericht + Karte im Browser öffnen
"""


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


def _interactive(console: Console, args: argparse.Namespace) -> list[str]:
    """Fragt Strecke und Korridor ab; gibt die Bahnhofsliste zurück."""
    console.print(Panel.fit(
        "[bold]bm-rail[/bold] — findet Brandmeister-DMR-Relais entlang "
        "einer Bahnstrecke\n[dim]Leere Eingabe übernimmt den Vorschlag in "
        "Klammern.[/dim]",
        border_style="cyan",
    ))
    origin = Prompt.ask("  [cyan]Startbahnhof[/cyan]", default="Koblenz Hbf")
    destination = Prompt.ask("  [cyan]Zielbahnhof[/cyan]", default="Nürnberg Hbf")
    via_raw = Prompt.ask(
        "  [cyan]Zwischenhalte[/cyan] [dim](optional, Komma-getrennt)[/dim]",
        default="", show_default=False,
    )
    args.corridor = FloatPrompt.ask(
        "  [cyan]Korridorbreite in km[/cyan]", default=args.corridor)
    args.open = True
    via = [v.strip() for v in via_raw.split(",") if v.strip()]
    return [origin, *via, destination]


def _run(names: list[str], args: argparse.Namespace, console: Console) -> int:
    out_dir = args.out or Path("out") / f"{_slug(names[0])}-{_slug(names[-1])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    planner = RoutePlanner()
    console.print(f"\n[bold]Route:[/bold] {' → '.join(names)}")
    route = (planner.route_interpolated(names) if args.straight_line
             else planner.route(names))
    console.print(f"  Gefundene Verbindung: {', '.join(route.legs) or 'Luftlinie'}")

    client = BrandmeisterClient()
    console.print("[bold]Lade Brandmeister-Geräteliste …[/bold]")
    repeaters = client.repeaters()
    hits = find_in_corridor(repeaters, route.points, args.corridor)
    console.print(f"  {len(repeaters)} Repeater im Netz, "
                  f"[bold]{len(hits)}[/bold] im {args.corridor:g}-km-Korridor")
    if not hits:
        console.print("[red]Keine Relais im Korridor gefunden.[/red] "
                      "Tipp: Korridor vergrößern (--corridor 25).")
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
    anytone_dir = out_dir / "anytone"
    write_anytone(results, anytone_dir, zone, tg_names)

    console.print(Panel.fit(
        f"[green]Fertig.[/green] Ausgaben in [bold]{out_dir}/[/bold]\n"
        f"  bericht.html   Kanaltabellen für manuelle CPS-Eingabe\n"
        f"  karte.html     interaktive Streckenkarte\n"
        f"  relais.csv     Rohdaten (Semikolon-getrennt)\n"
        f"  anytone/       Channel/TalkGroups/Zone-CSV "
        f"[yellow](Format vorläufig = D878UV)[/yellow]",
        border_style="green",
    ))

    if args.open:
        webbrowser.open(html_path.resolve().as_uri())
        webbrowser.open(map_path.resolve().as_uri())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="bm-rail",
        description="Findet Brandmeister-DMR-Relais entlang einer Bahnstrecke "
                    "(Rufzeichen, Frequenzen, Talkgroups TS1/TS2 inkl. "
                    "Zeitschaltung und Cluster).",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--from", dest="origin", metavar="BAHNHOF",
                    help="Startbahnhof, z. B. 'Koblenz Hbf'")
    ap.add_argument("--to", dest="destination", metavar="BAHNHOF",
                    help="Zielbahnhof")
    ap.add_argument("--via", action="append", default=[], metavar="BAHNHOF",
                    help="Zwischenhalt (mehrfach möglich)")
    ap.add_argument("--stations", metavar="LISTE",
                    help="Alternativ: kommagetrennte Bahnhofsliste")
    ap.add_argument("--corridor", type=float, default=15.0, metavar="KM",
                    help="Korridorbreite in km (Default: 15)")
    ap.add_argument("--straight-line", action="store_true",
                    help="Keine Verbindungssuche, Luftlinie zwischen Bahnhöfen")
    ap.add_argument("--open", action="store_true",
                    help="Bericht und Karte danach im Browser öffnen")
    ap.add_argument("--out", type=Path, default=None, metavar="DIR",
                    help="Ausgabeverzeichnis (Default: out/<start>-<ziel>)")
    args = ap.parse_args()

    console = Console()
    try:
        if args.stations:
            names = [s.strip() for s in args.stations.split(",") if s.strip()]
        elif args.origin and args.destination:
            names = [args.origin, *args.via, args.destination]
        elif sys.stdin.isatty() and not (args.origin or args.destination):
            names = _interactive(console, args)
        else:
            ap.error("Entweder --from UND --to angeben, oder --stations, "
                     "oder ohne Argumente interaktiv starten.")

        return _run(names, args, console)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Abgebrochen.[/dim]")
        return 130
    except RuntimeError as e:
        console.print(f"[red]Fehler:[/red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
