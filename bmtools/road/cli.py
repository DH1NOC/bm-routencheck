"""bm-car / bm-bike: DMR-Relais entlang einer Auto- oder Radroute.

Eingabewege: Google-Maps-Link (Wegpunkte -> OSRM-Routing), Komoot-Link
(fertige Tour-Geometrie), GPX-Datei oder Start/Ziel als Text. Ohne
Argumente startet ein interaktiver Assistent. Danach läuft dieselbe
Pipeline wie bei bm-rail (Erreichbarkeit im Geländemodell, Bericht,
Karte, CSV, AnyTone-Codeplug).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import questionary
from rich.console import Console

from bmtools import gui, ui
from bmtools.ausgabe import ausgabe_basis
from bmtools.routelib.melden import Melder, TerminalMelder
from bmtools.routelib.model import Route, Waypoint
from bmtools.routelib.pipeline import run_pipeline, slug

from . import RouteInputError
from .geocode import geocode_candidates
from .gmaps_link import (
    SHORTLINK_HOSTS,
    LinkWaypoint,
    expand_short_link,
    parse_gmaps_url,
)
from .gpx import read_gpx
from .komoot import SPORT_LABEL, fetch_tour, is_komoot_url, parse_komoot_url
from .routing import MODE_LABEL, route_from_track, route_waypoints

# profil -> (Tool-Label, Routen-Label für Karte/Texte, folium-Icon, Kommando)
PROFILES = {
    "car": ("Auto", "Autoroute", "car", "bm-auto"),
    "bike": ("Rad", "Radroute", "bicycle", "bm-rad"),
}
# profil -> GUI-Toolname (deutsche Tab-Namen wie im bmtools-Menü)
GUI_TOOL = {"car": "auto", "bike": "rad"}
BANNER_ICON = {"car": "🚗", "bike": "🚴"}

EXAMPLES = """\
Beispiele:
  {p}                                          interaktiver Assistent
  {p} "https://maps.app.goo.gl/…"              Google-Maps-Route
  {p} "https://www.komoot.com/tour/…"          Komoot-Tour (Teilen-Link)
  {p} --gpx tour.gpx                           GPX-Datei (z. B. Komoot-Export)
  {p} --von "Koblenz" --nach "Nürnberg Zollhaus"

Die englischen Namen (bm-car/bm-bike, --from, --to, …) bleiben als
Aliasse gültig.
"""


def _q(prompt: questionary.Question) -> Any:
    """questionary-Prompt ausführen; Ctrl-C/ESC bricht sauber ab."""
    answer = prompt.ask()
    if answer is None:
        raise KeyboardInterrupt
    return answer


def _nonempty(v: str) -> bool | str:
    return True if v.strip() else "Bitte etwas eingeben"


def _short_name(name: str) -> str:
    """Adresse auf den Ortsteil eindampfen (für Zone/Ausgabeordner):
    'Colmantstraße 7, 56170 Bendorf' -> 'Bendorf'."""
    part = name.split(",")[-1].strip()
    return re.sub(r"^\d{4,5}\s+", "", part) or name


def _resolve(names_or_wps: Sequence[str | Waypoint | LinkWaypoint],
             melder: Melder, interactive: bool) -> list[Waypoint]:
    """Unaufgelöste Wegpunkte geocodieren (interaktiv mit Auswahl)."""
    resolved: list[Waypoint] = []
    for item in names_or_wps:
        if isinstance(item, Waypoint):
            resolved.append(item)
            continue
        if (isinstance(item, LinkWaypoint)
                and item.lat is not None and item.lon is not None):
            resolved.append(Waypoint(item.name, item.lat, item.lon))
            continue
        name = item if isinstance(item, str) else item.name
        candidates = geocode_candidates(name)
        if interactive and len(candidates) > 1:
            chosen = candidates[melder.auswahl(
                f"Ort für '{name}':", [c.label for c in candidates])]
        else:
            chosen = candidates[0]
        melder.text(f"  [dim]→ {chosen.label}[/dim]")
        resolved.append(chosen)
    return resolved


def _warn(melder: Melder) -> Callable[[str], None]:
    return lambda msg: melder.text(f"[yellow]{msg}[/yellow]")


def _route_from_gmaps(link: str, args: argparse.Namespace, melder: Melder,
                      profile: str, interactive: bool) -> tuple[Route, str]:
    if urlsplit(link).netloc.lower() in SHORTLINK_HOSTS:
        link = expand_short_link(link)
    g = parse_gmaps_url(link)

    mode = g.mode or profile
    if mode != profile:
        label, tool_label = MODE_LABEL[mode], MODE_LABEL[profile]
        if interactive:
            gewaehlt = melder.auswahl(
                f"Der Link ist eine {label}-Route, aufgerufen ist das "
                f"{tool_label}-Tool. Wonach routen?",
                [f"{label} (wie im Link)", f"{tool_label} (wie das Tool)"])
            mode = (mode, profile)[gewaehlt]
        else:
            melder.text(f"[yellow]Hinweis: Der Link ist eine {label}-Route "
                        f"— geroutet wird nach dem Link ({label}).[/yellow]")

    waypoints = _resolve(g.waypoints, melder, interactive)
    melder.text(f"  [bold]Route ({MODE_LABEL[mode]}):[/bold] "
                + " → ".join(w.name for w in waypoints))
    if interactive and not melder.frage_ja("Route so berechnen?"):
        raise KeyboardInterrupt
    route = route_waypoints(waypoints, mode, warn=_warn(melder))
    zone = f"{_short_name(waypoints[0].name)}-{_short_name(waypoints[-1].name)}"
    return route, zone


def _route_from_komoot(link: str, melder: Melder,
                       interactive: bool) -> tuple[Route, str]:
    tour = fetch_tour(parse_komoot_url(link), page_url=link)
    sport = SPORT_LABEL.get(tour.sport, tour.sport)
    melder.text(f"  [bold]Komoot-Tour:[/bold] {tour.name} "
                f"({sport}, {tour.distance_km:.1f} km, "
                f"{len(tour.points)} Punkte)")
    if interactive and not melder.frage_ja("Diese Tour verwenden?"):
        raise KeyboardInterrupt
    route = route_from_track(
        tour.points, f"Komoot-Tour „{tour.name}“ ({sport}, "
                     f"{tour.distance_km:.1f} km)")
    return route, tour.name


def _route_from_gpx(path: Path, melder: Melder) -> tuple[Route, str]:
    track = read_gpx(path)
    melder.text(f"  [bold]GPX:[/bold] {track.name} "
                f"({len(track.points)} Punkte)")
    route = route_from_track(track.points, f"GPX-Import „{track.name}“")
    return route, track.name


def _interactive(console: Console, args: argparse.Namespace,
                 label: str, cmd: str) -> None:
    """Fragt Link (Google/Komoot) oder Start/Ziel/Via ab."""
    console.print()
    ui.banner(
        console,
        f"{cmd} — DMR- und FM-Relais entlang einer {label}route",
        "Link von Google Maps oder Komoot einfügen — oder leer lassen "
        "und Start/Ziel eintippen",
        icon=BANNER_ICON.get(args.profile, "📡"))
    link = _q(questionary.text(
        "Routen-Link (Google Maps oder Komoot; leer = manuelle Eingabe):",
        style=ui.QSTYLE)).strip()
    if link:
        args.link = link
    else:
        args.origin = _q(questionary.text(
            "Start (Ort oder Adresse):", validate=_nonempty,
            style=ui.QSTYLE)).strip()
        args.destination = _q(questionary.text(
            "Ziel (Ort oder Adresse):", validate=_nonempty,
            style=ui.QSTYLE)).strip()
        via_raw = _q(questionary.text(
            "Zwischenpunkte (optional, Komma-getrennt):", style=ui.QSTYLE))
        args.via = [v.strip() for v in via_raw.split(",") if v.strip()]
    args.open = True


def main(profile: str, *, gui_start: bool = True) -> int:
    """gui_start=False: nur Terminal (das bmtools-Menü ruft die Tools so
    auf — wer schon im Terminal-Menü ist, will kein Fenster)."""
    ui.argparse_deutsch()
    label, route_label, icon, cmd = PROFILES[profile]
    ap = argparse.ArgumentParser(
        description=f"Findet DMR-Relais (Brandmeister) und analoge "
                    f"FM-Relais (relaislisten.darc.de) entlang einer "
                    f"{route_label} — Rufzeichen, Frequenzen, Talkgroups "
                    f"TS1/TS2 inkl. Zeitschaltung und Cluster, CTCSS.",
        epilog=EXAMPLES.format(p=cmd),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("link", nargs="?", metavar="LINK",
                    help="Google-Maps-Routenlink (auch Kurzlink) oder "
                         "Komoot-Tour-Link")
    ap.add_argument("--gpx", type=Path, default=None, metavar="DATEI",
                    help="GPX-Datei statt Link (z. B. Komoot-Export)")
    ap.add_argument("--von", "--from", dest="origin", metavar="ORT",
                    help="Start (Ort/Adresse), Alternative zum Link")
    ap.add_argument("--nach", "--to", dest="destination", metavar="ORT",
                    help="Ziel")
    ap.add_argument("--via", action="append", default=[], metavar="ORT",
                    help="Zwischenpunkt (mehrfach möglich)")
    ui.add_start_arguments(ap)
    ui.add_fm_arguments(ap)
    ap.add_argument("--korridor", "--corridor", dest="corridor", type=float,
                    default=None, metavar="KM",
                    help="Optionales Limit: maximaler Streckenabstand in km. "
                         "Ohne Angabe zählt allein die rechnerische "
                         "Erreichbarkeit des Relais von der Strecke")
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
                    help="Ausgabeverzeichnis (Default: out/<route>)")
    args = ap.parse_args()
    args.profile = profile

    console = Console()
    # GUI-Entscheidung (GUI-UMBAU.md): nur ohne Routen-Argumente —
    # Skript-Aufrufe mit Flags laufen unverändert im Terminal.
    routen_args = bool(args.link or args.gpx
                       or args.origin or args.destination or args.via)
    if args.gui and routen_args:
        ap.error("--gui kann nicht mit Routen-Argumenten kombiniert "
                 "werden — die Eingaben macht man dann im Fenster")
    if gui_start and not args.terminal and not routen_args:
        code = gui.start_oder_none(console, GUI_TOOL[profile],
                                   erzwungen=args.gui)
        if code is not None:
            return code
    interactive = False
    melder = TerminalMelder(console)
    try:
        if not (args.link or args.gpx or (args.origin and args.destination)):
            if sys.stdin.isatty():
                interactive = True
                _interactive(console, args, label, cmd)
            else:
                ap.error("Entweder LINK angeben, oder --gpx DATEI, oder "
                         "--von und --nach, oder ohne Argumente interaktiv "
                         "starten.")

        if args.gpx:
            route, zone = _route_from_gpx(args.gpx, melder)
        elif args.link and is_komoot_url(args.link):
            route, zone = _route_from_komoot(args.link, melder, interactive)
        elif args.link:
            route, zone = _route_from_gmaps(args.link, args, melder,
                                            profile, interactive)
        else:
            names = [args.origin, *args.via, args.destination]
            waypoints = _resolve(names, melder, interactive)
            melder.text(f"  [bold]Route ({MODE_LABEL[profile]}):[/bold] "
                        + " → ".join(w.name for w in waypoints))
            route = route_waypoints(waypoints, profile, warn=_warn(melder))
            zone = (f"{_short_name(waypoints[0].name)}-"
                    f"{_short_name(waypoints[-1].name)}")

        melder.text(f"  {', '.join(route.legs)}")
        # Letzte Frage des Assistenten, bewusst NACH Routenaufbau samt
        # Geocoding-Rückfragen und Bestätigung (Nutzerwunsch 2026-07-15:
        # Modus am Ende, nie mittendrin)
        if interactive:
            args.modus = _q(ui.modus_frage(args.modus))
        out_dir = args.out or ausgabe_basis(args) / slug(zone)
        return run_pipeline(
            route, melder=melder, out_dir=out_dir,
            corridor_km=args.corridor, no_terrain=args.no_terrain,
            open_browser=args.open, zone=zone,
            route_label=route_label, waypoint_icon=icon,
            refresh=args.refresh, modus=args.modus,
            bandbreite=args.bandbreite, ctcss_decode=args.ctcss_decode,
            pdf=args.pdf, interactive=interactive)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Abgebrochen.[/dim]")
        return 130
    except RouteInputError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    except RuntimeError as e:
        console.print(f"[red]Fehler:[/red] {e}")
        return 1


def main_car(*, gui_start: bool = True) -> int:
    return main("car", gui_start=gui_start)


def main_bike(*, gui_start: bool = True) -> int:
    return main("bike", gui_start=gui_start)


if __name__ == "__main__":
    sys.exit(main("car"))
