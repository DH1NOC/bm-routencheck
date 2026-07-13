"""Gemeinsamer Ablauf aller Tools ab fertiger Route: Erreichbarkeit
(Geländemodell), Talkgroup-Anreicherung, Tabelle/CSV, HTML-Bericht,
Karte und AnyTone-Export.

Hierher aus bmtools/rail/cli.py extrahiert (R4); die Konsolen-Texte
sind bewusst unverändert.
"""
from __future__ import annotations

import re
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import track

from bmtools.bm_api import BrandmeisterClient, DeviceProfile, TalkgroupSub
from .codeplug.anytone import write_anytone
from .corridor import find_in_corridor
from .coverage import BBOX_BUFFER_KM, estimate_coverage
from .mapview import write_map
from .model import Route
from .report import RepeaterResult, print_table, write_csv
from .report_html import write_html_report
from .terrain import TerrainError, TerrainModel


def slug(text: str) -> str:
    text = text.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _with_local_tg(profile: DeviceProfile, simplex: bool) -> DeviceProfile:
    """TG9 'Lokal' ist auf jedem Relais implizit verfügbar, fehlt aber in
    der API — hier als Standard-Eintrag ergänzen (TS2; Simplex: Slot 0)."""
    if not any(s.talkgroup == 9 for s in profile.subscriptions):
        profile.subscriptions.append(
            TalkgroupSub(9, 0 if simplex else 2, "implicit", "Lokal"))
        profile.subscriptions.sort(key=lambda s: (s.slot, s.talkgroup))
    return profile


def run_pipeline(route: Route, *, console: Console, out_dir: Path,
                 corridor_km: float | None, no_terrain: bool,
                 open_browser: bool, zone: str,
                 route_label: str = "Strecke",
                 waypoint_icon: str = "flag") -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    client = BrandmeisterClient()
    console.print("[bold]Lade Brandmeister-Geräteliste …[/bold]")
    repeaters = client.repeaters()

    # Auswahlkriterium ist die rechnerische Erreichbarkeit von der Strecke
    # (Sichtkontakt zu >=1 Streckenpunkt), nicht ein fester Abstand.
    terrain = None if no_terrain else TerrainModel()
    with console.status("Erreichbarkeit berechnen (Geländemodell; lädt ggf. "
                        "Höhenkacheln) …" if terrain else
                        "Erreichbarkeit berechnen (Horizontmodell) …"):
        try:
            coverage = estimate_coverage(route.points, repeaters, terrain)
        except TerrainError as e:
            console.print(f"[yellow]Höhendaten nicht verfügbar ({e}) — "
                          f"Fallback auf Horizontmodell.[/yellow]")
            terrain = None
            coverage = estimate_coverage(route.points, repeaters, None)

    reachable = [d for d in repeaters if d.id in coverage.reachable_ids]
    max_dist = corridor_km if corridor_km else BBOX_BUFFER_KM
    hits = find_in_corridor(reachable, route.points, max_dist)
    limit_note = f" (Limit {corridor_km:g} km Streckenabstand)" if corridor_km else ""
    console.print(f"  {len(repeaters)} Repeater im Netz, "
                  f"[bold]{len(hits)}[/bold] von der Strecke aus rechnerisch "
                  f"erreichbar{limit_note}")
    if not hits:
        console.print("[red]Kein Relais von der Strecke aus erreichbar.[/red]")
        return 1

    results = [
        RepeaterResult(hit=h, profile=_with_local_tg(
            client.profile(h.device.id),
            simplex=h.device.tx_mhz == h.device.rx_mhz))
        for h in track(hits, description="Talkgroup-Profile laden …")
    ]

    print_table(results, console)

    if coverage.terrain_used:
        console.print(
            f"  Abdeckung (Geländemodell): freie Sicht "
            f"[bold]{coverage.pct(coverage.covered_km):.0f} %[/bold], "
            f"Grenzbereich {coverage.pct(coverage.marginal_km):.0f} %, "
            f"Schatten [bold]{coverage.uncovered_pct:.0f} %[/bold] "
            f"({coverage.uncovered_km:.0f} von {coverage.total_km:.0f} km)")
    else:
        console.print(
            f"  Abdeckungsschätzung: ca. [bold]{coverage.uncovered_pct:.0f} %[/bold] "
            f"der Strecke ohne DMR ({coverage.uncovered_km:.0f} von "
            f"{coverage.total_km:.0f} km; Horizontmodell, ohne Gelände)")

    tg_names = client.talkgroup_names()
    csv_path = out_dir / "relais.csv"
    html_path = out_dir / "bericht.html"
    map_path = out_dir / "karte.html"
    write_csv(results, csv_path)
    write_html_report(results, route, html_path, tg_names, coverage)
    with console.status("Karte erzeugen (inkl. Relais-Sichtfelder) …"):
        write_map(results, route, max_dist, map_path, coverage,
                  terrain if coverage.terrain_used else None,
                  route_label=route_label, waypoint_icon=waypoint_icon)
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

    if open_browser:
        webbrowser.open(html_path.resolve().as_uri())
        webbrowser.open(map_path.resolve().as_uri())
    return 0
