"""Der GUI-Lauf (G4): Formulardaten → Routenaufbau → run_pipeline,
im Hintergrund-Thread, alle Ausgaben/Rückfragen über den GuiMelder.

Der Routenaufbau nutzt dieselben Funktionen wie die Terminal-Tools
(rail.cli._run/_run_link, road.cli._route_from_* — seit G4 Melder-
parametrisiert); nur die dünne Orchestrierung (Namespace aus dem
Formular, Zone/Ausgabeordner) steht hier noch einmal, kommentiert am
jeweiligen CLI-Vorbild. run_pipeline bleibt die eine Quelle der
Wahrheit.
"""
from __future__ import annotations

import argparse
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bmtools.rail.bahn_link import BahnLinkError
from bmtools.road import RouteInputError

from .melder import Ereignis, GuiMelder


def _namespace(daten: dict[str, Any]) -> argparse.Namespace:
    """Formulardaten → argparse-Namespace mit den CLI-Defaults.

    Nicht im Formular abgebildete Flags (Korridor, Gelände, Refresh,
    Bandbreite, CTCSS-Decode, Ausgabeordner) tragen die Defaults der
    Tools; open=False, weil das Fenster die Ergebnisse selbst zeigt."""
    return argparse.Namespace(
        modes=str(daten.get("zuggattung") or "alle"),
        time=None,
        arrive=bool(daten.get("ankunft")),
        direct=bool(daten.get("direkt")),
        corridor=None, no_terrain=False, open=False, refresh=False,
        modus=str(daten.get("modus") or "beide"),
        bandbreite="12.5", ctcss_decode=False,
        out=None, straight_line=False)


def _via_liste(daten: dict[str, Any]) -> list[str]:
    return [v.strip() for v in str(daten.get("via", "")).split(",")
            if v.strip()]


class Lauf:
    """Ein laufender (oder beendeter) Pipeline-Lauf des Fensters."""

    def __init__(self, sende: Callable[[Ereignis], None]) -> None:
        self._sende = sende
        self._abbruch = threading.Event()
        self.melder = GuiMelder(sende, self._abbruch)
        self._thread: threading.Thread | None = None

    def laeuft(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def starten(self, tool: str, daten: dict[str, Any]) -> None:
        self._thread = threading.Thread(
            target=self._lauf, args=(tool, daten), daemon=True,
            name=f"bm-lauf-{tool}")
        self._thread.start()

    def abbrechen(self) -> None:
        self._abbruch.set()

    # ------------------------------------------------------------------

    def _lauf(self, tool: str, daten: dict[str, Any]) -> None:
        code = 1
        try:
            if tool == "bahn":
                code = self._bahn(daten)
            else:
                code = self._strasse(tool, daten)
        except KeyboardInterrupt:
            code = 130
            self._sende({"typ": "text", "text": "Abgebrochen."})
        except (BahnLinkError, RouteInputError) as e:
            self._sende({"typ": "fehler", "text": str(e)})
        except RuntimeError as e:
            self._sende({"typ": "fehler", "text": str(e)})
        except Exception as e:  # Schutznetz: das Fenster braucht IMMER
            # ein fertig-Ereignis, sonst bleibt es im Lauf-Zustand hängen
            self._sende({"typ": "fehler",
                         "text": f"Unerwarteter Fehler: {e!r}"})
        finally:
            self._sende({"typ": "fertig", "code": code})

    def _bahn(self, daten: dict[str, Any]) -> int:
        # Vorbild: rail.cli.main() — Link-Weg bzw. Stationsauflösung
        from bmtools.rail import cli as rail_cli
        from bmtools.rail.route import NoItineraryError, RoutePlanner

        args = _namespace(daten)
        zeit = str(daten.get("zeit", "")).strip()
        if zeit:
            args.time = rail_cli._parse_time(zeit)
        m = self.melder
        planner = RoutePlanner()
        link = str(daten.get("link", "")).strip()
        try:
            if link:
                return rail_cli._run_link(link, args, m, planner,
                                          interactive=True,
                                          modus_fragen=False)
            names = [str(daten["von"]), *_via_liste(daten),
                     str(daten["nach"])]
            stations = rail_cli._resolve_stations(planner, names, m,
                                                  interactive=True)
            return rail_cli._run(stations, args, m, planner,
                                 interactive=True, modus_fragen=False)
        except NoItineraryError as e:
            self._sende({"typ": "fehler",
                         "text": f"{e} — Tipp: Zuggattung »alle« wählen, "
                                 f"ohne »nur Direktverbindungen«, oder "
                                 f"andere Uhrzeit."})
            return 1

    def _strasse(self, tool: str, daten: dict[str, Any]) -> int:
        # Vorbild: road.cli.main() — GPX/Komoot/Google-Link/Start-Ziel
        from bmtools.road import cli as road_cli
        from bmtools.road.komoot import is_komoot_url
        from bmtools.road.routing import MODE_LABEL, route_waypoints
        from bmtools.routelib.pipeline import run_pipeline, slug

        profile = {"auto": "car", "rad": "bike"}[tool]
        _, route_label, icon, _ = road_cli.PROFILES[profile]
        args = _namespace(daten)
        m = self.melder
        link = str(daten.get("link", "")).strip()
        gpx = str(daten.get("gpx", "")).strip()

        if gpx:
            route, zone = road_cli._route_from_gpx(Path(gpx), m)
        elif link and is_komoot_url(link):
            route, zone = road_cli._route_from_komoot(link, m,
                                                      interactive=True)
        elif link:
            route, zone = road_cli._route_from_gmaps(link, args, m,
                                                     profile,
                                                     interactive=True)
        else:
            names = [str(daten["von"]), *_via_liste(daten),
                     str(daten["nach"])]
            waypoints = road_cli._resolve(names, m, interactive=True)
            m.text(f"  [bold]Route ({MODE_LABEL[profile]}):[/bold] "
                   + " → ".join(w.name for w in waypoints))
            route = route_waypoints(waypoints, profile,
                                    warn=road_cli._warn(m))
            zone = (f"{road_cli._short_name(waypoints[0].name)}-"
                    f"{road_cli._short_name(waypoints[-1].name)}")

        m.text(f"  {', '.join(route.legs)}")
        out_dir = Path("out") / slug(zone)
        return run_pipeline(
            route, melder=m, out_dir=out_dir, corridor_km=args.corridor,
            no_terrain=args.no_terrain, open_browser=False, zone=zone,
            route_label=route_label, waypoint_icon=icon,
            modus=args.modus, bandbreite=args.bandbreite,
            ctcss_decode=args.ctcss_decode, interactive=False)
