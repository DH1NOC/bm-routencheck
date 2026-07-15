"""Parser für die CGI-Antworten von relaislisten.darc.de (DL3EL).

Die Antworten sind "schmutziges" HTML (verifiziert 2026-07-15):
ISO-8859-1, Datenzeilen enden auf ``<br>``, HTML-Entities auch ohne
Schluss-Semikolon (``F&#252rth``), Dezimalkomma bei Frequenzen. Das CSV
(``printas=csv``) hat Koordinaten nur bogenminutengenau (``49&deg;28'N``)
— und weil ``&deg;`` selbst ein Semikolon enthält, müssen Entities vor
dem Spalten-Split dekodiert werden. Die GPX-Ausgabe (``printas=gpx``)
derselben Query liefert dezimale Koordinaten (4 Nachkommastellen),
aber mit HTML-Präambel vor dem XML und ``<br>``-Präfix je Zeile;
gemergt wird über (Rufzeichen, Ausgabefrequenz).

Zeilen ohne parsebare Frequenzen werden verworfen — in den Livedaten
betrifft das einzelne Auslands-Einträge (leere Input-Spalte bei OK/ON,
Ausreißer wie ``#WERT!`` oder ``Simplex`` als Input).
"""
from __future__ import annotations

import html
import re
from dataclasses import replace

from .models import FmRepeater, fm_repeater_id

# Call;QRG;Input;Locator;Info;Breite;Länge;CTCSS;Mode/Node;Entfernung
_CSV_COLUMNS = 10

_ARCMIN_RE = re.compile(r"^(\d+)°(\d+)'([NSEW])$")
_WPT_RE = re.compile(
    r"<wpt lat=\"([+-][\d.]+)\" lon=\"([+-][\d.]+)\">\s*"
    r"<name>([^<]*)</name>\s*<cmt>([^<]*)</cmt>",
    re.S,
)


def _freq_mhz(value: str) -> float | None:
    """Frequenzspalte ("438,625") → MHz; leer/Unsinn ("#WERT!") = None."""
    try:
        f = float(value.strip().replace(",", "."))
    except ValueError:
        return None
    return f if f > 0 else None


def _ctcss_hz(value: str) -> float | None:
    """CTCSS-Spalte ("88,5Hz") → Hz; leer = kein Ton."""
    return _freq_mhz(value.removesuffix("Hz"))


def _arcmin_coord(value: str) -> float | None:
    """Bogenminuten-Koordinate ("49°28'N") → Dezimalgrad."""
    m = _ARCMIN_RE.match(value.strip())
    if not m:
        return None
    deg = int(m.group(1)) + int(m.group(2)) / 60
    return -deg if m.group(3) in "SW" else deg


def _freq_key(callsign: str, mhz: float) -> tuple[str, float]:
    """Merge-/Dedupe-Schlüssel; rundet, weil die Listen dieselbe QRG mal
    als 438,5125 und mal als 438,51250 schreiben."""
    return callsign, round(mhz, 4)


def parse_csv(text: str) -> list[FmRepeater]:
    """CSV-Antwort (dekodiertes ISO-8859-1) → FmRepeater-Liste.

    Koordinaten zunächst bogenminutengenau; merge_gpx_coords() verfeinert
    sie. Reihenfolge (nach Entfernung) bleibt erhalten, Dubletten der
    Quelle (DL3EL- und fr-Liste überschneiden sich) bleiben drin —
    dedupe() ist ein eigener Schritt.
    """
    repeaters: list[FmRepeater] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.endswith("<br>"):
            continue  # HTML-Rumpf, Fußnoten
        parts = html.unescape(line.removesuffix("<br>")).split(";")
        if len(parts) < _CSV_COLUMNS or parts[0].startswith("Call"):
            continue  # Kopfzeile, Copy&Paste-Hinweis am Ende
        if len(parts) > _CSV_COLUMNS:
            # Info-Spalte enthielt Semikolons → Mitte wieder zusammenfassen
            parts = [*parts[:4], ";".join(parts[4:len(parts) - 5]), *parts[-5:]]
        call, qrg, inp, locator, info, breite, laenge, ctcss, _mode, _dist = parts
        tx = _freq_mhz(qrg)
        rx = _freq_mhz(inp)
        lat = _arcmin_coord(breite)
        lng = _arcmin_coord(laenge)
        if tx is None or rx is None or lat is None or lng is None:
            continue
        callsign = call.strip()
        repeaters.append(FmRepeater(
            id=fm_repeater_id(callsign, tx),
            callsign=callsign, tx_mhz=tx, rx_mhz=rx,
            ctcss_hz=_ctcss_hz(ctcss), lat=lat, lng=lng,
            city=info.strip(), locator=locator.strip(),
        ))
    return repeaters


def parse_gpx_coords(text: str) -> dict[tuple[str, float], tuple[float, float]]:
    """GPX-Antwort → {(Call, QRG): (lat, lng)} mit dezimalen Koordinaten.

    Waypoint-Name ist das Rufzeichen, das erste Token des <cmt> die
    Ausgabefrequenz — zusammen genau der CSV-Schlüssel. Der Regex-Ansatz
    umgeht HTML-Präambel und <br>-Präfixe, ein XML-Parser scheitert daran.
    """
    coords: dict[tuple[str, float], tuple[float, float]] = {}
    for lat, lng, name, cmt in _WPT_RE.findall(text):
        mhz = _freq_mhz(cmt.split()[0] if cmt.split() else "")
        if mhz is None:
            continue  # z. B. Waypoint "Kartenmitte"
        coords[_freq_key(name.strip(), mhz)] = (float(lat), float(lng))
    return coords


def merge_gpx_coords(
    repeaters: list[FmRepeater],
    coords: dict[tuple[str, float], tuple[float, float]],
) -> list[FmRepeater]:
    """Ersetzt Bogenminuten-Koordinaten durch die dezimalen aus dem GPX;
    Relais ohne GPX-Treffer behalten die groben Werte."""
    merged = []
    for r in repeaters:
        latlng = coords.get(_freq_key(r.callsign, r.tx_mhz))
        merged.append(replace(r, lat=latlng[0], lng=latlng[1]) if latlng else r)
    return merged


def dedupe(repeaters: list[FmRepeater]) -> list[FmRepeater]:
    """Dubletten über (Rufzeichen, Ausgabefrequenz) entfernen.

    Es bleibt die Position des ersten Treffers (Antworten sind nach
    Entfernung sortiert), aber ein späterer Eintrag MIT CTCSS ersetzt
    einen tonlosen: DL3EL- und fr-Liste beschreiben dasselbe Relais
    unterschiedlich vollständig (Beispiel DB0THM — nur der fr-Eintrag
    trägt den 88,5-Hz-Ton)."""
    index: dict[tuple[str, float], int] = {}
    unique: list[FmRepeater] = []
    for r in repeaters:
        key = _freq_key(r.callsign, r.tx_mhz)
        if key not in index:
            index[key] = len(unique)
            unique.append(r)
        elif unique[index[key]].ctcss_hz is None and r.ctcss_hz is not None:
            unique[index[key]] = r
    return unique
