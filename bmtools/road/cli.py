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
from questionary import Choice
from rich.console import Console

from bmtools import ui
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
             console: Console, interactive: bool) -> list[Waypoint]:
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
            chosen = _q(questionary.select(
                f"Ort für '{name}':",
                choices=[Choice(c.label, value=c) for c in candidates],
                style=ui.QSTYLE, pointer=ui.POINTER))
        else:
            chosen = candidates[0]
        console.print(f"  [dim]→ {chosen.label}[/dim]")
        resolved.append(chosen)
    return resolved


def _warn(console: Console) -> Callable[[str], None]:
    return lambda msg: console.print(f"[yellow]{msg}[/yellow]")


def _route_from_gmaps(link: str, args: argparse.Namespace, console: Console,
                      profile: str, interactive: bool) -> tuple[Route, str]:
    if urlsplit(link).netloc.lower() in SHORTLINK_HOSTS:
        link = expand_short_link(link)
    g = parse_gmaps_url(link)

    mode = g.mode or profile
    if mode != profile:
        label, tool_label = MODE_LABEL[mode], MODE_LABEL[profile]
        if interactive:
            mode = _q(questionary.select(
                f"Der Link ist eine {label}-Route, aufgerufen ist das "
                f"{tool_label}-Tool. Wonach routen?",
                choices=[Choice(f"{label} (wie im Link)", mode),
                         Choice(f"{tool_label} (wie das Tool)", profile)],
                style=ui.QSTYLE, pointer=ui.POINTER))
        else:
            console.print(f"[yellow]Hinweis: Der Link ist eine {label}-Route "
                          f"— geroutet wird nach dem Link ({label}).[/yellow]")

    waypoints = _resolve(g.waypoints, console, interactive)
    console.print(f"  [bold]Route ({MODE_LABEL[mode]}):[/bold] "
                  + " → ".join(w.name for w in waypoints))
    if interactive and not _q(questionary.confirm(
            "Route so berechnen?", default=True, style=ui.QSTYLE)):
        raise KeyboardInterrupt
    route = route_waypoints(waypoints, mode, warn=_warn(console))
    zone = f"{_short_name(waypoints[0].name)}-{_short_name(waypoints[-1].name)}"
    return route, zone


def _route_from_komoot(link: str, console: Console,
                       interactive: bool) -> tuple[Route, str]:
    tour = fetch_tour(parse_komoot_url(link), page_url=link)
    sport = SPORT_LABEL.get(tour.sport, tour.sport)
    console.print(f"  [bold]Komoot-Tour:[/bold] {tour.name} "
                  f"({sport}, {tour.distance_km:.1f} km, "
                  f"{len(tour.points)} Punkte)")
    if interactive and not _q(questionary.confirm(
            "Diese Tour verwenden?", default=True, style=ui.QSTYLE)):
        raise KeyboardInterrupt
    route = route_from_track(
        tour.points, f"Komoot-Tour „{tour.name}“ ({sport}, "
                     f"{tour.distance_km:.1f} km)")
    return route, tour.name


def _route_from_gpx(path: Path, console: Console) -> tuple[Route, str]:
    track = read_gpx(path)
    console.print(f"  [bold]GPX:[/bold] {track.name} "
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
    args.modus = _q(ui.modus_frage(args.modus))
    args.open = True


def main(profile: str) -> int:
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
    ap.add_argument("--oeffnen", "--open", dest="open", action="store_true",
                    help="Bericht und Karte danach im Browser öffnen")
    ap.add_argument("--ausgabe", "--out", dest="out", type=Path, default=None,
                    metavar="ORDNER",
                    help="Ausgabeverzeichnis (Default: out/<route>)")
    args = ap.parse_args()
    args.profile = profile

    console = Console()
    interactive = False
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
            route, zone = _route_from_gpx(args.gpx, console)
        elif args.link and is_komoot_url(args.link):
            route, zone = _route_from_komoot(args.link, console, interactive)
        elif args.link:
            route, zone = _route_from_gmaps(args.link, args, console,
                                            profile, interactive)
        else:
            names = [args.origin, *args.via, args.destination]
            waypoints = _resolve(names, console, interactive)
            console.print(f"  [bold]Route ({MODE_LABEL[profile]}):[/bold] "
                          + " → ".join(w.name for w in waypoints))
            route = route_waypoints(waypoints, profile, warn=_warn(console))
            zone = (f"{_short_name(waypoints[0].name)}-"
                    f"{_short_name(waypoints[-1].name)}")

        console.print(f"  {', '.join(route.legs)}")
        out_dir = args.out or Path("out") / slug(zone)
        return run_pipeline(
            route, console=console, out_dir=out_dir,
            corridor_km=args.corridor, no_terrain=args.no_terrain,
            open_browser=args.open, zone=zone,
            route_label=route_label, waypoint_icon=icon,
            refresh=args.refresh, modus=args.modus,
            bandbreite=args.bandbreite, ctcss_decode=args.ctcss_decode)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Abgebrochen.[/dim]")
        return 130
    except RouteInputError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    except RuntimeError as e:
        console.print(f"[red]Fehler:[/red] {e}")
        return 1


def main_car() -> int:
    return main("car")


def main_bike() -> int:
    return main("bike")


if __name__ == "__main__":
    sys.exit(main("car"))
