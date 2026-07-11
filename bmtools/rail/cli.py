"""bm-rail: DMR-Relais entlang einer Bahnstrecke finden.

Ohne Argumente startet ein interaktiver Assistent (inkl. Auswahl der
konkreten Zugverbindung); alle Angaben lassen sich auch als Flags
übergeben (für Skripte/Wiederholläufe).
"""
from __future__ import annotations

import argparse
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.progress import track

from bmtools.bm_api import BrandmeisterClient, DeviceProfile, TalkgroupSub
from .codeplug.anytone import write_anytone
from .corridor import find_in_corridor
from .mapview import write_map
from .report import RepeaterResult, print_table, write_csv
from .report_html import write_html_report
from .route import (ItineraryOption, NoItineraryError, PlanOptions,
                    RoutePlanner, Station)

EXAMPLES = """\
Beispiele:
  bm-rail                                          interaktiver Assistent
  bm-rail --from "Koblenz Hbf" --to "Nürnberg Hbf"
  bm-rail --from Hamburg --to München --modes fern --direct
  bm-rail --from Koblenz --to Nürnberg --time "2026-07-14 08:00"
  bm-rail --from Koblenz --to Nürnberg --time "2026-07-14 17:30" --arrive
  bm-rail --stations "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --straight-line
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


def _parse_time(raw: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%H:%M"):
        try:
            t = datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":  # nur Uhrzeit -> heute
            now = datetime.now()
            t = t.replace(year=now.year, month=now.month, day=now.day)
        return t.astimezone()
    raise argparse.ArgumentTypeError(
        f"Zeitangabe nicht verstanden: {raw!r} "
        f"(Formate: 'JJJJ-MM-TT HH:MM', 'TT.MM.JJJJ HH:MM' oder 'HH:MM')")


def _norm(s: str) -> str:
    return re.sub(r"\W+", "", s).lower()


def _resolve_stations(planner: RoutePlanner, names: list[str],
                      console: Console, interactive: bool) -> list[Station]:
    """Bahnhofsnamen auflösen; bei Mehrdeutigkeit interaktiv nachfragen."""
    stations: list[Station] = []
    for name in names:
        candidates = planner.geocode_candidates(name)
        if (interactive and len(candidates) > 1
                and _norm(candidates[0].name) != _norm(name)):
            console.print(f"  [bold]'{name}' ist mehrdeutig:[/bold]")
            for i, c in enumerate(candidates, start=1):
                console.print(f"    [cyan]{i}[/cyan]  {c.label}")
            idx = IntPrompt.ask(
                "  [cyan]Welcher Bahnhof?[/cyan]",
                choices=[str(i) for i in range(1, len(candidates) + 1)],
                default=1)
            chosen = candidates[idx - 1]
        else:
            chosen = candidates[0]
        if interactive:
            console.print(f"  [dim]→ {chosen.label}[/dim]")
        stations.append(chosen)
    return stations


def _interactive(console: Console, args: argparse.Namespace,
                 planner: RoutePlanner) -> list[Station]:
    """Fragt Strecke, Verbindungsfilter und Korridor ab."""
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
    via = [v.strip() for v in via_raw.split(",") if v.strip()]
    stations = _resolve_stations(
        planner, [origin, *via, destination], console, interactive=True)
    args.modes = Prompt.ask(
        "  [cyan]Zuggattung[/cyan] [dim](alle=Fern+Nah)[/dim]",
        choices=["alle", "fern", "nah"], default=args.modes,
    )
    args.direct = Confirm.ask(
        "  [cyan]Nur Direktverbindungen?[/cyan]", default=args.direct)
    time_raw = Prompt.ask(
        "  [cyan]Abfahrtszeit[/cyan] [dim](z. B. '2026-07-14 08:00' oder "
        "'08:00'; leer = jetzt)[/dim]",
        default="", show_default=False,
    )
    if time_raw.strip():
        args.time = _parse_time(time_raw)
        args.arrive = Confirm.ask(
            "  [cyan]Ist das die Ankunftszeit (statt Abfahrt)?[/cyan]",
            default=False)
    args.corridor = FloatPrompt.ask(
        "  [cyan]Korridorbreite in km[/cyan]", default=args.corridor)
    args.open = True
    return stations


def _make_chooser(console: Console):
    """Interaktive Auswahl unter den gefundenen Verbindungen je Abschnitt."""
    def chooser(options: list[ItineraryOption],
                frm: Station, to: Station) -> ItineraryOption:
        if len(options) == 1:
            console.print(f"  Verbindung {frm.name} → {to.name}: "
                          f"{options[0].summary}")
            return options[0]
        console.print(f"\n  [bold]Verbindungen {frm.name} → {to.name}:[/bold]")
        for i, o in enumerate(options, start=1):
            console.print(f"    [cyan]{i}[/cyan]  {o.summary}")
        idx = IntPrompt.ask(
            "  [cyan]Welche Verbindung?[/cyan]",
            choices=[str(i) for i in range(1, len(options) + 1)], default=1)
        return options[idx - 1]
    return chooser


def _run(stations: list[Station], args: argparse.Namespace, console: Console,
         planner: RoutePlanner, interactive: bool) -> int:
    names = [s.name for s in stations]
    out_dir = args.out or Path("out") / f"{_slug(names[0])}-{_slug(names[-1])}"
    out_dir.mkdir(parents=True, exist_ok=True)

    opts = PlanOptions(modes=args.modes, time=args.time,
                       arrive_by=args.arrive, direct_only=args.direct)
    console.print(f"\n[bold]Route:[/bold] {' → '.join(s.label for s in stations)}")
    chooser = _make_chooser(console) if interactive else None
    route = (planner.route_interpolated(stations) if args.straight_line
             else planner.route(stations, opts, chooser))
    console.print(f"  Gewählte Verbindung: {', '.join(route.legs) or 'Luftlinie'}")

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
    write_anytone(results, out_dir / "anytone", zone, tg_names)

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
    ap.add_argument("--modes", choices=["alle", "fern", "nah"], default="alle",
                    help="Zuggattung: fern = ICE/IC/Nachtzug, nah = RE/RB/S-Bahn "
                         "(Default: alle)")
    ap.add_argument("--time", type=_parse_time, default=None, metavar="ZEIT",
                    help="Abfahrtszeit, z. B. '2026-07-14 08:00' oder '08:00' "
                         "(Default: jetzt)")
    ap.add_argument("--arrive", action="store_true",
                    help="--time als Ankunftszeit interpretieren")
    ap.add_argument("--direct", action="store_true",
                    help="Nur Direktverbindungen (ohne Umstieg)")
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
    interactive = False
    planner = RoutePlanner()
    try:
        if args.stations:
            names = [s.strip() for s in args.stations.split(",") if s.strip()]
            stations = _resolve_stations(planner, names, console, interactive=False)
        elif args.origin and args.destination:
            names = [args.origin, *args.via, args.destination]
            stations = _resolve_stations(planner, names, console, interactive=False)
        elif sys.stdin.isatty() and not (args.origin or args.destination):
            interactive = True
            stations = _interactive(console, args, planner)
        else:
            ap.error("Entweder --from UND --to angeben, oder --stations, "
                     "oder ohne Argumente interaktiv starten.")

        return _run(stations, args, console, planner, interactive)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Abgebrochen.[/dim]")
        return 130
    except NoItineraryError as e:
        console.print(f"[red]{e}[/red]\n"
                      "Tipp: Filter lockern (--modes alle, ohne --direct) "
                      "oder andere Uhrzeit wählen.")
        return 1
    except RuntimeError as e:
        console.print(f"[red]Fehler:[/red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
