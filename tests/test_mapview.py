"""Smoke-Test Karte: FM-Marker (orange, CVD-sicher), Modus-Popups,
Sichtfeld-Fortschritt, GUI-Kartendaten (U4)."""
import base64
import hashlib
import io
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from bmtools.bm_api.models import TalkgroupSub
from bmtools.routelib import mapview as mapview_mod
from bmtools.routelib import terrain as terrain_mod
from bmtools.routelib.coverage import horizon_km
from bmtools.routelib.mapview import karten_daten, write_map
from bmtools.routelib.model import Route, Station
from bmtools.routelib.viewshed_raster import merc_y
from tests.conftest import make_device, make_fm_repeater, make_fm_result, make_result


def kunstgelaende(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Zerklüftetes, aber deterministisches Kunstgelände.

    Flaches Stub-Gelände liefert nur volle Sichtkreise — hier entstehen
    echte Schatten und Grenzbereiche, damit Zuschnitt und Aggregation
    der Sichtfelder überhaupt etwas zu tun haben.
    """
    la = np.asarray(lats, dtype=np.float64)
    lo = np.asarray(lons, dtype=np.float64)
    h = (400.0 * np.sin(la * 37.0) * np.cos(lo * 41.0)
         + 250.0 * np.sin(la * 113.0 + lo * 97.0)
         + 120.0 * np.cos(la * 211.0 - lo * 173.0))
    return h.astype(np.float32)


def kunstgelaende_modell(tmp_path: Path, monkeypatch) -> terrain_mod.TerrainModel:
    monkeypatch.setattr(terrain_mod, "user_cache_dir", lambda name: str(tmp_path))
    terrain = terrain_mod.TerrainModel()
    monkeypatch.setattr(terrain, "elevations", kunstgelaende)
    monkeypatch.setattr(terrain, "prefetch",
                        lambda lats, lons, progress=None: None)
    return terrain


def serialisiere_pool(monkeypatch, terrain: terrain_mod.TerrainModel) -> None:
    """Prozesspool durch einen seriellen Ersatz tauschen.

    Die echten Worker bauen über init_worker() ein eigenes TerrainModel
    und laden Höhenkacheln aus dem Netz — im Test unerwünscht. Geprüft
    werden soll die Aggregation, nicht das Forken.

    as_completed liefert bewusst RÜCKWÄRTS: im echten Prozesspool ist
    die Fertigstellungsreihenfolge beliebig, und die Einzelfelder müssen
    trotzdem indexgleich mit results landen. Gäbe der Ersatz die
    Reihenfolge der Einreichung zurück, bliebe genau dieser Fehler
    unentdeckt.
    """
    class Ergebnis:
        def __init__(self, wert):
            self._wert = wert

        def result(self):
            return self._wert

    class SerielleAusfuehrung:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, *args):
            return Ergebnis(fn(*args, terrain))

    monkeypatch.setattr(mapview_mod, "ProcessPoolExecutor", SerielleAusfuehrung)
    monkeypatch.setattr(mapview_mod, "as_completed", lambda fs: reversed(list(fs)))


def overlay_pixel(uri: str) -> np.ndarray:
    """RGBA-Array eines Overlay-Daten-URI."""
    roh = base64.b64decode(uri.partition("base64,")[2])
    return np.asarray(Image.open(io.BytesIO(roh)).convert("RGBA"))


def rampen_index(uri: str) -> np.ndarray:
    """Overlay zurück auf seine HEATMAP_RAMP-Stufen abbilden."""
    pixel = overlay_pixel(uri)
    index = np.zeros(pixel.shape[:2], dtype=np.uint8)
    for stufe, farbe in enumerate(mapview_mod.HEATMAP_RAMP):
        if stufe:  # Stufe 0 ist die transparente Vorbelegung
            index[np.all(pixel == farbe, axis=-1)] = stufe
    return index


def feld_pixelbereich(gitter, bounds: list[list[float]],
                      ) -> tuple[int, int, int, int]:
    """Bounds eines Einzelfelds zurück in Pixelindizes des Rasters.

    Umkehrung von _Rastergitter.bounds — schlägt die Rückrechnung fehl,
    liegt das Overlay auf der Karte falsch.
    """
    (lat_sued, lon_west), (lat_nord, lon_ost) = bounds
    span_lon = gitter.lon_max - gitter.lon_min
    span_y = gitter.y_max - gitter.y_min

    def zeile(lat: float) -> int:
        return round((gitter.y_max - merc_y(lat)) / span_y * gitter.h)

    return (zeile(lat_nord), zeile(lat_sued),
            round((lon_west - gitter.lon_min) / span_lon * gitter.w),
            round((lon_ost - gitter.lon_min) / span_lon * gitter.w))


@pytest.fixture
def sichtfeld_szenario(tmp_path: Path, monkeypatch):
    """Drei Relais auf Kunstgelände entlang einer kurzen Route."""
    terrain = kunstgelaende_modell(tmp_path, monkeypatch)
    serialisiere_pool(monkeypatch, terrain)
    points = [(50.0 + i * 0.02, 8.0 + i * 0.03) for i in range(12)]
    route = Route(points=points, stations=[Station("Start", *points[0])])
    results = [
        make_result(make_device(id=1, callsign="DB0AA", lat=50.05, lng=8.05)),
        make_result(make_device(id=2, callsign="DB0BB", lat=50.14, lng=8.19)),
        make_result(make_device(id=3, callsign="DB0CC", lat=50.20, lng=8.30)),
    ]
    return terrain, route, results


def test_karte_gemischt_faerbt_fm_orange(tmp_path: Path):
    points = [(50.0, 8.0), (50.1, 8.1), (50.2, 8.2)]
    route = Route(points=points,
                  stations=[Station("Start", *points[0]),
                            Station("Ziel", *points[-1])])
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
        make_fm_result(make_fm_repeater(
            callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525,
            ctcss_hz=88.5, locator="JO40AA")),
        make_fm_result(make_fm_repeater(
            callsign="DB0OT", tx_mhz=145.6, rx_mhz=145.0, ctcss_hz=None)),
    ]
    out = tmp_path / "karte.html"
    write_map(results, route, out)
    html = out.read_text(encoding="utf-8")

    assert "orange" in html                    # FM-Marker (kein Grün: CVD)
    assert "CTCSS 88.5 Hz (wird gesendet)" in html
    # ohne CTCSS-Angabe: Öffnungsweg ehrlich offen lassen
    assert "Träger oder Tonruf 1750 Hz" in html
    assert "Ablage -7.6 MHz" in html
    assert "Locator JO40AA" in html
    assert "DB0FX (5.0 km) — FM" in html        # Tooltip mit Modus-Zusatz
    assert "TS1" in html                        # DMR-Popup weiter vollständig


def test_karten_daten_fuer_die_gui(tmp_path: Path):
    """U4: karten_daten liefert dieselben Inhalte wie die folium-Karte
    als JSON-fähiges Dict (Marker-Popups aus denselben Helfern)."""
    points = [(50.0, 8.0), (50.123456789, 8.1), (50.2, 8.2)]
    route = Route(points=points,
                  stations=[Station("Start", *points[0]),
                            Station("Ziel", *points[-1])])
    results = [
        make_result(make_device(), [TalkgroupSub(262, 1, "static")]),
        make_fm_result(make_fm_repeater(
            callsign="DB0FX", tx_mhz=439.125, rx_mhz=431.525,
            ctcss_hz=88.5, locator="JO40AA")),
    ]

    daten = karten_daten(results, route, route_label="Bahnstrecke",
                         waypoint_icon="train")

    json.dumps(daten)  # muss ohne Sonderbehandlung serialisierbar sein
    assert [e["name"] for e in daten["ebenen"]] == [
        "OpenStreetMap", "Carto (Ausweichkarte)"]
    assert daten["bounds"] == [[50.0, 8.0], [50.2, 8.2]]
    assert daten["stations_icon"] == "train"
    assert [s["name"] for s in daten["stationen"]] == ["Start", "Ziel"]
    # Ohne Coverage: einfache Routenlinie, gerundet auf 5 Stellen
    assert daten["segmente"] is None and daten["legende"] is None
    assert daten["route"][1] == [50.12346, 8.1]
    farben = {m["farbe"] for m in daten["marker"]}
    assert farben == {"dmr", "fm"}
    fm_popup = next(m["popup"] for m in daten["marker"]
                    if m["farbe"] == "fm")
    assert "CTCSS 88.5 Hz (wird gesendet)" in fm_popup
    assert "Locator JO40AA" in fm_popup


def test_sichtfelder_melden_fortschritt(tmp_path: Path, monkeypatch):
    """Ein Relais (sequenzieller Pfad, kein Prozesspool) auf flachem
    Stub-Gelände: viewshed_progress meldet (0, 1) und (1, 1)."""
    monkeypatch.setattr(terrain_mod, "user_cache_dir",
                        lambda name: str(tmp_path))
    terrain = terrain_mod.TerrainModel()
    monkeypatch.setattr(
        terrain, "elevations",
        lambda lats, lons: np.zeros(np.shape(lats), dtype=np.float32))
    monkeypatch.setattr(terrain, "prefetch",
                        lambda lats, lons, progress=None: None)

    points = [(50.0, 8.0), (50.1, 8.1), (50.2, 8.2)]
    route = Route(points=points, stations=[Station("Start", *points[0])])
    results = [make_result(make_device(), [TalkgroupSub(262, 1, "static")])]
    meldungen: list[tuple[int, int]] = []
    out = tmp_path / "karte.html"
    write_map(results, route, out, terrain=terrain,
              viewshed_progress=lambda f, g: meldungen.append((f, g)))
    assert meldungen == [(0, 1), (1, 1)]
    assert "data:image/png" in out.read_text(encoding="utf-8")  # Overlay da


# Stand vor dem Zuschnitt-Refactor (render_relay liefert seit dem nur
# noch die belegte Pixel-Bbox statt des vollen Rasters). Gehasht wird
# das dekodierte RGBA-Array, nicht die PNG-Bytes: zlib-Ausgaben sind
# über Versionen und Plattformen hinweg nicht garantiert gleich, die
# Pixel dagegen reine numpy-Rechnung.
SUMMENKARTE_SHA256 = "39bf9d136e83cb253e21a406993e572819112768500d4760c922134b5af6da10"


def test_summenkarte_bleibt_unveraendert(sichtfeld_szenario, tmp_path: Path):
    """Regressionsanker der aggregierten Sichtfeld-Heatmap.

    Schlägt dieser Test fehl, hat sich das gerenderte Sichtfeld-Overlay
    geändert. War das beabsichtigt (Rampe, Auflösung, Viewshed-Modell),
    ist der Hash bewusst neu zu setzen — dann bitte im Commit begründen,
    warum sich die Abdeckungsdarstellung ändern durfte.
    """
    terrain, route, results = sichtfeld_szenario
    overlay = write_map(results, route, tmp_path / "karte.html",
                        terrain=terrain)
    assert overlay is not None
    pixel = overlay_pixel(overlay.uri)
    assert hashlib.sha256(pixel.tobytes()).hexdigest() == SUMMENKARTE_SHA256


def test_einzelfelder_ergeben_zusammen_die_summenkarte(
        sichtfeld_szenario, tmp_path: Path):
    """Die Summenkarte IST die Vereinigung der Einzelfelder.

    Prüft in einem Zug Zuschnitt, Bounds-Rückrechnung und Rampenstufen:
    jedes Einzelfeld wird über seine Geo-Bounds zurück ins globale
    Raster einsortiert; die Vereinigung muss die Sicht- und Grenz-
    bereichsflächen der Summenkarte exakt reproduzieren.

    Bewusst nur BINÄR (Sicht vs. Grenzbereich vs. nichts), nicht
    stufenweise: die Einzelfelder stufen nach Abstand, die Summenkarte
    nach Relaiszahl — und ein Pixel genau auf einer Abstandsgrenze darf
    beim Rückrechnen in die Nachbarstufe kippen. Diese Zusicherung also
    bitte nicht »verschärfen«, sie würde flackern.
    """
    terrain, route, results = sichtfeld_szenario
    overlay = write_map(results, route, tmp_path / "karte.html",
                        terrain=terrain)
    assert overlay is not None
    summe = rampen_index(overlay.uri)
    h, w = summe.shape
    (lat_min, lon_min), (lat_max, lon_max) = overlay.bounds
    gitter = mapview_mod._Rastergitter(w, h, lat_min, lon_min,
                                       lat_max, lon_max)

    assert len(overlay.felder) == len(results)
    assert all(f is not None for f in overlay.felder)

    sicht = np.zeros((h, w), dtype=bool)
    grenz = np.zeros((h, w), dtype=bool)
    for feld in overlay.felder:
        assert feld is not None
        stufen = rampen_index(feld.uri)
        y0, y1, x0, x1 = feld_pixelbereich(gitter, feld.bounds)
        # Deckt die Bounds-Rückrechnung genau das Bild ab? Weicht sie ab,
        # sitzt das Overlay auf der Karte verschoben.
        assert stufen.shape == (y1 - y0, x1 - x0)
        sicht[y0:y1, x0:x1] |= stufen >= 2
        grenz[y0:y1, x0:x1] |= stufen == 1

    # Summenkarte: Stufe >= 2 heißt >= 1 Relais mit Sicht, Stufe 1 heißt
    # ausschließlich Grenzbereich (Sicht überstimmt ihn dort)
    assert np.array_equal(sicht, summe >= 2)
    assert np.array_equal(grenz & ~sicht, summe == 1)


def test_einzelfeld_gehoert_zum_richtigen_relais(sichtfeld_szenario,
                                                 tmp_path: Path):
    """relais_felder[i] muss das Feld von results[i] sein.

    Darauf ruht das ganze Merkmal — die Oberfläche verbindet Marker,
    Tabellenzeile und Sichtfeld allein über diesen Index. Der
    Rekompositions-Test kann das NICHT zeigen: die Vereinigung aller
    Felder bleibt dieselbe, auch wenn die Zuordnung durchgeschüttelt
    ist. Zusammen mit der rückwärtigen Fertigstellungsreihenfolge in
    serialisiere_pool fängt dieser Test eine verrutschte
    Future-zu-Index-Zuordnung.

    Geprüft wird über den Schwerpunkt der nächsten Abstandsstufe
    (0–10 km): der liegt naturgemäß beim Relais. Die bloßen Bounds
    reichen nicht — bei ~24 km Horizont und ~10 km Relaisabstand
    enthalten sie auch die Nachbarn.
    """
    terrain, route, results = sichtfeld_szenario
    overlay = write_map(results, route, tmp_path / "karte.html",
                        terrain=terrain)
    assert overlay is not None
    for nr, (r, feld) in enumerate(zip(results, overlay.felder, strict=True)):
        assert feld is not None
        stufen = rampen_index(feld.uri)
        h, w = stufen.shape
        (lat_sued, lon_west), (lat_nord, lon_ost) = feld.bounds
        gitter = mapview_mod._Rastergitter(w, h, lat_sued, lon_west,
                                           lat_nord, lon_ost)
        lat, lon = gitter.pixelmitten(0, h, 0, w)
        nah = stufen == 4  # dunkelste Stufe: 0–10 km ums Relais
        assert nah.any(), f"{r.device.callsign}: keine nahe Sichtstufe"
        schwerpunkt = (float(np.broadcast_to(lat, nah.shape)[nah].mean()),
                       float(np.broadcast_to(lon, nah.shape)[nah].mean()))
        abstaende = [float(mapview_mod._abstand_km(
            np.array([schwerpunkt[0]]), np.array([schwerpunkt[1]]),
            o.device.lat, o.device.lng)[0]) for o in results]
        naechstes = abstaende.index(min(abstaende))
        assert naechstes == nr, (
            f"Feld {nr} liegt bei {results[naechstes].device.callsign}, "
            f"gehört laut Index aber zu {r.device.callsign}")


def test_einzelfeld_stuft_nach_abstand(sichtfeld_szenario, tmp_path: Path):
    """Dunkelste Stufe liegt nah am Relais, hellere weiter draußen —
    und kein Sicht-Pixel liegt jenseits des Radiohorizonts."""
    terrain, route, results = sichtfeld_szenario
    overlay = write_map(results, route, tmp_path / "karte.html",
                        terrain=terrain)
    assert overlay is not None
    feld = overlay.felder[0]
    assert feld is not None
    stufen = rampen_index(feld.uri)
    (lat_sued, lon_west), (lat_nord, lon_ost) = feld.bounds
    h, w = stufen.shape
    gitter = mapview_mod._Rastergitter(w, h, lat_sued, lon_west,
                                       lat_nord, lon_ost)
    lat, lon = gitter.pixelmitten(0, h, 0, w)
    gerät = results[0].device
    abstand = mapview_mod._abstand_km(lat, lon, gerät.lat, gerät.lng)

    # Toleranz: viewshed_raster zeichnet die Sichtläufe mit width=2 und
    # weitet sie danach mit MaxFilter(3) — zusammen bis zu ~3 Pixel über
    # die gerechnete Sichtgrenze hinaus. Grob genug, um die Dilatation
    # zu schlucken, eng genug, um eine systematisch falsche
    # Abstandsrechnung (verwechselte Achse, fehlender cos(lat)) zu fangen.
    rand = 3 * mapview_mod.HEATMAP_PX_KM

    for stufe, (unten, oben) in {4: (0.0, 10.0), 3: (10.0, 20.0),
                                 2: (20.0, math.inf)}.items():
        treffer = abstand[stufen == stufe]
        assert len(treffer), f"Stufe {stufe} kommt im Sichtfeld nicht vor"
        assert treffer.min() >= unten - rand
        assert treffer.max() <= oben + rand

    # Kein Sicht-Pixel jenseits des Radiohorizonts: fängt eine
    # systematisch verrutschte Abstandsrechnung ab
    assert abstand[stufen >= 2].max() <= horizon_km(gerät.agl) + rand


def test_kartendaten_reichen_einzelfelder_durch(sichtfeld_szenario,
                                                tmp_path: Path):
    """Die Einzelfelder liegen indexgleich mit den Markern im Payload —
    die GUI verbindet Marker, Tabellenzeile und Sichtfeld über diesen
    gemeinsamen Index."""
    terrain, route, results = sichtfeld_szenario
    overlay = write_map(results, route, tmp_path / "karte.html",
                        terrain=terrain)
    assert overlay is not None
    daten = karten_daten(results, route, overlay=overlay)

    json.dumps(daten)  # muss ohne Sonderbehandlung serialisierbar sein
    felder = daten["relais_felder"]
    assert len(felder) == len(daten["marker"]) == len(results)
    assert all(f["uri"].startswith("data:image/png") for f in felder)
    # Abstandsstufen von nah (dunkel) nach fern (hell), plus der
    # Hinweis, dass die Stufen Geometrie und keine Feldstärke sind
    legende = daten["feld_legende"]
    assert [s["text"] for s in legende["stufen"]] == [
        "Sicht 0–10 km", "Sicht 10–20 km", "Sicht über 20 km"]
    assert [s["farbe"] for s in legende["stufen"]] == [
        "#03395C", "#0072B2", "#56B4E9"]
    assert legende["grenz"]["farbe"] == "#A6D6EB"
    assert "keine Feldstärke" in legende["hinweis"]
    # Das Summen-Overlay bleibt unverändert — mapimage/PDF lesen es
    assert daten["overlay"]["uri"] == overlay.uri
    assert daten["overlay"]["bounds"] == overlay.bounds


def test_karte_html_verdrahtet_die_einzelfelder(sichtfeld_szenario,
                                                tmp_path: Path):
    """Die verschickbare karte.html bekommt dieselbe Einzelansicht.

    Prüft vor allem die zwei Bruchstellen der folium-Verdrahtung: die
    referenzierten JS-Variablen müssen wirklich existieren, und das
    Skript muss auf DOMContentLoaded warten, weil folium sein eigenes JS
    HINTER die manuell angehängten Skript-Kinder rendert.
    """
    terrain, route, results = sichtfeld_szenario
    out = tmp_path / "karte.html"
    overlay = write_map(results, route, out, terrain=terrain)
    assert overlay is not None
    quelle = out.read_text(encoding="utf-8")

    skript = quelle.index('var D = {"felder"')
    # Verzögert, weil das Skript baulich vor seinen Variablen steht
    assert 'DOMContentLoaded", function' in quelle, (
        "Einzelfeld-Skript läuft sofort — es stünde damit vor den "
        "folium-Variablen, die es benutzt")
    assert quelle.index('DOMContentLoaded", function') < skript
    definiert = set(re.findall(r"var (\w+) = L\.(?:marker|imageOverlay)\(",
                               quelle))
    definiert |= set(re.findall(r"var (\w+) = L\.map\(", quelle))
    referenziert = set(re.findall(r"var karte = (\w+), ebene = (\w+);",
                                  quelle)[0])
    marker_zeile = re.search(r"var marker = \[([^\]]*)\]", quelle)
    assert marker_zeile is not None, "Marker-Liste fehlt im Skript"
    referenziert |= set(marker_zeile.group(1).replace(" ", "").split(","))
    fehlend = referenziert - definiert
    assert not fehlend, f"Skript referenziert undefinierte Variablen: {fehlend}"
    assert len(referenziert) == len(results) + 2  # Marker + Karte + Ebene

    # Jedes Einzelfeld liegt in der Datei — sie bleibt eigenständig
    for feld in overlay.felder:
        assert feld is not None
        assert feld.uri in quelle
    assert "keine Feldstärke" in quelle


def test_ohne_gelaende_keine_einzelfelder(tmp_path: Path):
    """Horizontmodell-Fallback (Netzabbruch): keine Sichtfelder, weder
    aggregiert noch einzeln — die Oberfläche muss das aushalten."""
    points = [(50.0, 8.0), (50.1, 8.1)]
    route = Route(points=points, stations=[Station("Start", *points[0])])
    results = [make_result(make_device())]
    overlay = write_map(results, route, tmp_path / "karte.html", terrain=None)
    assert overlay is None

    daten = karten_daten(results, route, overlay=None)
    assert daten["overlay"] is None
    assert daten["relais_felder"] is None
    assert daten["feld_legende"] is None
