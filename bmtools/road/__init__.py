"""bm-car / bm-bike: DMR-Relais entlang einer Auto- oder Radroute.

Routenquellen: Google-Maps-Link (Wegpunkte -> OSRM-Routing),
Komoot-Tour-Link (fertige Geometrie) oder GPX-Datei.
"""


class RouteInputError(RuntimeError):
    """Routen-Eingabe (Link/Datei) unbrauchbar — Meldung ist nutzerfertig."""
