"""bm-rail: DMR-Relais entlang einer Bahnstrecke finden.

Ohne Argumente startet ein interaktiver Assistent (inkl. Auswahl der
konkreten Zugverbindung); alle Angaben lassen sich auch als Flags
übergeben (für Skripte/Wiederholläufe).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import questionary
from questionary import Choice
from rich.console import Console
from rich.panel import Panel

from bmtools.routelib.pipeline import run_pipeline, slug
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


def _q(prompt):
    """questionary-Prompt ausführen; Ctrl-C/ESC bricht sauber ab."""
    answer = prompt.ask()
    if answer is None:
        raise KeyboardInterrupt
    return answer


def _text_with_default(message: str, default: str, validate=None) -> str:
    """Texteingabe mit leerem Feld statt Vorbefüllung: Der Default steht
    als Hinweis daneben und gilt bei leerer Eingabe — nichts wegzulöschen."""
    wrapped = (lambda v: True if not v.strip() else validate(v)) if validate else None
    answer = _q(questionary.text(
        message, instruction=f"(Enter = {default})", validate=wrapped)).strip()
    return answer or default


def _time_valid(raw: str):
    if not raw.strip():
        return True
    try:
        _parse_time(raw)
        return True
    except argparse.ArgumentTypeError:
        return "Format: 'JJJJ-MM-TT HH:MM', 'TT.MM.JJJJ HH:MM' oder 'HH:MM'"


def _float_valid(raw: str):
    try:
        float(raw.replace(",", "."))
        return True
    except ValueError:
        return "Bitte eine Zahl eingeben"


def _resolve_stations(planner: RoutePlanner, names: list[str],
                      console: Console, interactive: bool) -> list[Station]:
    """Bahnhofsnamen auflösen.

    Interaktiv wird bei mehreren Kandidaten IMMER gefragt (Top-Treffer
    vorausgewählt): Namensgleichheit ist kein Eindeutigkeitsbeweis —
    'Koblenz' ist z. B. exakt der Name eines Schweizer Bahnhofs."""
    stations: list[Station] = []
    for name in names:
        candidates = planner.geocode_candidates(name)
        if interactive and len(candidates) > 1:
            chosen = _q(questionary.select(
                f"Bahnhof für '{name}':",
                choices=[Choice(c.label, value=c) for c in candidates]))
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
        "einer Bahnstrecke\n[dim]Auswahl mit ↑/↓ und Enter; Texteingaben "
        "mit Enter bestätigen.[/dim]",
        border_style="cyan",
    ))
    origin = _text_with_default("Startbahnhof:", "Nürnberg Hbf")
    destination = _text_with_default("Zielbahnhof:", "Berlin Hbf")
    via_raw = _q(questionary.text("Zwischenhalte (optional, Komma-getrennt):"))
    via = [v.strip() for v in via_raw.split(",") if v.strip()]
    stations = _resolve_stations(
        planner, [origin, *via, destination], console, interactive=True)
    args.modes = _q(questionary.select(
        "Zuggattung:",
        choices=[
            Choice("alle  — Fern- und Nahverkehr", "alle"),
            Choice("fern  — ICE/IC/EC und Nachtzüge", "fern"),
            Choice("nah   — RE/RB/S-Bahn", "nah"),
        ],
        default=None))
    args.direct = _q(questionary.confirm(
        "Nur Direktverbindungen?", default=args.direct))
    time_raw = _q(questionary.text(
        "Abfahrtszeit (z. B. '2026-07-14 08:00' oder '08:00'; leer = jetzt):",
        validate=_time_valid))
    if time_raw.strip():
        args.time = _parse_time(time_raw)
        args.arrive = _q(questionary.confirm(
            "Ist das die Ankunftszeit (statt Abfahrt)?", default=False))
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
        return _q(questionary.select(
            f"Verbindung {frm.name} → {to.name}:",
            choices=[Choice(o.summary, value=o) for o in options]))
    return chooser


def _run(stations: list[Station], args: argparse.Namespace, console: Console,
         planner: RoutePlanner, interactive: bool) -> int:
    names = [s.name for s in stations]
    out_dir = args.out or Path("out") / f"{slug(names[0])}-{slug(names[-1])}"

    opts = PlanOptions(modes=args.modes, time=args.time,
                       arrive_by=args.arrive, direct_only=args.direct)
    console.print(f"\n[bold]Route:[/bold] {' → '.join(s.label for s in stations)}")
    chooser = _make_chooser(console) if interactive else None
    route = (planner.route_interpolated(stations) if args.straight_line
             else planner.route(stations, opts, chooser))
    console.print(f"  Gewählte Verbindung: {', '.join(route.legs) or 'Luftlinie'}")

    zone = f"{names[0].removesuffix(' Hbf')}-{names[-1].removesuffix(' Hbf')}"
    return run_pipeline(
        route, console=console, out_dir=out_dir, corridor_km=args.corridor,
        no_terrain=args.no_terrain, open_browser=args.open, zone=zone,
        route_label="Bahnstrecke", waypoint_icon="train",
        refresh=args.refresh)


def main() -> int:
    ap = argparse.ArgumentParser(
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
    ap.add_argument("--corridor", type=float, default=None, metavar="KM",
                    help="Optionales Limit: maximaler Streckenabstand in km. "
                         "Ohne Angabe zählt allein die rechnerische "
                         "Erreichbarkeit des Relais von der Strecke")
    ap.add_argument("--straight-line", action="store_true",
                    help="Keine Verbindungssuche, Luftlinie zwischen Bahnhöfen")
    ap.add_argument("--no-terrain", action="store_true",
                    help="Abdeckungsschätzung ohne Geländemodell "
                         "(kein Höhenkachel-Download)")
    ap.add_argument("--refresh", action="store_true",
                    help="Brandmeister-Daten frisch laden statt aus dem "
                         "Cache (Geräteliste hält sonst 1 Tag, Profile 12 h)")
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
