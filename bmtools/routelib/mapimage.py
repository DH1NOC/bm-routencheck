"""Statisches Kartenbild für den PDF-Export (U7, GUI-UMBAU.md).

Komponiert per Pillow aus OSM-Kacheln (gecacht wie die Höhenkacheln,
mit identifizierendem User-Agent), Routen-Segmenten, Abdeckungs-
Overlay, Relais-/Wegpunkt-Markern, Maßstabsleiste und Attribution.

Eingabe ist bewusst das karten_daten-Payload aus mapview (U4) — die
Leaflet-Ansicht der GUI und dieses Bild zeichnen damit aus exakt
derselben Quelle (Segmente, Stile, Overlay, Marker) und können nicht
auseinanderlaufen; der PDF-Export (U8) rendert direkt daraus.
"""
from __future__ import annotations

import base64
import io
import itertools
import math
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont
from platformdirs import user_cache_dir

# tile.openstreetmap.de wie die Leaflet-Ansicht (keine Referer-Pflicht,
# s. mapview.write_map); höflicher Umgang ist Pflicht (Risiken,
# GUI-UMBAU.md): identifizierender UA, Disk-Cache, moderater Zoom.
KACHEL_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
USER_AGENT = "bmtools/0.1 (Amateurfunk-Tool; Kontakt: cnohl@gmx.de)"
KACHEL_PX = 256
MAX_PARALLEL_DOWNLOADS = 8
DOWNLOAD_VERSUCHE = 3
MIN_ZOOM = 3
# Moderat gekappt (Tile-Server-Höflichkeit): 14 reicht für lesbare
# Ortsnamen im 300-dpi-Druck, Hauszoom braucht keine Route
MAX_ZOOM = 14

# Marker-Füllfarben — dieselbe Palette wie .kmarker in stil.css
# (CVD-sicher, ohne Rot/Grün-Paar)
MARKER_FARBEN = {"dmr": "#0072B2", "fm": "#E69F00",
                 "grenz": "#808A93", "station": "#D55E00"}

ATTRIBUTION = "© OpenStreetMap-Mitwirkende"


class KartenbildFehler(RuntimeError):
    """Kartenkacheln nicht verfügbar (Netz/Quelle)."""


def kachel_cache_dir() -> Path:
    """Basisordner des Kachel-Caches (auch für cache_admin)."""
    return Path(user_cache_dir("bmtools")) / "osm-kacheln"


# ---------------------------------------------------------- Geometrie

def _merc_px(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web-Mercator: Weltpixel-Koordinaten bei 256er-Kacheln."""
    scale = KACHEL_PX * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    lat_r = math.radians(min(85.05112878, max(-85.05112878, lat)))
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r))
         / math.pi) / 2.0 * scale
    return x, y


def _zoom_fuer_bounds(bounds: list[list[float]], max_b: int,
                      max_h: int) -> int:
    """Größter Zoom, bei dem die Bounds ins Zielmaß passen."""
    (lat_min, lon_min), (lat_max, lon_max) = bounds
    for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        x0, y1 = _merc_px(lat_min, lon_min, zoom)
        x1, y0 = _merc_px(lat_max, lon_max, zoom)
        if x1 - x0 <= max_b and y1 - y0 <= max_h:
            return zoom
    return MIN_ZOOM


def _meter_pro_pixel(lat: float, zoom: int) -> float:
    return (40075016.686 * math.cos(math.radians(lat))
            / (KACHEL_PX * (2 ** zoom)))


def _massstab_laenge_m(mpp: float, ziel_px: int = 130) -> float:
    """Runde Maßstabslänge (1/2/5·10^n Meter) nahe ziel_px."""
    roh = mpp * ziel_px
    zehner = 10 ** math.floor(math.log10(roh))
    for faktor in (5, 2, 1):
        if faktor * zehner <= roh:
            return faktor * zehner
    return zehner


# ------------------------------------------------------- Kachel-Lader

class KachelLader:
    """Lädt und cached OSM-Kacheln (Muster wie terrain.TerrainModel)."""

    def __init__(self, zoom: int) -> None:
        self.zoom = zoom
        self.cache_dir = kachel_cache_dir() / str(zoom)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(timeout=30,
                                  headers={"User-Agent": USER_AGENT})
        self._lock = threading.Lock()
        self.geladen = 0  # Downloads dieses Laufs (Tests/Diagnose)

    def _pfad(self, tx: int, ty: int) -> Path:
        return self.cache_dir / f"{tx}_{ty}.png"

    def _download(self, tx: int, ty: int) -> None:
        pfad = self._pfad(tx, ty)
        if pfad.exists():
            return
        for versuch in range(1, DOWNLOAD_VERSUCHE + 1):
            try:
                r = self._http.get(
                    KACHEL_URL.format(z=self.zoom, x=tx, y=ty))
                break
            except httpx.HTTPError as e:
                if versuch == DOWNLOAD_VERSUCHE:
                    raise KartenbildFehler(
                        f"Kartenkachel {self.zoom}/{tx}/{ty} nach "
                        f"{DOWNLOAD_VERSUCHE} Versuchen nicht ladbar "
                        f"({e.__class__.__name__})") from e
                time.sleep(versuch)
        if r.status_code != 200:
            raise KartenbildFehler(
                f"Kartenkachel {self.zoom}/{tx}/{ty} nicht ladbar "
                f"(HTTP {r.status_code})")
        # Atomar schreiben: der Disk-Cache wird von Threads geteilt
        tmp = pfad.with_name(
            f"{pfad.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(r.content)
        os.replace(tmp, pfad)
        with self._lock:
            self.geladen += 1

    def lade(self, keys: list[tuple[int, int]],
             progress: Callable[[int, int], None] | None = None,
             ) -> dict[tuple[int, int], Image.Image]:
        fehlend = [k for k in keys if not self._pfad(*k).exists()]
        if fehlend:
            if progress:
                progress(0, len(fehlend))
            fertig = 0

            def laden(tx: int, ty: int) -> None:
                nonlocal fertig
                self._download(tx, ty)
                if progress:
                    with self._lock:
                        fertig += 1
                        stand = fertig
                    progress(stand, len(fehlend))

            with ThreadPoolExecutor(
                    max_workers=min(MAX_PARALLEL_DOWNLOADS,
                                    len(fehlend))) as pool:
                for f in [pool.submit(laden, tx, ty)
                          for tx, ty in fehlend]:
                    f.result()
        return {k: Image.open(self._pfad(*k)).convert("RGB")
                for k in keys}


# -------------------------------------------------------- Zeichnung

def _gestrichelte_linie(draw: ImageDraw.ImageDraw,
                        punkte: list[tuple[float, float]], farbe: str,
                        breite: int, muster: str | None,
                        faktor: float = 1.0) -> None:
    """Polylinie mit Leaflet-Dash-Muster ("10,6") — PIL kennt keine
    Strichelung, daher entlang der Linie auf-/absetzen. faktor
    skaliert das Muster mit der Ausgabe-Auflösung (Druck)."""
    if not muster:
        draw.line(punkte, fill=farbe, width=breite, joint="curve")
        return
    laengen = [float(m) * faktor for m in muster.split(",")]
    an = True
    rest = laengen[0]
    idx = 0
    for (x0, y0), (x1, y1) in itertools.pairwise(punkte):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg == 0:
            continue
        t = 0.0
        while t < seg:
            schritt = min(rest, seg - t)
            if an:
                xa = x0 + (x1 - x0) * (t / seg)
                ya = y0 + (y1 - y0) * (t / seg)
                xb = x0 + (x1 - x0) * ((t + schritt) / seg)
                yb = y0 + (y1 - y0) * ((t + schritt) / seg)
                draw.line([(xa, ya), (xb, yb)], fill=farbe, width=breite)
            t += schritt
            rest -= schritt
            if rest <= 0:
                idx = (idx + 1) % len(laengen)
                rest = laengen[idx]
                an = not an


def _schrift(groesse: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(groesse)
    except TypeError:  # Pillow < 10.1: load_default ohne Größe
        return ImageFont.load_default()


def _textbox(draw: ImageDraw.ImageDraw, xy: tuple[float, float],
             text: str, schrift: Any, *, anker: str) -> None:
    """Text mit halbtransparent weißem Kasten (Lesbarkeit auf Karte)."""
    box = draw.textbbox(xy, text, font=schrift, anchor=anker)
    draw.rectangle((box[0] - 4, box[1] - 2, box[2] + 4, box[3] + 2),
                   fill=(255, 255, 255, 210))
    draw.text(xy, text, font=schrift, fill="#111111", anchor=anker)


def _marker(draw: ImageDraw.ImageDraw, x: float, y: float, farbe: str,
            radius: float, rand: int) -> None:
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 fill=farbe, outline="#ffffff", width=rand)


def _nummern_marker(draw: ImageDraw.ImageDraw, x: float, y: float,
                    farbe: str, text: str, schrift: Any,
                    f: float) -> None:
    """Relais-Marker als nummerierte Pille (U8-Befund 2026-07-20:
    Nummer statt Punkt — die Nr. steht auch in der PDF-Tabelle)."""
    box = draw.textbbox((x, y), text, font=schrift, anchor="mm")
    pad_x, pad_y = 5 * f, 3 * f
    draw.rounded_rectangle(
        (box[0] - pad_x, box[1] - pad_y, box[2] + pad_x, box[3] + pad_y),
        radius=7 * f, fill=farbe, outline="#ffffff",
        width=max(1, round(1.5 * f)))
    draw.text((x, y), text, font=schrift, fill="#ffffff", anchor="mm")


# ------------------------------------------------------------ Aufbau

def render_kartenbild(karte: dict[str, Any], *,
                      max_breite_px: int = 1600,
                      max_hoehe_px: int = 1200,
                      rand_px: int = 40,
                      fuellen: bool = False,
                      lader: KachelLader | None = None,
                      tile_progress: Callable[[int, int], None] | None = None,
                      ) -> Image.Image:
    """Kartenbild aus dem karten_daten-Payload (mapview, U4).

    fuellen=True liefert exakt max_breite×max_hoehe (Route zentriert,
    Umgebung füllt auf) — fürs PDF, das die volle Papierbreite nutzt
    (U8-Befund 2026-07-20). Stilgrößen (Linien, Marker, Schrift)
    skalieren mit der Bildbreite, damit 300-dpi-Ausgaben lesbar
    bleiben. lader: injizierbar für Tests; tile_progress wie beim
    Geländemodell.
    """
    bounds = karte["bounds"]
    zoom = _zoom_fuer_bounds(bounds, max_breite_px - 2 * rand_px,
                             max_hoehe_px - 2 * rand_px)
    if lader is None:
        lader = KachelLader(zoom)
    else:
        zoom = lader.zoom

    (lat_min, lon_min), (lat_max, lon_max) = bounds
    x0, y1 = _merc_px(lat_min, lon_min, zoom)
    x1, y0 = _merc_px(lat_max, lon_max, zoom)
    if fuellen:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x0, x1 = cx - max_breite_px / 2, cx + max_breite_px / 2
        y0, y1 = cy - max_hoehe_px / 2, cy + max_hoehe_px / 2
    else:
        x0 -= rand_px
        y0 -= rand_px
        x1 += rand_px
        y1 += rand_px
    breite = max(1, round(x1 - x0))
    hoehe = max(1, round(y1 - y0))
    # Stil-Skalierung: 800 px ≈ Bildschirmmaßstab (Faktor 1)
    f = max(1.0, breite / 800.0)

    def px(lat: float, lon: float) -> tuple[float, float]:
        wx, wy = _merc_px(lat, lon, zoom)
        return wx - x0, wy - y0

    # Kachel-Mosaik
    tx0, ty0 = int(x0 // KACHEL_PX), int(y0 // KACHEL_PX)
    tx1, ty1 = int(x1 // KACHEL_PX), int(y1 // KACHEL_PX)
    n = 2 ** zoom
    keys = [(tx % n, ty) for ty in range(ty0, ty1 + 1)
            for tx in range(tx0, tx1 + 1)
            if 0 <= ty < n]
    kacheln = lader.lade(keys, tile_progress)
    bild = Image.new("RGB", (breite, hoehe), "#d9dee3")
    for ty in range(ty0, ty1 + 1):
        if not 0 <= ty < n:
            continue
        for tx in range(tx0, tx1 + 1):
            kachel = kacheln.get((tx % n, ty))
            if kachel is not None:
                bild.paste(kachel, (int(tx * KACHEL_PX - x0),
                                    int(ty * KACHEL_PX - y0)))
    bild = bild.convert("RGBA")

    # Abdeckungs-Overlay (vorgerechnetes Raster, Deckkraft wie Leaflet)
    overlay = karte.get("overlay")
    if overlay:
        b64 = overlay["uri"].partition("base64,")[2]
        raster = Image.open(io.BytesIO(base64.b64decode(b64))) \
            .convert("RGBA")
        (o_lat_min, o_lon_min), (o_lat_max, o_lon_max) = overlay["bounds"]
        ox0, oy1 = px(o_lat_min, o_lon_min)
        ox1, oy0 = px(o_lat_max, o_lon_max)
        ziel_b = max(1, round(ox1 - ox0))
        ziel_h = max(1, round(oy1 - oy0))
        raster = raster.resize((ziel_b, ziel_h),
                               Image.Resampling.BILINEAR)
        alpha = raster.getchannel("A").point(lambda a: int(a * 0.8))
        raster.putalpha(alpha)
        ebene = Image.new("RGBA", bild.size, (0, 0, 0, 0))
        ebene.paste(raster, (round(ox0), round(oy0)), raster)
        bild = Image.alpha_composite(bild, ebene)

    draw = ImageDraw.Draw(bild)

    # Route: Statussegmente wie die Leaflet-Ansicht, sonst Fallback-Linie
    stile = karte.get("stile") or {}
    if karte.get("segmente"):
        for seg in karte["segmente"]:
            stil = stile.get(str(seg["status"]), {})
            punkte = [px(lat, lon) for lat, lon in seg["punkte"]]
            if len(punkte) > 1:
                _gestrichelte_linie(draw, punkte,
                                    stil.get("farbe", "#0072B2"),
                                    max(2, round(5 * f)),
                                    stil.get("dash"), f)
    elif karte.get("route"):
        punkte = [px(lat, lon) for lat, lon in karte["route"]]
        if len(punkte) > 1:
            draw.line(punkte, fill="#cc0000", width=max(2, round(3 * f)),
                      joint="curve")

    # Wegpunkte als vermilion Kreise, Relais als nummerierte Pillen in
    # den Statusfarben — die Nr. (1-basiert, Zeilen-Reihenfolge) steht
    # auch in der PDF-Tabelle (U8-Befund)
    marker_schrift = _schrift(round(13 * f))
    for s in karte.get("stationen") or []:
        sx, sy = px(s["lat"], s["lon"])
        _marker(draw, sx, sy, MARKER_FARBEN["station"], 10 * f,
                max(2, round(2 * f)))
    for i, mk in enumerate(karte.get("marker") or []):
        mx, my = px(mk["lat"], mk["lng"])
        _nummern_marker(draw, mx, my,
                        MARKER_FARBEN.get(mk["farbe"], "#0072B2"),
                        str(i + 1), marker_schrift, f)

    # Maßstabsleiste unten links
    mitte_lat = (lat_min + lat_max) / 2
    mpp = _meter_pro_pixel(mitte_lat, zoom)
    laenge_m = _massstab_laenge_m(mpp, round(130 * f))
    laenge_px = laenge_m / mpp
    schrift = _schrift(round(14 * f))
    strich = max(2, round(3 * f))
    sx0, sy0 = 16 * f, hoehe - 22 * f
    draw.rectangle((sx0 - 6 * f, sy0 - 24 * f,
                    sx0 + laenge_px + 6 * f, sy0 + 10 * f),
                   fill=(255, 255, 255, 210))
    draw.line([(sx0, sy0), (sx0 + laenge_px, sy0)], fill="#111111",
              width=strich)
    for ende in (sx0, sx0 + laenge_px):
        draw.line([(ende, sy0 - 6 * f), (ende, sy0 + 4 * f)],
                  fill="#111111", width=strich)
    beschriftung = (f"{laenge_m / 1000:g} km" if laenge_m >= 1000
                    else f"{laenge_m:g} m")
    draw.text((sx0 + laenge_px / 2, sy0 - 9 * f), beschriftung,
              font=schrift, fill="#111111", anchor="ms")

    # Attribution unten rechts (Pflicht)
    _textbox(draw, (breite - 8 * f, hoehe - 6 * f), ATTRIBUTION,
             schrift, anker="rs")

    return bild.convert("RGB")
