"""Interaktive HTML-Karte: Streckenverlauf + Relais-Marker (folium/Leaflet).

Seit U4 (GUI-UMBAU.md) liefert karten_daten() dieselben Inhalte
(Segmente, Marker-Popups, Legende, Overlay) als JSON-fähiges Dict an
die native Leaflet-Ansicht der GUI — die Helfer sind geteilt, damit
Datei-Karte und GUI-Karte nie auseinanderlaufen.
"""
from __future__ import annotations

import base64
import html
import io
import math
import os
from bisect import bisect_right
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import folium
import numpy as np
from PIL import Image

from bmtools.fm_api.models import band_label

from . import viewshed_raster
from .corridor import bounding_box, cumulative_km
from .coverage import DEFAULT_AGL_M, LOS, MARGINAL, SHADOW, CoverageEstimate, horizon_km
from .model import Point, RepeaterLike, Route
from .report import MODUS_LABEL, RepeaterResult, _fmt_subs
from .terrain import TerrainModel

HEATMAP_PX_KM = 0.25       # Zielauflösung des Rasters
HEATMAP_MAX_PX = 1800      # Deckel je Achse
# Kräftige Hellblau->Dunkelblau-Rampe (CVD-sicher: eine Farbachse,
# Helligkeit trägt die Information): hellste Stufe = nur Grenzbereich
# (Beugung), darüber 1 / 2 / >=3 Relais mit freier Sicht
HEATMAP_RAMP = np.array([
    (0, 0, 0, 0),           # keine Abdeckung: transparent
    (166, 214, 235, 110),   # nur Grenzbereich — #A6D6EB
    (86, 180, 233, 150),    # 1 Relais  — #56B4E9
    (0, 114, 178, 195),     # 2 Relais  — #0072B2
    (3, 57, 92, 230),       # >=3 Relais — #03395C
], dtype=np.uint8)

# Farbenblind-sicher (rechnerisch geprüft: CVD-Delta-E >= 57, Kontrast zur
# Kartenfläche >= 3:1) und redundant über den Linienstil kodiert — Status
# ist nie nur an der Farbe erkennbar.
STATUS_STYLE = {
    LOS: ("#0072B2", None, "Abdeckung wahrscheinlich (Sicht)"),
    MARGINAL: ("#B86200", "10,6", "Grenzbereich (Beugung möglich)"),
    SHADOW: ("#000000", "2,7", "Funkschatten (geschätzt)"),
}

# Basiskarten — GUI-Leaflet-Ansicht und folium-Karte nutzen dieselben
# Quellen: OSM.DE ohne Referer-Pflicht (s. Kommentar in write_map),
# Carto-CDN als umschaltbare Ausweich-Ebene. Keyless.
KARTEN_EBENEN: list[dict[str, Any]] = [
    {"name": "OpenStreetMap",
     "url": "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
     "max_zoom": 18,
     "attribution": '&copy; <a href="https://www.openstreetmap.org/'
                    'copyright">OpenStreetMap</a>-Mitwirkende'},
    {"name": "Carto (Ausweichkarte)",
     "url": "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/"
            "{z}/{x}/{y}.png",
     "subdomains": "abcd",
     "max_zoom": 20,
     "attribution": '&copy; <a href="https://www.openstreetmap.org/'
                    'copyright">OpenStreetMap</a>-Mitwirkende &copy; '
                    '<a href="https://carto.com/attributions">CARTO</a>'},
]

OVERLAY_NAME = "Relais-Sichtfelder (rechnerisch)"

# Abstandsstufen des Einzelrelais-Sichtfelds (km). Bei genau einem
# Relais trägt die Summen-Rampe keine Information mehr — dort zählt sie
# abdeckende Relais —, deshalb stuft die Einzelansicht nach Abstand:
# dunkel = nah. Das ist reine Geometrie; ERP und Antennendiagramm sind
# dem Tool unbekannt, die Stufen sind KEINE Feldstärke. Die Legende sagt
# das ausdrücklich (FELD_STUFEN_LABEL).
FELD_STUFEN_KM = (10.0, 20.0)


def _hex(farbe: np.ndarray) -> str:
    r, g, b = (int(k) for k in farbe[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def _feld_legende() -> dict[str, Any]:
    """Legende der Einzelrelais-Ansicht: Abstandsstufen von nah (dunkel)
    nach fern (hell), dazu der Grenzbereich und der Ehrlichkeits-Hinweis.

    Wortlaut und Farben stehen hier — GUI-Karte und folium-Karte lesen
    beide von hier, damit sie nie auseinanderlaufen.
    """
    grenzen = FELD_STUFEN_KM
    texte = [f"Sicht 0–{grenzen[0]:g} km"]
    texte += [f"Sicht {a:g}–{b:g} km" for a, b in pairwise(grenzen)]
    texte.append(f"Sicht über {grenzen[-1]:g} km")
    # Sicht-Stufen der Rampe von dunkel (nah) nach hell (fern); Stufe 0
    # ist transparent, Stufe 1 der Grenzbereich. strict=True hält die
    # Zusicherung fest, dass FELD_STUFEN_KM genau so viele Stufen
    # verlangt, wie HEATMAP_RAMP für Sicht hergibt.
    farben = [_hex(HEATMAP_RAMP[i]) for i in range(len(HEATMAP_RAMP) - 1, 1, -1)]
    return {
        "stufen": [{"farbe": f, "text": t}
                   for f, t in zip(farben, texte, strict=True)],
        "grenz": {"farbe": _hex(HEATMAP_RAMP[1]),
                  "text": "Grenzbereich (Beugung möglich)"},
        # Der Kern der Ehrlichkeit: die Stufen sind Geometrie. Das Tool
        # kennt weder Sendeleistung noch Antennendiagramm.
        "hinweis": "Abstufung = Abstand zum Relais, keine Feldstärke "
                   "(ERP und Antennendiagramm sind unbekannt)",
        "zurueck": "alle Relais anzeigen",
    }


@dataclass(frozen=True)
class RelaisFeld:
    """Sichtfeld eines einzelnen Relais als eigenes Karten-Overlay."""
    uri: str
    bounds: list[list[float]]


@dataclass(frozen=True)
class Sichtfelder:
    """Gerenderte Sichtfelder eines Laufs.

    uri/bounds sind die aggregierte Summenkarte (alle Relais), felder
    die Einzelfelder — indexgleich mit der results-Liste und damit mit
    den Markern; None, wo ein Relais kein Sichtfeld im Raster hat.
    """
    uri: str
    bounds: list[list[float]]
    felder: list[RelaisFeld | None]

# Semantische Marker-Farben -> folium-Icon-Farbe (die GUI stylt die
# semantischen Namen selbst, projektweit dieselbe Bedeutung)
_FARBE_FOLIUM = {"dmr": "blue", "fm": "orange", "grenz": "gray"}


def _legend_line(color: str, dash: str | None) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<svg width="34" height="8" style="vertical-align:middle">'
            f'<line x1="1" y1="4" x2="33" y2="4" stroke="{color}" '
            f'stroke-width="4"{dash_attr}/></svg>')


def _legend(modus_label: str, marker_note: str) -> str:
    return f"""
<div style="position:fixed; bottom:16px; left:16px; z-index:9999;
     background:#fff; color:#111; padding:8px 12px; border-radius:6px;
     box-shadow:0 1px 4px #0006; font:13px/1.8 sans-serif;">
<b>Geschätzte {modus_label}-Abdeckung</b><br>
{_legend_line(*STATUS_STYLE[LOS][:2])} Sicht (durchgezogen)<br>
{_legend_line(*STATUS_STYLE[MARGINAL][:2])} Grenzbereich (gestrichelt)<br>
{_legend_line(*STATUS_STYLE[SHADOW][:2])} Schatten (gepunktet)<br>
<span style="display:inline-block;width:30px;height:10px;vertical-align:middle;
background:linear-gradient(90deg,#A6D6EB,#56B4E9,#0072B2,#03395C)"></span>
Relais-Sichtfeld (hellste Stufe: nur Beugung, sonst dunkler = mehr Relais)<br>
Marker: {marker_note}
</div>
"""


def _pos(d: RepeaterLike) -> tuple[float, float]:
    """Koordinaten als Nicht-None: is_repeater() bzw. der FM-Parser
    filtern Positionslose, bevor sie hierher gelangen."""
    assert d.lat is not None and d.lng is not None
    return d.lat, d.lng


def _png_uri(index: np.ndarray) -> str:
    """Rampenindex-Array als PNG-Daten-URI.

    PNG selbst kodieren: branca normalisiert numpy-Arrays kanalweise auf
    255 und würde die Farbe verfälschen (Blau -> Cyan).
    """
    buf = io.BytesIO()
    Image.fromarray(HEATMAP_RAMP[index], "RGBA").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _inv_merc_y(y: float) -> float:
    """Umkehrung von viewshed_raster.merc_y — Mercator-Y zu Breitengrad."""
    return 2.0 * (math.degrees(math.atan(math.exp(y))) - 45.0)


class _Rastergitter:
    """Pixelgitter des Sichtfeld-Rasters mit seiner Geo-Zuordnung.

    Zeilen liegen linear in Mercator-Y (so spannt Leaflet ImageOverlays
    auf), Spalten linear im Längengrad.
    """

    def __init__(self, w: int, h: int, lat_min: float, lon_min: float,
                 lat_max: float, lon_max: float) -> None:
        self.w, self.h = w, h
        self.lon_min, self.lon_max = lon_min, lon_max
        self.y_min = viewshed_raster.merc_y(lat_min)
        self.y_max = viewshed_raster.merc_y(lat_max)

    def bounds(self, y0: int, y1: int, x0: int, x1: int) -> list[list[float]]:
        """Geo-Bounds der Pixel y0..y1-1 / x0..x1-1.

        Kantenbasiert (Anteil /w bzw. /h, nicht /(w-1)): Leaflet zieht
        die Bildkanten auf die Bounds, nicht die Pixelmitten. So deckt
        ein Zuschnitt auf dem Schirm exakt dieselbe Fläche ab wie die
        entsprechenden Pixel der Summenkarte — die beiden Ansichten
        springen beim Umschalten nicht gegeneinander.
        """
        span_lon = self.lon_max - self.lon_min
        span_y = self.y_max - self.y_min
        return [[_inv_merc_y(self.y_max - y1 / self.h * span_y),
                 self.lon_min + x0 / self.w * span_lon],
                [_inv_merc_y(self.y_max - y0 / self.h * span_y),
                 self.lon_min + x1 / self.w * span_lon]]

    def pixelmitten(self, y0: int, y1: int, x0: int, x1: int,
                    ) -> tuple[np.ndarray, np.ndarray]:
        """(lat, lon) der Pixelmitten eines Zuschnitts als Zeilen-/
        Spaltenvektor — zum Broadcasten auf die Zuschnittfläche."""
        span_lon = self.lon_max - self.lon_min
        span_y = self.y_max - self.y_min
        lon = self.lon_min + (np.arange(x0, x1) + 0.5) / self.w * span_lon
        merc = self.y_max - (np.arange(y0, y1) + 0.5) / self.h * span_y
        lat = 2.0 * (np.degrees(np.arctan(np.exp(merc))) - 45.0)
        return lat[:, None], lon[None, :]


def _abstand_km(lat: np.ndarray, lon: np.ndarray,
                lat0: float, lon0: float) -> np.ndarray:
    """Haversine-Abstand jedes Punktes zum Relais (km) — vektorisiert.

    Bewusst keine Näherung über einen festen km/Pixel-Faktor: die Zeilen
    des Rasters liegen in Mercator-Y, auf einem Raster über die ganze
    Republik unterscheiden sich Nord- und Südrand deutlich in km/Pixel.
    """
    p0 = math.radians(lat0)
    p1 = np.radians(lat)
    dphi = p1 - p0
    dlmb = np.radians(lon - lon0)
    a = (np.sin(dphi / 2.0) ** 2
         + math.cos(p0) * np.cos(p1) * np.sin(dlmb / 2.0) ** 2)
    return 2.0 * 6371.0 * np.arcsin(np.sqrt(a))


def _relais_feld(los: np.ndarray, marg_bits: np.ndarray,
                 bbox: viewshed_raster.Bbox, gitter: _Rastergitter,
                 lat0: float, lon0: float) -> RelaisFeld:
    """Einzelfeld eines Relais als PNG-Overlay, nach Abstand gestuft.

    Rampenindex: 1 = Grenzbereich (hellste Stufe), 2..4 = Sicht von
    fern nach nah — dieselbe HEATMAP_RAMP wie die Summenkarte, damit
    »dunkler = besser« in beiden Ansichten gilt und die geprüften
    Farbfehlsichtigkeits-Abstände unverändert weiter gelten.
    """
    y0, y1, x0, x1 = bbox
    ch, cw = y1 - y0, x1 - x0
    marg = np.unpackbits(marg_bits, count=ch * cw).reshape(ch, cw).astype(bool)
    lat, lon = gitter.pixelmitten(y0, y1, x0, x1)
    stufe = np.digitize(_abstand_km(lat, lon, lat0, lon0), FELD_STUFEN_KM)
    # Sicht schlägt Grenzbereich (die MaxFilter-Dilatation kann beide
    # Ebenen überlappen lassen) — wie in der Summenkarte, wo count > 0
    # den Grenzbereich überstimmt.
    index = np.where(los.astype(bool), 4 - stufe, marg.astype(np.uint8))
    return RelaisFeld(uri=_png_uri(index),
                      bounds=gitter.bounds(y0, y1, x0, x1))


def _coverage_raster(results: list[RepeaterResult], route: Route,
                     terrain: TerrainModel,
                     tile_progress: Callable[[int, int], None] | None = None,
                     viewshed_progress: Callable[[int, int], None] | None = None,
                     ) -> Sichtfelder:
    """Viewsheds aller Korridor-Relais rastern.

    Liefert die Summenkarte — ein Blauton, Deckkraft nach Zahl der
    abdeckenden Relais (sequenzielle Ein-Farb-Rampe, farbfehlsichtig-
    keits-sicher) — und dazu jedes Einzelfeld als eigenes, nach Abstand
    gestuftes Overlay für die Einzelrelais-Ansicht.

    tile_progress/viewshed_progress melden (fertig, gesamt) für den
    Kachel-Prefetch bzw. je fertig gerechnetem Relais-Sichtfeld.
    """
    # Raster-Ausdehnung: Strecke plus jedes Relais samt seiner vollen
    # Sichtweite — sonst werden Viewsheds am Rasterrand abgeschnitten
    # (weit abseits stehende Relais sogar komplett).
    lat_min, lon_min, lat_max, lon_max = bounding_box(route.points, 2.0)
    for r in results:
        d_lat, d_lng = _pos(r.device)
        radius = horizon_km(r.device.agl or DEFAULT_AGL_M)
        dlat = radius / 111.32
        dlon = radius / (111.32 * math.cos(math.radians(d_lat)))
        lat_min = min(lat_min, d_lat - dlat)
        lat_max = max(lat_max, d_lat + dlat)
        lon_min = min(lon_min, d_lng - dlon)
        lon_max = max(lon_max, d_lng + dlon)
    mid_lat = (lat_min + lat_max) / 2
    width_km = (lon_max - lon_min) * 111.32 * math.cos(math.radians(mid_lat))
    height_km = (lat_max - lat_min) * 111.32
    w = min(int(width_km / HEATMAP_PX_KM), HEATMAP_MAX_PX)
    h = min(int(height_km / HEATMAP_PX_KM), HEATMAP_MAX_PX)

    # Volle Horizont-Reichweite rechnen — dieselbe Grenze wie in der
    # Streckenklassifikation, sonst widersprechen sich Linie und Heatmap
    tasks: list[viewshed_raster.RenderTask] = [
        (*_pos(r.device), r.device.agl or DEFAULT_AGL_M,
         w, h, lat_min, lon_min, lat_max, lon_max)
        for r in results]

    # Kacheln aller Sichtfelder vorab in einem Rutsch parallel laden —
    # verhindert bei kaltem Cache doppelte Downloads konkurrierender Worker
    pre_lats, pre_lons = [], []
    for lat, lng, agl, *_ in tasks:
        d_km = np.arange(0.0, horizon_km(agl) + 4.0, 4.0)
        az = np.radians(np.arange(0.0, 360.0, 5.0))
        pre_lats.append((lat + np.outer(np.cos(az), d_km) / 111.32).ravel())
        pre_lons.append((lng + np.outer(np.sin(az), d_km)
                         / (111.32 * math.cos(math.radians(lat)))).ravel())
    terrain.prefetch(np.concatenate(pre_lats), np.concatenate(pre_lons),
                     tile_progress)

    gitter = _Rastergitter(w, h, lat_min, lon_min, lat_max, lon_max)
    count = np.zeros((h, w), dtype=np.uint8)   # Relais mit freier Sicht
    marginal = np.zeros((h, w), dtype=bool)    # Grenzbereich (Beugung)
    felder: list[RelaisFeld | None] = [None] * len(tasks)
    fertig = 0

    def einrechnen(nr: int, ergebnis: viewshed_raster.RenderResult) -> None:
        """Ein fertiges Sichtfeld in die Summenkarte addieren und als
        Einzelfeld ablegen. nr ist der results-Index — die Einzelfelder
        müssen indexgleich mit den Markern bleiben."""
        nonlocal fertig
        los, marg_bits, bbox = ergebnis
        if bbox is not None:
            y0, y1, x0, x1 = bbox
            ch, cw = y1 - y0, x1 - x0
            count[y0:y1, x0:x1] += los
            marginal[y0:y1, x0:x1] |= np.unpackbits(
                marg_bits, count=ch * cw).reshape(ch, cw).astype(bool)
            felder[nr] = _relais_feld(los, marg_bits, bbox, gitter,
                                      tasks[nr][0], tasks[nr][1])
        fertig += 1
        if viewshed_progress:
            viewshed_progress(fertig, len(tasks))

    if viewshed_progress:
        viewshed_progress(0, len(tasks))
    if len(tasks) > 1:
        workers = min(len(tasks), os.cpu_count() or 2)
        with ProcessPoolExecutor(
                max_workers=workers,
                initializer=viewshed_raster.init_worker) as pool:
            # submit/as_completed statt pool.map: Fortschritt je fertigem
            # Sichtfeld; die Aggregation ist reihenfolge-unabhängig. Das
            # Future trägt seinen results-Index mit, damit die Einzelfelder
            # trotz beliebiger Fertigstellungsreihenfolge richtig landen.
            nummern = {pool.submit(viewshed_raster.render_relay, t): nr
                       for nr, t in enumerate(tasks)}
            for f in as_completed(nummern):
                einrechnen(nummern[f], f.result())
    else:
        for nr, t in enumerate(tasks):
            einrechnen(nr, viewshed_raster.render_relay(t, terrain))

    # Rampenindex: 0 = nichts, 1 = nur Grenzbereich, 2..4 = 1/2/>=3 Relais
    index = np.where(count > 0, 1 + np.clip(count, 0, 3),
                     marginal.astype(np.uint8))
    return Sichtfelder(uri=_png_uri(index),
                       bounds=[[lat_min, lon_min], [lat_max, lon_max]],
                       felder=felder)


def _coverage_segments(
    route: Route, coverage: CoverageEstimate,
) -> list[tuple[int, list[Point], float, float]]:
    """Streckenpunkte zu Abschnitten gleichen Abdeckungsstatus bündeln.

    Liefert (status, punkte, start_km, end_km) je Abschnitt.
    """
    cum = cumulative_km(route.points)
    sample_kms = [s.km for s in coverage.samples]

    def status_at(km: float) -> int:
        idx = bisect_right(sample_kms, km) - 1
        return coverage.samples[max(idx, 0)].status

    segments: list[tuple[int, list[Point], float, float]] = []
    current = status_at(0.0)
    pts = [route.points[0]]
    seg_start = 0.0
    for prev_k, p, k in zip(cum, route.points[1:], cum[1:], strict=False):
        s = status_at((prev_k + k) / 2)
        if s == current:
            pts.append(p)
        else:
            segments.append((current, pts, seg_start, prev_k))
            pts = [pts[-1], p]
            seg_start = prev_k
            current = s
    segments.append((current, pts, seg_start, cum[-1]))
    return segments


def _reachable_in_range(coverage: CoverageEstimate, start_km: float,
                        end_km: float, listed: set[str],
                        status: int) -> str:
    """Erreichbare Relais eines Abschnitts als Tooltip-Zusatz.

    * markiert Relais, die nicht in der Ergebnisliste stehen (z. B. wegen
    --corridor-Limit oder weil sie nur grenzwertig erreichbar sind).
    """
    names: set[str] = set()
    unlisted: set[str] = set()
    for s in coverage.samples:
        if start_km - 0.25 <= s.km <= end_km:
            pool = s.los if status == LOS else (s.los + s.marginal)
            for c in pool:
                (names if c in listed else unlisted).add(c)
    parts = sorted(names) + [f"{c}*" for c in sorted(unlisted)]
    if not parts:
        return ""
    suffix = " (* nicht in der Relais-Liste)" if unlisted else ""
    return f" — Relais: {', '.join(parts)}{suffix}"


def _marker_farbe(r: RepeaterResult) -> str:
    # Orange für FM (statt Grün): Farbwelt ohne Rot/Grün, s. ui.py
    return ("grenz" if r.marginal_only
            else "fm" if r.modus == "fm" else "dmr")


def _marker_popup(r: RepeaterResult) -> str:
    e = html.escape
    d = r.device
    marginal_note = ("<b>Nur Grenzbereich</b> — keine freie Sicht zur "
                     "Strecke, Empfang per Beugung möglich<br>"
                     if r.marginal_only else "")
    if r.modus == "fm":
        fm = r.fm
        offset = fm.rx_mhz - fm.tx_mhz
        ablage = ("Simplex" if abs(offset) < 1e-9
                  else f"Ablage {offset:+g} MHz")
        # Quelle kennt kein Tonruf-Feld: ohne CTCSS bleibt offen, ob
        # Träger reicht oder der 1750-Hz-Tonruf nötig ist
        ctcss = (f", CTCSS {fm.ctcss_hz:g} Hz (wird gesendet)"
                 if fm.ctcss_hz
                 else ", Öffnen: Träger oder Tonruf 1750 Hz")
        return (
            f"<b>{e(fm.callsign)}</b> — {e(fm.city)}<br>{marginal_note}"
            f"FM ({band_label(fm.tx_mhz)})<br>"
            f"RX <code>{fm.tx_mhz:.5f}</code> / "
            f"TX <code>{fm.rx_mhz:.5f}</code> MHz, "
            f"{ablage}{ctcss}<br>"
            f"<small>km {r.hit.chainage_km:.0f}, Abstand "
            f"{r.hit.distance_km:.1f} km, Locator {e(fm.locator)}</small>"
        )
    return (
        f"<b>{e(d.callsign)}</b> — {e(d.city)}<br>{marginal_note}"
        f"RX <code>{d.tx_mhz:.5f}</code> / TX <code>{d.rx_mhz:.5f}</code> MHz, "
        f"CC{r.dmr.colorcode}<br>"
        f"TS1: {e(_fmt_subs(r.tg_profile.for_slot(1)) or '–')}<br>"
        f"TS2: {e(_fmt_subs(r.tg_profile.for_slot(2)) or '–')}<br>"
        f"<small>km {r.hit.chainage_km:.0f}, Abstand "
        f"{r.hit.distance_km:.1f} km, DMR-ID {d.id}</small>"
    )


def _marker_tooltip(r: RepeaterResult, has_dmr: bool, has_fm: bool) -> str:
    tooltip = f"{r.device.callsign} ({r.hit.distance_km:.1f} km)"
    if has_dmr and has_fm:
        tooltip += f" — {MODUS_LABEL[r.modus]}"
    if r.marginal_only:
        tooltip += " — nur Grenzbereich"
    return tooltip


def _marker_infos(results: list[RepeaterResult],
                  ) -> list[tuple[RepeaterResult, str, str, str]]:
    """Je Relais (result, farbe, tooltip, popup_html) — geteilt von
    folium-Karte und GUI-Kartendaten."""
    has_dmr = any(r.modus == "dmr" for r in results)
    has_fm = any(r.modus == "fm" for r in results)
    return [(r, _marker_farbe(r), _marker_tooltip(r, has_dmr, has_fm),
             _marker_popup(r)) for r in results]


def _segment_infos(route: Route, coverage: CoverageEstimate,
                   listed: set[str],
                   ) -> list[tuple[int, list[Point], str]]:
    """Abdeckungs-Abschnitte samt fertigem Tooltip-Text."""
    infos: list[tuple[int, list[Point], str]] = []
    for status, pts, start_km, end_km in _coverage_segments(route, coverage):
        label = STATUS_STYLE[status][2]
        tooltip = f"km {start_km:.0f}–{end_km:.0f}: {label}"
        if status != SHADOW:
            tooltip += _reachable_in_range(
                coverage, start_km, end_km, listed, status)
        infos.append((status, pts, tooltip))
    return infos


def _legende_infos(results: list[RepeaterResult]) -> tuple[str, str]:
    """(Modus-Label, Marker-Hinweis) für die Legende."""
    has_dmr = any(r.modus == "dmr" for r in results)
    has_fm = any(r.modus == "fm" for r in results)
    modus_label = MODUS_LABEL["beide" if has_dmr and has_fm
                              else "fm" if has_fm else "dmr"]
    # Orange statt des naheliegenden Grüns für FM: die Farbwelt des
    # Projekts ist bewusst ohne Rot/Grün (Farbfehlsichtigkeit, ui.py)
    marker_note = ("blau = DMR, orange = FM, grau = nur Grenzbereich "
                   "(Beugung)" if has_dmr and has_fm else
                   "orange = FM-Relais, grau = nur Grenzbereich "
                   "(Beugung)" if has_fm else
                   "blau = Sicht zur Strecke, grau = nur Grenzbereich "
                   "(Beugung)")
    return modus_label, marker_note


def write_map(results: list[RepeaterResult], route: Route, path: Path,
              coverage: CoverageEstimate | None = None,
              terrain: TerrainModel | None = None,
              route_label: str = "Strecke",
              waypoint_icon: str = "flag", *,
              tile_progress: Callable[[int, int], None] | None = None,
              viewshed_progress: Callable[[int, int], None] | None = None,
              ) -> Sichtfelder | None:
    """Folium-Karte schreiben; liefert die gerenderten Sichtfelder
    (Summenkarte und Einzelfelder) zurück — die GUI-Kartendaten
    (karten_daten) verwenden sie weiter, statt die Viewsheds doppelt zu
    rechnen."""
    overlay: Sichtfelder | None = None
    lats = [p[0] for p in route.points]
    lons = [p[1] for p in route.points]
    # tile.openstreetmap.de statt tile.openstreetmap.org: Die OSMF-Server
    # verlangen einen Referer (osm.wiki/Blocked) — eine verschickte, per
    # file:// geöffnete HTML-Datei sendet aber nie einen (Referer ist ein
    # forbidden header, Leaflets referrerPolicy hilft nur auf gehosteten
    # Seiten), Empfänger sahen "Access Blocked"-Kacheln (2026-07-13).
    # Der FOSSGIS-Server liefert die klassische OSM-Optik ohne
    # Referer-Pflicht; Carto-CDN als umschaltbare Ausweich-Ebene.
    m = folium.Map(tiles=None)
    folium.TileLayer("OpenStreetMap.DE", name="OpenStreetMap").add_to(m)
    folium.TileLayer("cartodbvoyager", name="Carto (Ausweichkarte)",
                     show=False).add_to(m)
    m.fit_bounds([(min(lats), min(lons)), (max(lats), max(lons))])

    if terrain is not None and results:
        overlay = _coverage_raster(results, route, terrain,
                                   tile_progress, viewshed_progress)
        folium.raster_layers.ImageOverlay(
            image=overlay.uri, bounds=overlay.bounds, opacity=0.8,
            name=OVERLAY_NAME,
        ).add_to(m)
    # Vor den Markern einhängen, sonst listet das Control jeden Marker
    folium.LayerControl().add_to(m)

    if coverage is not None and coverage.samples:
        listed = {r.device.callsign for r in results}
        for status, pts, tooltip in _segment_infos(route, coverage, listed):
            color, dash, _ = STATUS_STYLE[status]
            folium.PolyLine(pts, color=color, weight=5, opacity=0.95,
                            dash_array=dash, tooltip=tooltip).add_to(m)
        # branca.Element bekommt .html erst zur Laufzeit angehängt
        m.get_root().html.add_child(  # type: ignore[attr-defined]
            folium.Element(_legend(*_legende_infos(results))))
    else:
        folium.PolyLine(route.points, color="#c00", weight=3,
                        tooltip=route_label).add_to(m)
    for s in route.stations:
        folium.Marker(
            (s.lat, s.lon), tooltip=s.name,
            icon=folium.Icon(color="red", icon=waypoint_icon, prefix="fa"),
        ).add_to(m)

    for r, farbe, tooltip, popup in _marker_infos(results):
        folium.Marker(
            _pos(r.device),
            tooltip=tooltip,
            popup=folium.Popup(popup, max_width=340),
            icon=folium.Icon(color=_FARBE_FOLIUM[farbe], icon="tower-cell",
                             prefix="fa"),
        ).add_to(m)

    m.save(str(path))
    return overlay


def _runde_punkte(punkte: list[Point]) -> list[list[float]]:
    # 5 Nachkommastellen (~1 m): hält die JSON-Nutzlast langer Routen
    # klein, ohne sichtbare Abweichung auf der Karte
    return [[round(lat, 5), round(lon, 5)] for lat, lon in punkte]


def karten_daten(results: list[RepeaterResult], route: Route,
                 coverage: CoverageEstimate | None = None,
                 overlay: Sichtfelder | None = None,
                 *, route_label: str = "Strecke",
                 waypoint_icon: str = "flag") -> dict[str, Any]:
    """Kartendaten für die native Leaflet-Ansicht der GUI (U4) als
    JSON-fähiges Dict — gespeist aus denselben Helfern wie die
    folium-Karte (write_map), overlay ist deren Rückgabewert."""
    lats = [p[0] for p in route.points]
    lons = [p[1] for p in route.points]
    daten: dict[str, Any] = {
        "ebenen": KARTEN_EBENEN,
        "bounds": [[min(lats), min(lons)], [max(lats), max(lons)]],
        "route_label": route_label,
        "stationen": [{"name": s.name, "lat": s.lat, "lon": s.lon}
                      for s in route.stations],
        "stations_icon": waypoint_icon,
        "stile": {str(status): {"farbe": farbe, "dash": dash,
                                "label": label}
                  for status, (farbe, dash, label) in STATUS_STYLE.items()},
        "marker": [{"lat": _pos(r.device)[0], "lng": _pos(r.device)[1],
                    "farbe": farbe, "tooltip": tooltip, "popup": popup,
                    # Rufzeichen einzeln: die Einzelfeld-Legende benennt
                    # das Relais, der Tooltip trägt noch Abstand und Modus
                    "rufzeichen": r.device.callsign}
                   for r, farbe, tooltip, popup in _marker_infos(results)],
        "segmente": None,
        "route": None,
        "overlay": None,
        # Einzelfelder, indexgleich mit "marker" — None, wo kein
        # Sichtfeld vorliegt (leeres Feld, oder Lauf ohne Geländemodell)
        "relais_felder": None,
        "feld_legende": _feld_legende(),
        "legende": None,
    }
    if overlay is not None:
        daten["overlay"] = {"uri": overlay.uri, "bounds": overlay.bounds,
                            "name": OVERLAY_NAME}
        daten["relais_felder"] = [
            None if f is None else {"uri": f.uri, "bounds": f.bounds}
            for f in overlay.felder]
    if coverage is not None and coverage.samples:
        listed = {r.device.callsign for r in results}
        daten["segmente"] = [
            {"status": str(status), "punkte": _runde_punkte(pts),
             "tooltip": tooltip}
            for status, pts, tooltip in _segment_infos(route, coverage,
                                                       listed)]
        modus_label, marker_note = _legende_infos(results)
        daten["legende"] = {
            "modus_label": modus_label,
            "marker_note": marker_note,
            "sichtfelder": overlay is not None,
            # Zeilen wie in _legend() der folium-Karte — Wortlaut bleibt
            # hier die eine Quelle
            "linien": [
                {"farbe": STATUS_STYLE[st][0], "dash": STATUS_STYLE[st][1],
                 "text": txt}
                for st, txt in ((LOS, "Sicht (durchgezogen)"),
                                (MARGINAL, "Grenzbereich (gestrichelt)"),
                                (SHADOW, "Schatten (gepunktet)"))],
        }
    else:
        daten["route"] = _runde_punkte(route.points)
    return daten
