"""Gemeinsamer Ablauf aller Tools ab fertiger Route: Erreichbarkeit
(Geländemodell), Talkgroup-Anreicherung, Tabelle/CSV, HTML-Bericht,
Karte und AnyTone-Export.

Hierher aus bmtools/rail/cli.py extrahiert (R4); die Konsolen-Texte
sind bewusst unverändert. Seit G2 (GUI-UMBAU.md) laufen alle Ausgaben
und Rückfragen über einen Melder (melden.py) — Default ist der
TerminalMelder mit exakt dem bisherigen rich-Verhalten, die GUI
injiziert ab G4 ihren eigenen.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from bmtools.bm_api import BrandmeisterClient, DeviceProfile, TalkgroupSub
from bmtools.fm_api import DL3ELClient, FmRepeater, band_label

from .codeplug.anytone import write_anytone
from .codeplug.chirp import write_chirp
from .corridor import find_in_corridor
from .coverage import BBOX_BUFFER_KM, estimate_coverage, suchradius_hinweis
from .mapview import karten_daten, write_map
from .melden import Melder, TerminalMelder
from .model import RepeaterLike, Route
from .oeffnen import system_oeffnen_still
from .report import (
    FUNK_LABEL,
    RepeaterResult,
    km_empfangsbereiche,
    relais_daten,
    write_csv,
)
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


def run_pipeline(route: Route, *, console: Console | None = None,
                 melder: Melder | None = None,
                 out_dir: Path,
                 corridor_km: float | None, no_terrain: bool,
                 suchradius_km: float | None = None,
                 open_browser: bool, zone: str,
                 route_label: str = "Strecke",
                 waypoint_icon: str = "flag",
                 refresh: bool = False,
                 modus: str = "beide",
                 bandbreite: str = "12.5",
                 ctcss_decode: bool = False,
                 pdf: bool = False,
                 interactive: bool = False) -> int:
    """melder=None: TerminalMelder auf der übergebenen Konsole (bzw.
    stdout) — das bisherige Verhalten. Die GUI übergibt ihren eigenen.

    suchradius_km: Vorfilter-Radius um die Strecke für die
    Erreichbarkeitsrechnung; None oder <=0 heißt Default (60 km)."""
    m: Melder = melder if melder is not None else TerminalMelder(console)
    if suchradius_km is None or suchradius_km <= 0:
        suchradius_km = BBOX_BUFFER_KM
    # Auffälliger Radius: einmal deutlich sagen, womit gerechnet wird —
    # gerade bei Beta-Testern muss das Programm selbst reden.
    if (hinweis := suchradius_hinweis(suchradius_km)) is not None:
        m.text(f"[yellow]{hinweis}[/yellow]")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Ab hier absolut: Der gemeldete Pfad ist das, was der Nutzer sucht
    # (»Ergebnisse in out/xyz/« half niemandem, der nicht weiß, was sein
    # Arbeitsverzeichnis ist — Beta-Befund 2026-07-26), und der
    # Ausgabeordner geht so absolut an den Dateimanager (s. oeffnen.py).
    out_dir = out_dir.resolve()

    # Grobe Schritte für den Gesamt-Balken der GUI (Melder.schritt,
    # Terminal: No-op). Übersprungene Schritte (keine DMR-Treffer)
    # lassen den Balken einfach vorspringen.
    phasen: list[str] = []
    if modus != "fm":
        phasen.append("Brandmeister-Geräteliste laden")
    if modus != "dmr":
        phasen.append("FM-Relais laden")
    phasen.append("Erreichbarkeit berechnen")
    if modus != "fm":
        phasen.append("Talkgroup-Profile laden")
    phasen += ["Bericht und Karte erzeugen", "Codeplug schreiben"]

    def schritt(text: str) -> None:
        m.schritt(phasen.index(text) + 1, len(phasen), text)

    cache_note = " [dim](Cache wird ignoriert)[/dim]" if refresh else ""
    client: BrandmeisterClient | None = None
    repeaters: list[RepeaterLike] = []
    quellen_note = []
    if modus != "fm":
        schritt("Brandmeister-Geräteliste laden")
        client = BrandmeisterClient(refresh=refresh)
        m.text(f"[bold]Lade Brandmeister-Geräteliste …[/bold]{cache_note}")
        repeaters += [d for d in client.repeaters() if _band_2m_70cm(d)]
        quellen_note.append(f"{len(repeaters)} DMR-Repeater (2 m/70 cm) "
                            "im Netz")
    if modus != "dmr":
        schritt("FM-Relais laden")
        m.text("[bold]Lade FM-Relais entlang der Route "
               f"(relaislisten.darc.de) …[/bold]{cache_note}")
        with m.balken() as fm_b:
            # Kurz halten: die Balken-Zeile muss samt X/Y-Zähler in
            # 80 Zeichen passen
            fm_task = fm_b.task("Stützpunkte abfragen (alle 50 km, "
                                "gedrosselt)")

            def fm_progress(fertig: int, gesamt: int) -> None:
                fm_b.update(fm_task, fertig=fertig, gesamt=gesamt)

            fm_relais = [r for r in DL3ELClient(refresh=refresh)
                         .repeaters_along(route.points, progress=fm_progress)
                         if _band_2m_70cm(r)]
        repeaters += fm_relais
        quellen_note.append(f"{len(fm_relais)} FM-Relais (2 m/70 cm) "
                            "im Routenumfeld")

    # Auswahlkriterium ist die rechnerische Erreichbarkeit von der Strecke
    # (Sichtkontakt zu >=1 Streckenpunkt), nicht ein fester Abstand.
    schritt("Erreichbarkeit berechnen")
    terrain = None if no_terrain else TerrainModel()
    with m.balken() as cov_b:
        # Kachel-Balken bleibt unsichtbar, bis wirklich Kacheln fehlen
        # (warmer Cache: nur der Rechenbalken). Update aus Threads ist ok,
        # Balken.update ist laut Schnittstelle threadsicher.
        kacheln_task = cov_b.task("Höhenkacheln laden", sichtbar=False)
        punkte_task = cov_b.task(
            "Erreichbarkeit berechnen (Geländemodell)" if terrain else
            "Erreichbarkeit berechnen (Horizontmodell)")

        def tile_progress(fertig: int, gesamt: int) -> None:
            cov_b.update(kacheln_task, fertig=fertig, gesamt=gesamt,
                         sichtbar=True)

        def sample_progress(fertig: int, gesamt: int) -> None:
            cov_b.update(punkte_task, fertig=fertig, gesamt=gesamt)

        try:
            coverage = estimate_coverage(route.points, repeaters, terrain,
                                         suchradius_km=suchradius_km,
                                         tile_progress=tile_progress,
                                         sample_progress=sample_progress)
        except TerrainError as e:
            m.text(f"[yellow]Höhendaten nicht verfügbar ({e}) — "
                   f"Fallback auf Horizontmodell.[/yellow]")
            terrain = None
            cov_b.update(kacheln_task, sichtbar=False)
            cov_b.update(punkte_task, fertig=0,
                         beschreibung="Erreichbarkeit berechnen "
                                      "(Horizontmodell)")
            coverage = estimate_coverage(route.points, repeaters, None,
                                         suchradius_km=suchradius_km,
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
    m.text(f"  {', '.join(quellen_note)}, "
           f"[bold]{len(hits)}[/bold] von der Strecke aus rechnerisch "
           f"erreichbar{limit_note}{marginal_note}")
    if not hits:
        m.text("[red]Kein Relais von der Strecke aus erreichbar.[/red]")
        return 1

    # Talkgroup-Profile sind ein reines DMR-Konzept — FM-Relais bekommen
    # profile=None und überspringen die (gedrosselten) Profilabfragen.
    dmr_hits = [h for h in hits if not isinstance(h.device, FmRepeater)]
    profiles: dict[int, DeviceProfile] = {}
    if dmr_hits:
        assert client is not None  # DMR-Treffer gibt es nur mit BM-Client
        schritt("Talkgroup-Profile laden")
        profiles = {
            h.device.id: _with_local_tg(
                client.profile(h.device.id),
                simplex=h.device.tx_mhz == h.device.rx_mhz)
            for h in m.spur(dmr_hits, "Talkgroup-Profile laden …")
        }
    results = [
        RepeaterResult(
            hit=h,
            profile=profiles.get(h.device.id),
            marginal_only=h.device.id not in coverage.reachable_ids,
            modus="fm" if isinstance(h.device, FmRepeater) else "dmr")
        for h in hits
    ]

    m.tabelle(results)

    if coverage.terrain_used:
        m.text(
            f"  Abdeckung (Geländemodell): freie Sicht "
            f"[bold]{coverage.pct(coverage.covered_km):.0f} %[/bold], "
            f"Grenzbereich {coverage.pct(coverage.marginal_km):.0f} %, "
            f"Schatten [bold]{coverage.uncovered_pct:.0f} %[/bold] "
            f"({coverage.uncovered_km:.0f} von {coverage.total_km:.0f} km)")
    else:
        m.text(
            f"  Abdeckungsschätzung: ca. [bold]{coverage.uncovered_pct:.0f} %[/bold] "
            f"der Strecke ohne {FUNK_LABEL[modus]} "
            f"({coverage.uncovered_km:.0f} von "
            f"{coverage.total_km:.0f} km; Horizontmodell, ohne Gelände)")

    schritt("Bericht und Karte erzeugen")
    tg_names = client.talkgroup_names() if client else {}
    csv_path = out_dir / "relais.csv"
    html_path = out_dir / "bericht.html"
    map_path = out_dir / "karte.html"
    write_csv(results, csv_path)
    write_html_report(results, route, html_path, tg_names, coverage,
                      modus=modus)
    # Die Sichtfelder laden weitere Höhenkacheln nach — reißt das Netz
    # dabei ab, kommt die Karte ohne Sichtfelder statt gar nicht.
    overlay = None
    sichtfeld_terrain = terrain if coverage.terrain_used else None
    if sichtfeld_terrain is not None:
        with m.balken() as map_b:
            map_kacheln = map_b.task("Höhenkacheln laden (Sichtfelder)",
                                     sichtbar=False)
            felder_task = map_b.task("Karte erzeugen (Relais-Sichtfelder)")

            def map_tile_progress(fertig: int, gesamt: int) -> None:
                map_b.update(map_kacheln, fertig=fertig, gesamt=gesamt,
                             sichtbar=True)

            def felder_progress(fertig: int, gesamt: int) -> None:
                map_b.update(felder_task, fertig=fertig, gesamt=gesamt)

            try:
                overlay = write_map(
                    results, route, map_path, coverage, sichtfeld_terrain,
                    route_label=route_label, waypoint_icon=waypoint_icon,
                    tile_progress=map_tile_progress,
                    viewshed_progress=felder_progress)
            except TerrainError as e:
                m.text(f"[yellow]Höhendaten abgebrochen ({e}) — "
                       f"Karte ohne Relais-Sichtfelder.[/yellow]")
                sichtfeld_terrain = None
    if sichtfeld_terrain is None:
        with m.status("Karte erzeugen …"):
            overlay = write_map(results, route, map_path, coverage, None,
                                route_label=route_label,
                                waypoint_icon=waypoint_icon)
    # Dieselben Inhalte als strukturierte Daten für GUI und PDF
    # (U4/U5/U8): Karte (Overlay wird weiterverwendet statt doppelt
    # gerechnet), Kennzahlen für Top-Bar/Deckblatt, Relais-Zeilen für
    # DataGrid und PDF-Tabelle
    daten = {
        "karte": karten_daten(results, route, coverage, overlay,
                              route_label=route_label,
                              waypoint_icon=waypoint_icon),
        "kennzahlen": {
            "distanz_km": round(coverage.total_km),
            "terrain": coverage.terrain_used,
            "sicht_pct": round(coverage.pct(coverage.covered_km)),
            "grenz_pct": round(coverage.pct(coverage.marginal_km)),
            "schatten_pct": round(coverage.uncovered_pct),
            "anzahl": len(results),
            # Datenstand: Zeitpunkt des Laufs (BM/FM-Daten frisch bzw.
            # aus dem TTL-Cache) — PDF-Fußzeile und Statusleiste
            "stand": datetime.now().strftime("%d.%m.%Y"),
        },
        "relais": relais_daten(
            results, tg_names,
            km_bereiche=km_empfangsbereiche(coverage.samples)),
    }
    m.ergebnis_daten(daten)
    # Codeplug: digitale und analoge Kanäle in derselben Zone; die
    # FM-Kanäle zusätzlich als generisches CHIRP-CSV
    schritt("Codeplug schreiben")
    write_anytone(results, out_dir / "anytone", zone, tg_names,
                  bandbreite=bandbreite, ctcss_decode=ctcss_decode)
    chirp_path = write_chirp(results, out_dir / "chirp.csv",
                             bandbreite=bandbreite, ctcss_decode=ctcss_decode)

    if pdf:
        # Nachgelagert auf denselben Ergebnisdaten (§4/§5) — nur auf
        # Wunsch (--pdf bzw. GUI-Button), kein Automatik-Export
        m.text("[bold]Erzeuge PDF-Bericht …[/bold]")
        from .report_pdf import write_pdf
        with m.balken() as pdf_b:
            pdf_kacheln = pdf_b.task("Kartenkacheln laden (PDF)",
                                     sichtbar=False)

            def pdf_tiles(fertig: int, gesamt: int) -> None:
                pdf_b.update(pdf_kacheln, fertig=fertig, gesamt=gesamt,
                             sichtbar=True)

            write_pdf(daten, out_dir / "bericht.pdf",
                      tile_progress=pdf_tiles)

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
    if pdf:
        lines.append("  bericht.pdf    Druckbericht "
                     "(Deckblatt, Karte, Relais-Tabelle)")
    m.ergebnis(out_dir, html_path, map_path)
    m.erfolg(lines)

    # Öffnen ist Komfort — scheitert es, sagen wir das und machen weiter;
    # die Dateien liegen ja auf der Platte (und der Pfad steht oben).
    def oeffnen(ziel: Path) -> None:
        # Nicht webbrowser.open(): siehe oeffnen.py (Windows-Beta-Befund)
        fehler = system_oeffnen_still(ziel)
        if fehler is not None:
            m.text(f"[yellow]{ziel} ließ sich nicht öffnen "
                   f"({'; '.join(fehler.versuche)}).[/yellow]")

    if open_browser:
        oeffnen(html_path)
        oeffnen(map_path)
    # Beta-Wunsch 2026-07-17: Ausgabeordner (Codeplug-CSVs!) direkt im
    # Dateimanager öffnen können. Ctrl-C/ESC zählt als Nein.
    if interactive and m.ja_nein("Ausgabeordner im Dateimanager öffnen?"):
        oeffnen(out_dir)
    return 0
