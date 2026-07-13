"""Tests bahn.de-Verbindungslink-Parser (vbid + HAFAS-Recon).

Der Recon-String ist ein echtes, auf zwei Abschnitte gekürztes Fixture
(am 2026-07-13 über die vbid-API geholt; Verbindung Lindau -> Hamburg
am 17.08.2026, letzter Abschnitt mit Ankunft nach Mitternacht).
"""
from datetime import datetime

import pytest

from bmtools.rail.bahn_link import (BahnLinkError, TZ, extract_vbid,
                                    is_bahn_url, parse_recon)

VBID = "d406032b-b663-4266-952d-f8e117dd3e41"
URL = f"https://www.bahn.de/buchung/start?vbid={VBID}"

RECON = (
    "¶HKI¶T$A=1@O=Lindau-Insel@X=9680465@Y=47544343@L=8000230@a=128@"
    "$A=1@O=Augsburg Hbf@X=10885568@Y=48365444@L=8000013@a=128@"
    "$202608170657$202608170915$             3285$$1$$$$$$"
    "§T$A=1@O=Köln Hbf@X=6958730@Y=50943029@L=8000207@a=128@"
    "$A=1@O=Hamburg Hbf@X=10006909@Y=53552733@L=8002549@a=128@"
    "$202608172046$202608180126$ICE           514$$1$$$$$$"
    "¶KC¶#VE#2#CF#100#"
)


def test_extract_vbid_aus_url():
    assert extract_vbid(URL) == VBID
    assert extract_vbid(f"https://int.bahn.de/de/buchung/start?vbid={VBID}&x=1") == VBID


def test_extract_vbid_nackte_uuid():
    assert extract_vbid(VBID.upper()) == VBID


def test_extract_vbid_ohne_id():
    with pytest.raises(BahnLinkError, match="vbid"):
        extract_vbid("https://www.bahn.de/buchung/fahrplan/suche")


def test_is_bahn_url():
    assert is_bahn_url(URL)
    assert not is_bahn_url("https://www.komoot.com/tour/123")


def test_parse_recon_abschnitte():
    legs = parse_recon(RECON)
    assert len(legs) == 2

    erster = legs[0]
    assert erster.frm.name == "Lindau-Insel"
    assert erster.to.name == "Augsburg Hbf"
    # X = Länge, Y = Breite, jeweils Mikrograd
    assert (erster.frm.lat, erster.frm.lon) == (47.544343, 9.680465)
    assert erster.dep == datetime(2026, 8, 17, 6, 57, tzinfo=TZ)
    assert erster.arr == datetime(2026, 8, 17, 9, 15, tzinfo=TZ)
    assert erster.train == "3285"  # Füllraum entfernt


def test_parse_recon_uebernachtfahrt():
    letzter = parse_recon(RECON)[1]
    assert letzter.train == "ICE 514"
    assert letzter.dep == datetime(2026, 8, 17, 20, 46, tzinfo=TZ)
    assert letzter.arr == datetime(2026, 8, 18, 1, 26, tzinfo=TZ)


def test_parse_recon_unbrauchbar():
    with pytest.raises(BahnLinkError, match="HKI"):
        parse_recon("irgendwas ohne Recon")
    with pytest.raises(BahnLinkError, match="Zugabschnitt"):
        parse_recon("¶HKI¶G$nur-fussweg¶KC¶")


# --- Zuordnung bahn.de-Abschnitt -> Transitous-Kandidat ------------------

def _option(dep: datetime, train: str):
    """Kandidat mit 3 min Fußweg vor der Zug-Abfahrt (wie MOTIS liefert)."""
    from datetime import timedelta

    from bmtools.rail.route import ItineraryOption
    return ItineraryOption(start=dep - timedelta(minutes=3),
                           end=dep + timedelta(hours=1),
                           transfers=0, trains=[train],
                           labels=[f"{train} (A -> B)"],
                           points=[(0.0, 0.0), (1.0, 1.0)], dep=dep)


def test_match_bevorzugt_zugnummer_bei_gleicher_abfahrt():
    from bmtools.rail.route import _match_fixed_leg
    leg = parse_recon(RECON)[1]  # ICE 514 ab 20:46
    andere = _option(leg.dep, "RE 5")
    richtige = _option(leg.dep, "ICE 514")
    assert _match_fixed_leg([andere, richtige], leg, warn=None) is richtige


def test_match_findet_zugnummer_in_gtfs_schreibweise():
    # GTFS nennt den Zug "RE7 (3285)", bahn.de nur "3285"
    from bmtools.rail.route import _match_fixed_leg
    leg = parse_recon(RECON)[0]  # Zug "3285" ab 06:57
    andere = _option(leg.dep, "RE7 (3289)")
    richtige = _option(leg.dep, "RE7 (3285)")
    assert _match_fixed_leg([andere, richtige], leg, warn=None) is richtige


def test_match_faellt_auf_abfahrtszeit_zurueck():
    # Nur die Liniennummer im Datensatz -> exakte Abfahrtszeit zählt
    from bmtools.rail.route import _match_fixed_leg
    leg = parse_recon(RECON)[0]
    linie = _option(leg.dep, "RE 96")
    assert _match_fixed_leg([linie], leg, warn=None) is linie


def test_route_fixed_ueberbrueckt_unaufloesbaren_abschnitt():
    # Z. B. SEV-Bus, den der Fahrplandatensatz nicht kennt: nur dieser
    # Abschnitt wird Luftlinie, die Fahrt scheitert nicht komplett
    from bmtools.rail.route import NoItineraryError, RoutePlanner

    legs = parse_recon(RECON)
    planner = RoutePlanner()

    def kennt_nur_leg1(frm, to, opts):
        if frm.name == legs[1].frm.name:
            return [_option(legs[1].dep, "ICE 514")]
        raise NoItineraryError("kenn ich nicht")

    planner.segment_options = kennt_nur_leg1
    warnungen = []
    route = planner.route_fixed(legs, warn=warnungen.append)
    assert "Luftlinie" in route.legs[0] and "3285" in route.legs[0]
    assert "ICE 514" in route.legs[1] and "Luftlinie" not in route.legs[1]
    assert len(warnungen) == 1 and "überbrücke" in warnungen[0]


def test_match_warnt_ohne_zeittreffer_und_nimmt_naechste():
    from datetime import timedelta

    from bmtools.rail.route import _match_fixed_leg
    leg = parse_recon(RECON)[0]
    frueher = _option(leg.dep - timedelta(minutes=60), "RE7 (3283)")
    spaeter = _option(leg.dep + timedelta(minutes=30), "RE 96")
    warnungen = []
    chosen = _match_fixed_leg([frueher, spaeter], leg, warn=warnungen.append)
    assert chosen is spaeter
    assert "3285" in warnungen[0]
