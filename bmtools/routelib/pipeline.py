"""Gemeinsamer Ablauf aller Tools ab fertiger Route: Erreichbarkeit
(Geländemodell), Talkgroup-Anreicherung, Tabelle/CSV, HTML-Bericht,
Karte und AnyTone-Export.

Hierher aus bmtools/rail/cli.py extrahiert (R4); die Konsolen-Texte
sind bewusst unverändert.
"""
from __future__ import annotations

import re
from pathlib import Path

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

from bmtools import ui
from bmtools.bm_api import BrandmeisterClient, DeviceProfile, TalkgroupSub
from bmtools.fm_api import DL3ELClient, FmRepeater, band_label

from .codeplug.anytone import write_anytone
from .codeplug.chirp import write_chirp
from .corridor import find_in_corridor
from .coverage import estimate_coverage
from .mapview import write_map
from .model import RepeaterLike, Route
from .oeffnen import system_oeffnen
from .report import FUNK_LABEL, RepeaterResult, print_table, write_csv
from .report_html import write_html_report
from .terrain import TerrainError, TerrainModel

_UMLAUTE: dict[str, str | int | None] = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def slug(text: str) -> str:
    text = text.lower().translate(str.maketrans(_UMLAUTE))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _with_local_tg(profile: DeviceProfile, simplex: bool) -> DeviceProfile:
    """TG9 'Lokal' ist auf jedem Relais implizit verfügbar, fehlt aber in
    der API — hier als Standard-Eintrag ergänzen (TS2; Simplex: Slot 0).

    Slot-0-Einträge auf Duplex-Relais werden verworfen: BM nutzt Slot 0
    nur für Geräte ohne Timeslots; auf einem Duplex-Relais ist das eine
    Miskonfiguration des Sysops (Nutzerentscheidung 2026-07-13, Beispiel
    DB0TU TG 26231)."""
    if not simplex:
        profile.subscriptions = [s for s in profile.subscriptions
                                 if s.slot != 0]
    if not any(s.talkgroup == 9 for s in profile.subscriptions):
        profile.subscriptions.append(
            TalkgroupSub(9, 0 if simplex else 2, "implicit", "Lokal"))
        profile.subscriptions.sort(key=lambda s: (s.slot, s.talkgroup))
    return profile


def _band_2m_70cm(d: RepeaterLike) -> bool:
    """Nur 2-m- und 70-cm-Relais sind relevant (Festlegung 2026-07-15,
    Dualband-Funkgeräte) — 10-m-/6-m-/23-cm-Einträge beider Quellen
    werden aussortiert."""
    return d.tx_mhz is not None and band_label(d.tx_mhz) in ("2m", "70cm")


def run_pipeline(route: Route, *, console: Console, out_dir: Path,
                 corridor_km: float | None, no_terrain: bool,
                 open_browser: bool, zone: str,
                 route_label: str = "Strecke",
                 waypoint_icon: str = "flag",
                 refresh: bool = False,
                 modus: str = "beide",
                 bandbreite: str = "12.5",
                 ctcss_decode: bool = False,
                 interactive: bool = False) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_note = " [dim](Cache wird ignoriert)[/dim]" if refresh else ""
    client: BrandmeisterClient | None = None
    repeaters: list[RepeaterLike] = []
    quellen_note = []
    if modus != "fm":
        client = BrandmeisterClient(refresh=refresh)
        console.print(f"[bold]Lade Brandmeister-Geräteliste …[/bold]{cache_note}")
        repeaters += [d for d in client.repeaters() if _band_2m_70cm(d)]
        quellen_note.append(f"{len(repeaters)} DMR-Repeater (2 m/70 cm) "
                            "im Netz")
    if modus != "dmr":
        console.print("[bold]Lade FM-Relais entlang der Route "
                      f"(relaislisten.darc.de) …[/bold]{cache_note}")
        with ui.fortschritt(console) as fm_p:
            # Kurz halten: die Balken-Zeile muss samt X/Y-Zähler in
            # 80 Zeichen passen
            fm_task = fm_p.add_task("Stützpunkte abfragen (alle 50 km, "
                                    "gedrosselt)", total=None)

            def fm_progress(fertig: int, gesamt: int) -> None:
                fm_p.update(fm_task, completed=fertig, total=gesamt)

            fm_relais = [r for r in DL3ELClient(refresh=refresh)
                         .repeaters_along(route.points, progress=fm_progress)
                         if _band_2m_70cm(r)]
        repeaters += fm_relais
        quellen_note.append(f"{len(fm_relais)} FM-Relais (2 m/70 cm) "
                            "im Routenumfeld")

    # Auswahlkriterium ist die rechnerische Erreichbarkeit von der Strecke
    # (Sichtkontakt zu >=1 Streckenpunkt), nicht ein fester Abstand.
    terrain = None if no_terrain else TerrainModel()
    with ui.fortschritt(console) as cov_p:
        # Kachel-Balken bleibt unsichtbar, bis wirklich Kacheln fehlen
        # (warmer Cache: nur der Rechenbalken). Update aus Threads ist ok,
        # rich.progress ist threadsicher.
        kacheln_task = cov_p.add_task("Höhenkacheln laden", total=None,
                                      visible=False)
        punkte_task = cov_p.add_task(
            "Erreichbarkeit berechnen (Geländemodell)" if terrain else
            "Erreichbarkeit berechnen (Horizontmodell)", total=None)

        def tile_progress(fertig: int, gesamt: int) -> None:
            cov_p.update(kacheln_task, completed=fertig, total=gesamt,
                         visible=True)

        def sample_progress(fertig: int, gesamt: int) -> None:
            cov_p.update(punkte_task, completed=fertig, total=gesamt)

        try:
            coverage = estimate_coverage(route.points, repeaters, terrain,
                                         tile_progress=tile_progress,
                                         sample_progress=sample_progress)
        except TerrainError as e:
            console.print(f"[yellow]Höhendaten nicht verfügbar ({e}) — "
                          f"Fallback auf Horizontmodell.[/yellow]")
            terrain = None
            cov_p.update(kacheln_task, visible=False)
            cov_p.update(punkte_task, completed=0,
                         description="Erreichbarkeit berechnen "
                                     "(Horizontmodell)")
            coverage = estimate_coverage(route.points, repeaters, None,
                                         sample_progress=sample_progress)

    # Konsistenz-Zusage: Jedes Relais, das irgendwo (Karte, Abschnitts-
    # tabelle) als erreichbar oder grenzwertig auftaucht, bekommt auch
    # einen vollen Eintrag — Grenzbereichs-Relais markiert, kein
    # implizites Abstandslimit (nur --corridor begrenzt).
    listed_ids = coverage.reachable_ids | coverage.marginal_ids
    reachable = [d for d in repeaters if d.id in listed_ids]
    hits = find_in_corridor(reachable, route.points, corridor_km)
    marginal_count = sum(1 for h in hits
                         if h.device.id not in coverage.reachable_ids)
    limit_note = f" (Limit {corridor_km:g} km Streckenabstand)" if corridor_km else ""
    marginal_note = (f", davon {marginal_count} nur im Grenzbereich"
                     if marginal_count else "")
    console.print(f"  {', '.join(quellen_note)}, "
                  f"[bold]{len(hits)}[/bold] von der Strecke aus rechnerisch "
                  f"erreichbar{limit_note}{marginal_note}")
    if not hits:
        console.print("[red]Kein Relais von der Strecke aus erreichbar.[/red]")
        return 1

    # Talkgroup-Profile sind ein reines DMR-Konzept — FM-Relais bekommen
    # profile=None und überspringen die (gedrosselten) Profilabfragen.
    dmr_hits = [h for h in hits if not isinstance(h.device, FmRepeater)]
    profiles: dict[int, DeviceProfile] = {}
    if dmr_hits:
        assert client is not None  # DMR-Treffer gibt es nur mit BM-Client
        profiles = {
            h.device.id: _with_local_tg(
                client.profile(h.device.id),
                simplex=h.device.tx_mhz == h.device.rx_mhz)
            for h in track(dmr_hits, description="Talkgroup-Profile laden …")
        }
    results = [
        RepeaterResult(
            hit=h,
            profile=profiles.get(h.device.id),
            marginal_only=h.device.id not in coverage.reachable_ids,
            modus="fm" if isinstance(h.device, FmRepeater) else "dmr")
        for h in hits
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
            f"der Strecke ohne {FUNK_LABEL[modus]} "
            f"({coverage.uncovered_km:.0f} von "
            f"{coverage.total_km:.0f} km; Horizontmodell, ohne Gelände)")

    tg_names = client.talkgroup_names() if client else {}
    csv_path = out_dir / "relais.csv"
    html_path = out_dir / "bericht.html"
    map_path = out_dir / "karte.html"
    write_csv(results, csv_path)
    write_html_report(results, route, html_path, tg_names, coverage,
                      modus=modus)
    with console.status("Karte erzeugen (inkl. Relais-Sichtfelder) …"):
        # Die Sichtfelder laden weitere Höhenkacheln nach — reißt das Netz
        # dabei ab, kommt die Karte ohne Sichtfelder statt gar nicht.
        try:
            write_map(results, route, map_path, coverage,
                      terrain if coverage.terrain_used else None,
                      route_label=route_label, waypoint_icon=waypoint_icon)
        except TerrainError as e:
            console.print(f"[yellow]Höhendaten abgebrochen ({e}) — "
                          f"Karte ohne Relais-Sichtfelder.[/yellow]")
            write_map(results, route, map_path, coverage, None,
                      route_label=route_label, waypoint_icon=waypoint_icon)
    # Codeplug: digitale und analoge Kanäle in derselben Zone; die
    # FM-Kanäle zusätzlich als generisches CHIRP-CSV
    write_anytone(results, out_dir / "anytone", zone, tg_names,
                  bandbreite=bandbreite, ctcss_decode=ctcss_decode)
    chirp_path = write_chirp(results, out_dir / "chirp.csv",
                             bandbreite=bandbreite, ctcss_decode=ctcss_decode)

    lines = [
        f"[green]Fertig.[/green] Ausgaben in [bold]{out_dir}/[/bold]",
        "  bericht.html   Kanaltabellen für manuelle CPS-Eingabe",
        "  karte.html     interaktive Streckenkarte",
        "  relais.csv     Rohdaten (Semikolon-getrennt)",
        "  anytone/       Channel/TalkGroups/Zone-CSV "
        "[yellow](Format vorläufig = D878UV)[/yellow]",
    ]
    if chirp_path:
        lines.append("  chirp.csv      CHIRP-Import (nur die FM-Kanäle)")
    console.print(Panel.fit("\n".join(lines), border_style="green"))

    if open_browser:
        # Nicht webbrowser.open(): siehe oeffnen.py (Windows-Beta-Befund)
        system_oeffnen(html_path)
        system_oeffnen(map_path)
    # Beta-Wunsch 2026-07-17: Ausgabeordner (Codeplug-CSVs!) direkt im
    # Dateimanager öffnen können. Ctrl-C/ESC zählt als Nein.
    if interactive and questionary.confirm(
            "Ausgabeordner im Dateimanager öffnen?", default=False,
            style=ui.QSTYLE).ask():
        system_oeffnen(out_dir)
    return 0
