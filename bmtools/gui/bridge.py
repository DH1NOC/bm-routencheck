"""JS-Bridge des GUI-Fensters (pywebview js_api).

Alle öffentlichen Methoden sind im Frontend als
window.pywebview.api.<name>() aufrufbar und geben JSON-fähige Dicts
zurück: Startzustand, Feld-/Formular-Validierung, der native
GPX-Dateidialog (G3) sowie Start/Abbruch des Pipeline-Laufs und die
Zustellung von Dialog-Antworten (G4). Ereignisse in Gegenrichtung
laufen als bmEreignis()-Aufrufe über evaluate_js.

Die Validierung nutzt dieselben Parser wie der Terminal-Assistent
(bahn_link.extract_vbid, rail.cli-Zeitformate) — GUI und Terminal
dürfen nicht unterschiedlich urteilen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bmtools.rail.bahn_link import BahnLinkError, extract_vbid

from .lauf import Lauf
from .melder import Ereignis

# Feldschlüssel im Fehler-Dict, der sich nicht auf ein einzelnes
# Eingabefeld bezieht (das Frontend zeigt ihn unter dem Formular).
FORMULAR = "_formular"


def _zeit_fehler(text: str) -> str | None:
    """Zeitangabe prüfen; None = gültig. Nutzt die Terminal-Formate."""
    # Kandidat für einen gemeinsamen Ort (G4): _parse_time lebt noch im
    # Terminal-Assistenten, ist aber die eine Wahrheit für Zeitformate.
    from bmtools.rail.cli import _parse_time
    try:
        _parse_time(text)
        return None
    except argparse.ArgumentTypeError:
        return ("Format: 'JJJJ-MM-TT HH:MM', 'TT.MM.JJJJ HH:MM' "
                "oder 'HH:MM'")


def _bahn_link_fehler(link: str) -> str | None:
    try:
        extract_vbid(link)
        return None
    except BahnLinkError:
        return "Kein bahn.de-Verbindungslink (es fehlt …?vbid=…)"


def _routen_link_fehler(link: str) -> str | None:
    if link.startswith(("http://", "https://")):
        return None
    return "Bitte einen vollständigen Link einfügen (https://…)"


def pruefe_formular(tool: str, daten: dict[str, Any]) -> dict[str, str]:
    """Formulardaten eines Tools prüfen; leeres Dict = alles gültig.

    Schlüssel der Rückgabe sind die Feld-IDs des Frontends
    (z. B. 'bahn-zeit') bzw. FORMULAR für Formular-weite Fehler."""
    fehler: dict[str, str] = {}
    link = str(daten.get("link", "")).strip()
    von = str(daten.get("von", "")).strip()
    nach = str(daten.get("nach", "")).strip()

    if tool == "bahn":
        zeit = str(daten.get("zeit", "")).strip()
        if zeit and (f := _zeit_fehler(zeit)):
            fehler["bahn-zeit"] = f
        if link:
            if f := _bahn_link_fehler(link):
                fehler["bahn-link"] = f
        elif not (von and nach):
            fehler[FORMULAR] = ("Entweder bahn.de-Link einfügen oder "
                                "Start- und Zielbahnhof angeben.")
    elif tool in ("auto", "rad"):
        gpx = str(daten.get("gpx", "")).strip()
        if link:
            if f := _routen_link_fehler(link):
                fehler[f"{tool}-link"] = f
        elif gpx:
            if not Path(gpx).is_file():
                fehler[f"{tool}-gpx"] = f"Datei nicht gefunden: {gpx}"
        elif not (von and nach):
            fehler[FORMULAR] = ("Entweder Routen-Link einfügen, eine "
                                "GPX-Datei wählen oder Start und Ziel "
                                "angeben.")
    else:
        fehler[FORMULAR] = f"Unbekanntes Tool: {tool!r}"
    return fehler


class Bridge:
    """Zustand des Fensters plus die aus JS aufrufbaren Methoden.

    Attribute mit Unterstrich exportiert pywebview nicht — _fenster
    (webview.Window, wird nach create_window gesetzt) bleibt intern."""

    def __init__(self, tool: str | None = None) -> None:
        self._tool = tool
        self._fenster: Any = None
        self._lauf: Lauf | None = None

    def _sende_ereignis(self, ereignis: Ereignis) -> None:
        """Ereignis an das Frontend (threadsicher via evaluate_js)."""
        if self._fenster is not None:
            self._fenster.evaluate_js(
                f"bmEreignis({json.dumps(ereignis, ensure_ascii=False)})")

    def init_zustand(self) -> dict[str, Any]:
        """Startzustand fürs Frontend (aufgerufen bei pywebviewready)."""
        return {"tab": self._tool or "bahn"}

    def pruefe_feld(self, tool: str, feld: str, wert: str) -> dict[str, Any]:
        """Einzelfeld-Prüfung beim Verlassen des Felds (Live-Feedback)."""
        wert = wert.strip()
        fehler: str | None = None
        if wert:
            if feld == "zeit":
                fehler = _zeit_fehler(wert)
            elif feld == "link" and tool == "bahn":
                fehler = _bahn_link_fehler(wert)
            elif feld == "link":
                fehler = _routen_link_fehler(wert)
        return {"ok": fehler is None, "fehler": fehler}

    def waehle_gpx(self) -> dict[str, str] | None:
        """Nativer Datei-Dialog für die GPX-Auswahl; None = abgebrochen."""
        if self._fenster is None:
            return None
        import webview
        auswahl = self._fenster.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=("GPX-Dateien (*.gpx)", "Alle Dateien (*.*)"))
        if not auswahl:
            return None
        return {"pfad": str(auswahl[0])}

    def start_lauf(self, tool: str, daten: dict[str, Any]) -> dict[str, Any]:
        """Formular prüfen und den Lauf im Hintergrund-Thread starten."""
        if self._lauf is not None and self._lauf.laeuft():
            return {"ok": False,
                    "hinweis": "Es läuft bereits eine Suche — erst "
                               "abbrechen oder abwarten."}
        fehler = pruefe_formular(tool, daten)
        if fehler:
            return {"ok": False, "fehler": fehler}
        self._lauf = Lauf(self._sende_ereignis)
        self._lauf.starten(tool, daten)
        return {"ok": True}

    def antwort(self, frage_id: int, wert: Any) -> None:
        """Dialog-Antwort ans wartende Pipeline-Thread durchstellen;
        wert=null bedeutet: Dialog abgebrochen."""
        if self._lauf is not None:
            self._lauf.melder.antwort(int(frage_id), wert)

    def abbrechen(self) -> None:
        """Laufende Suche abbrechen (wirkt an der nächsten Meldestelle)."""
        if self._lauf is not None:
            self._lauf.abbrechen()
