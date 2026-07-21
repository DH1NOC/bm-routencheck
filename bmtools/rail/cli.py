"""bm-rail: DMR-Relais entlang einer Bahnstrecke finden.

Ohne Argumente startet ein interaktiver Assistent (inkl. Auswahl der
konkreten Zugverbindung); alle Angaben lassen sich auch als Flags
übergeben (für Skripte/Wiederholläufe). Alternativ übernimmt ein
bahn.de-Verbindungslink (…?vbid=…) die dort gewählte Verbindung direkt.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import questionary
from questionary import Choice
from rich.console import Console

from bmtools import gui, ui
from bmtools.routelib.melden import Melder, TerminalMelder
from bmtools.routelib.model import Route, Station
from bmtools.routelib.pipeline import run_pipeline, slug

from .bahn_link import BahnLinkError, extract_vbid, fetch_verbindung
from .route import Chooser, ItineraryOption, NoItineraryError, PlanOptions, RoutePlanner

EXAMPLES = """\
Beispiele:
  bm-bahn                                          interaktiver Assistent
  bm-bahn "https://www.bahn.de/buchung/start?vbid=…"   Verbindung aus bahn.de-Link
  bm-bahn --von "Koblenz Hbf" --nach "Nürnberg Hbf"
  bm-bahn --von Hamburg --nach München --zuggattung fern --direkt
  bm-bahn --von Koblenz --nach Nürnberg --zeit "2026-07-14 08:00"
  bm-bahn --von Koblenz --nach Nürnberg --zeit "2026-07-14 17:30" --ankunft
  bm-bahn --bahnhoefe "Koblenz Hbf, Mainz Hbf, Würzburg Hbf" --luftlinie

Die englischen Namen (bm-rail, --from, --to, …) bleiben als Aliasse gültig.
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


def _q(prompt: questionary.Question) -> Any:
    """questionary-Prompt ausführen; Ctrl-C/ESC bricht sauber ab."""
    answer = prompt.ask()
    if answer is None:
        raise KeyboardInterrupt
    return answer


def _text_with_default(message: str, default: str,
                       validate: Callable[[str], bool | str] | None = None,
                       ) -> str:
    """Texteingabe mit leerem Feld statt Vorbefüllung: Der Default steht
    als Hinweis daneben und gilt bei leerer Eingabe — nichts wegzulöschen."""
    wrapped = (lambda v: True if not v.strip() else validate(v)) if validate else None
    answer = _q(questionary.text(
        message, instruction=f"(Enter = {default})", validate=wrapped,
        style=ui.QSTYLE)).strip()
    return answer or default


def _time_valid(raw: str) -> bool | str:
    if not raw.strip():
        return True
    try:
        _parse_time(raw)
        return True
    except argparse.ArgumentTypeError:
        return "Format: 'JJJJ-MM-TT HH:MM', 'TT.MM.JJJJ HH:MM' oder 'HH:MM'"


def _float_valid(raw: str) -> bool | str:
    try:
        float(raw.replace(",", "."))
        return True
    except ValueError:
        return "Bitte eine Zahl eingeben"


def _link_valid(raw: str) -> bool | str:
    if not raw.strip():
        return True
    try:
        extract_vbid(raw)
        return True
    except BahnLinkError:
        return "Kein bahn.de-Verbindungslink (es fehlt …?vbid=…)"


def _resolve_stations(planner: RoutePlanner, names: list[str],
                      melder: Melder, interactive: bool) -> list[Station]:
    """Bahnhofsnamen auflösen.

    Interaktiv wird bei mehreren Kandidaten IMMER gefragt (Top-Treffer
    vorausgewählt): Namensgleichheit ist kein Eindeutigkeitsbeweis —
    'Koblenz' ist z. B. exakt der Name eines Schweizer Bahnhofs."""
    stations: list[Station] = []
    for name in names:
        candidates = planner.geocode_candidates(name)
        if interactive and len(candidates) > 1:
            chosen = candidates[melder.auswahl(
                f"Bahnhof für '{name}':",
                [c.label for c in candidates])]
        else:
            chosen = candidates[0]
        if interactive:
            melder.text(f"  [dim]→ {chosen.label}[/dim]")
        stations.append(chosen)
    return stations


def _interactive(console: Console, args: argparse.Namespace,
                 planner: RoutePlanner, melder: Melder) -> list[Station]:
    """Fragt Strecke, Verbindungsfilter und Korridor ab. Wird ein
    bahn.de-Link eingefügt, landet er in args.link und die Liste
    bleibt leer — die Verbindung steht dann schon fest."""
    console.print()
    ui.banner(console, "bm-bahn — DMR- und FM-Relais entlang einer Bahnstrecke",
              "Zugverbindung wählen — Bericht, Karte, CSV und Codeplug "
              "für die ganze Fahrt", icon="🚆")
    link = _q(questionary.text(
        "bahn.de-Verbindungslink (…?vbid=…; leer = Verbindung hier suchen):",
        validate=_link_valid, style=ui.QSTYLE)).strip()
    if link:
        args.link = link
        args.open = True
        return []
    origin = _text_with_default("Startbahnhof:", "Nürnberg Hbf")
    destination = _text_with_default("Zielbahnhof:", "Berlin Hbf")
    via_raw = _q(questionary.text("Zwischenhalte (optional, Komma-getrennt):",
                                  style=ui.QSTYLE))
    via = [v.strip() for v in via_raw.split(",") if v.strip()]
    stations = _resolve_stations(
        planner, [origin, *via, destination], melder, interactive=True)
    args.modes = _q(questionary.select(
        "Zuggattung:",
        choices=[
            Choice("alle  — Fern- und Nahverkehr", "alle"),
            Choice("fern  — ICE/IC/EC und Nachtzüge", "fern"),
            Choice("nah   — RE/RB/S-Bahn", "nah"),
        ],
        default=None, style=ui.QSTYLE, pointer=ui.POINTER))
    args.direct = _q(questionary.confirm(
        "Nur Direktverbindungen?", default=args.direct, style=ui.QSTYLE))
    time_raw = _q(questionary.text(
        "Abfahrtszeit (z. B. '2026-07-14 08:00' oder '08:00'; leer = jetzt):",
        validate=_time_valid, style=ui.QSTYLE))
    if time_raw.strip():
        args.time = _parse_time(time_raw)
        args.arrive = _q(questionary.confirm(
            "Ist das die Ankunftszeit (statt Abfahrt)?", default=False,
            style=ui.QSTYLE))
    args.open = True
    return stations


def _make_chooser(melder: Melder) -> Chooser:
    """Interaktive Auswahl unter den gefundenen Verbindungen je Abschnitt."""
    def chooser(options: list[ItineraryOption],
                frm: Station, to: Station) -> ItineraryOption:
        if len(options) == 1:
            melder.text(f"  Verbindung {frm.name} → {to.name}: "
                        f"{options[0].summary}")
            return options[0]
        return options[melder.auswahl(
            f"Verbindung {frm.name} → {to.name}:",
            [o.summary for o in options])]
    return chooser


def _pipeline(route: Route, args: argparse.Namespace, melder: Melder,
              interactive: bool = False,
              modus_fragen: bool | None = None) -> int:
    # Letzte Frage des Assistenten, bewusst NACH der kompletten
    # Streckenwahl (Nutzerwunsch 2026-07-15: Modus am Ende, nie
    # mittendrin). Die GUI stellt sie im Formular und schaltet sie
    # hier ab (modus_fragen=False bei interactive=True).
    if modus_fragen is None:
        modus_fragen = interactive
    if modus_fragen:
        args.modus = _q(ui.modus_frage(args.modus))
    names = [s.name for s in route.stations]
    out_dir = args.out or Path("out") / f"{slug(names[0])}-{slug(names[-1])}"
    zone = f"{names[0].removesuffix(' Hbf')}-{names[-1].removesuffix(' Hbf')}"
    return run_pipeline(
        route, melder=melder, out_dir=out_dir, corridor_km=args.corridor,
        no_terrain=args.no_terrain, open_browser=args.open, zone=zone,
        route_label="Bahnstrecke", waypoint_icon="train",
        refresh=args.refresh, modus=args.modus,
        bandbreite=args.bandbreite, ctcss_decode=args.ctcss_decode,
        pdf=args.pdf, interactive=interactive)


def _run(stations: list[Station], args: argparse.Namespace, melder: Melder,
         planner: RoutePlanner, interactive: bool,
         modus_fragen: bool | None = None) -> int:
    opts = PlanOptions(modes=args.modes, time=args.time,
                       arrive_by=args.arrive, direct_only=args.direct)
    melder.text(f"\n[bold]Route:[/bold] {' → '.join(s.label for s in stations)}")
    chooser = _make_chooser(melder) if interactive else None
    route = (planner.route_interpolated(stations) if args.straight_line
             else planner.route(stations, opts, chooser))
    melder.text(f"  Gewählte Verbindung: {', '.join(route.legs) or 'Luftlinie'}")
    return _pipeline(route, args, melder, interactive, modus_fragen)


def _run_link(link: str, args: argparse.Namespace, melder: Melder,
              planner: RoutePlanner, interactive: bool,
              modus_fragen: bool | None = None) -> int:
    """Verbindung aus bahn.de-Link übernehmen statt selbst zu suchen."""
    verbindung = fetch_verbindung(extract_vbid(link))
    melder.text(f"\n[bold]Verbindung laut bahn.de[/bold] "
                f"({verbindung.datum:%d.%m.%Y}): "
                f"{verbindung.start_ort} → {verbindung.ziel_ort}")
    for leg in verbindung.legs:
        plus = " (+1)" if leg.arr.date() != leg.dep.date() else ""
        melder.text(f"  {leg.dep:%H:%M} {leg.frm.name} → "
                    f"{leg.arr:%H:%M}{plus} {leg.to.name}  "
                    f"[dim]{leg.train}[/dim]")
    if interactive and not melder.frage_ja("Diese Verbindung verwenden?"):
        raise KeyboardInterrupt
    with melder.status("Strecke auflösen …") as status_update:
        route = planner.route_fixed(
            verbindung.legs,
            warn=lambda msg: melder.text(f"[yellow]{msg}[/yellow]"),
            progress=status_update)
    melder.text(f"  Übernommene Fahrt: {', '.join(route.legs) or 'Luftlinie'}")
    return _pipeline(route, args, melder, interactive, modus_fragen)


def main(*, gui_start: bool = True) -> int:
    """gui_start=False: nur Terminal (das bmtools-Menü ruft die Tools so
    auf — wer schon im Terminal-Menü ist, will kein Fenster)."""
    ui.argparse_deutsch()
    ap = argparse.ArgumentParser(
        description="Findet DMR-Relais (Brandmeister) und analoge FM-Relais "
                    "(relaislisten.darc.de) entlang einer Bahnstrecke — "
                    "Rufzeichen, Frequenzen, Talkgroups TS1/TS2 inkl. "
                    "Zeitschaltung und Cluster, CTCSS.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("link", nargs="?", metavar="LINK",
                    help="bahn.de-Verbindungslink (…?vbid=…) — die dort "
                         "gewählte Verbindung wird direkt übernommen, "
                         "Zeit-/Zugfilter entfallen")
    ap.add_argument("--von", "--from", dest="origin", metavar="BAHNHOF",
                    help="Startbahnhof, z. B. 'Koblenz Hbf'")
    ap.add_argument("--nach", "--to", dest="destination", metavar="BAHNHOF",
                    help="Zielbahnhof")
    ap.add_argument("--via", action="append", default=[], metavar="BAHNHOF",
                    help="Zwischenhalt (mehrfach möglich)")
    ap.add_argument("--bahnhoefe", "--stations", dest="stations",
                    metavar="LISTE",
                    help="Alternativ: kommagetrennte Bahnhofsliste")
    ap.add_argument("--zuggattung", "--modes", dest="modes",
                    choices=["alle", "fern", "nah"], default="alle",
                    help="fern = ICE/IC/Nachtzug, nah = RE/RB/S-Bahn "
                         "(Default: alle)")
    ap.add_argument("--zeit", "--time", dest="time", type=_parse_time,
                    default=None, metavar="ZEIT",
                    help="Abfahrtszeit, z. B. '2026-07-14 08:00' oder '08:00' "
                         "(Default: jetzt)")
    ap.add_argument("--ankunft", "--arrive", dest="arrive",
                    action="store_true",
                    help="--zeit als Ankunftszeit interpretieren")
    ap.add_argument("--direkt", "--direct", dest="direct",
                    action="store_true",
                    help="Nur Direktverbindungen (ohne Umstieg)")
    ui.add_start_arguments(ap)
    ui.add_fm_arguments(ap)
    ap.add_argument("--korridor", "--corridor", dest="corridor", type=float,
                    default=None, metavar="KM",
                    help="Optionales Limit: maximaler Streckenabstand in km. "
                         "Ohne Angabe zählt allein die rechnerische "
                         "Erreichbarkeit des Relais von der Strecke")
    ap.add_argument("--luftlinie", "--straight-line", dest="straight_line",
                    action="store_true",
                    help="Keine Verbindungssuche, Luftlinie zwischen Bahnhöfen")
    ap.add_argument("--ohne-gelaende", "--no-terrain", dest="no_terrain",
                    action="store_true",
                    help="Abdeckungsschätzung ohne Geländemodell "
                         "(kein Höhenkachel-Download)")
    ap.add_argument("--aktualisieren", "--refresh", dest="refresh",
                    action="store_true",
                    help="Relais-Daten frisch laden statt aus dem Cache "
                         "(BM-Geräteliste und FM-Liste halten sonst 1 Tag, "
                         "Profile 12 h)")
    ap.add_argument("--pdf", action="store_true",
                    help="zusätzlich bericht.pdf erzeugen (Deckblatt, "
                         "Übersichtskarte, Relais-Tabelle; DIN A4)")
    ap.add_argument("--oeffnen", "--open", dest="open", action="store_true",
                    help="Bericht und Karte danach im Browser öffnen")
    ap.add_argument("--ausgabe", "--out", dest="out", type=Path, default=None,
                    metavar="ORDNER",
                    help="Ausgabeverzeichnis (Default: out/<start>-<ziel>)")
    args = ap.parse_args()

    console = Console()
    # GUI-Entscheidung (GUI-UMBAU.md): nur ohne Strecken-Argumente —
    # Skript-Aufrufe mit Flags laufen unverändert im Terminal.
    strecken_args = bool(args.link or args.stations
                         or args.origin or args.destination or args.via)
    if args.gui and strecken_args:
        ap.error("--gui kann nicht mit Strecken-Argumenten kombiniert "
                 "werden — die Eingaben macht man dann im Fenster")
    if gui_start and not args.terminal and not strecken_args:
        code = gui.start_oder_none(console, "bahn", erzwungen=args.gui)
        if code is not None:
            return code
    interactive = False
    melder = TerminalMelder(console)
    planner = RoutePlanner()
    try:
        if args.link:
            return _run_link(args.link, args, melder, planner,
                             interactive=False)
        if args.stations:
            names = [s.strip() for s in args.stations.split(",") if s.strip()]
            stations = _resolve_stations(planner, names, melder, interactive=False)
        elif args.origin and args.destination:
            names = [args.origin, *args.via, args.destination]
            stations = _resolve_stations(planner, names, melder, interactive=False)
        elif sys.stdin.isatty() and not (args.origin or args.destination):
            interactive = True
            stations = _interactive(console, args, planner, melder)
            if args.link:  # Assistent bekam einen bahn.de-Link
                return _run_link(args.link, args, melder, planner,
                                 interactive=True)
        else:
            ap.error("Entweder LINK (bahn.de) angeben, --von UND --nach, "
                     "--bahnhoefe, oder ohne Argumente interaktiv starten.")

        return _run(stations, args, melder, planner, interactive)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Abgebrochen.[/dim]")
        return 130
    except BahnLinkError as e:
        console.print(f"[red]{e}[/red]")
        return 1
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
