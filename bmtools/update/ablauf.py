"""Der komplette Update-Ablauf: suchen → laden → prüfen → tauschen.

Verbindet die geprüften Einzelteile (pruefen/laden/tausch) zu dem, was
GUI und Terminal tatsächlich aufrufen. UI-frei — Fortschritt läuft über
den bekannten (fertig, gesamt)-Callback.
"""
from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from bmtools.version import eigene_version, version_anzeige

from . import laden, tausch
from .pruefen import Angebot, suche_update
from .ziel import beschreibbar, eigenes_programm, plattform

# Name des Arbeitsordners neben dem Ziel (Linux/macOS — und bis 0.4.3
# alle Plattformen; siehe arbeitsordner()).
ARBEITSORDNER = ".bm-update"
TEMP_ARBEITSORDNER = "bm-routencheck-update"


def arbeitsordner(ziel: Path) -> Path:
    """Wo Download und Auspacken stattfinden.

    Linux/macOS: NEBEN dem Ziel, nicht im System-Temp — os.replace kann
    keine Dateisystemgrenzen überschreiten (EXDEV), und /tmp ist oft
    tmpfs, während das Programm woanders liegt. Windows: im System-Temp —
    dort tauscht der cmd-Helfer per »move«, das Dateien notfalls über
    Laufwerksgrenzen kopiert, und neben der Exe irritierten die
    Update-Reste (Nutzerbefund 2026-07-30).
    """
    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / TEMP_ARBEITSORDNER
    return ziel.parent / ARBEITSORDNER


class UpdateFehler(Exception):
    """Sammelfehler für den Ablauf — Text ist nutzertauglich."""


def beim_start_aufraeumen() -> None:
    """Beim Programmstart: Backup der Vorversion verwerfen.

    Dass wir laufen, ist der Beweis für den gelungenen Tausch
    (Nutzerfestlegung: alte Fassung behalten bis zum ersten Erfolg).
    Fehler hier sind belanglos und dürfen den Start nie stören.
    """
    try:
        ziel = eigenes_programm()
        if ziel is not None:
            tausch.alte_fassung_verwerfen(ziel)
            # Reste des letzten Laufs: Arbeitsordner (unter Windows hat
            # der Helfer die neue Exe erst nach unserem Ende dort
            # herausgeholt) und ein Helfer-Skript, das nie zum
            # Selbstlöschen kam
            laden.aufraeumen(arbeitsordner(ziel))
            # Altlast: Bis 0.4.3 lag der Arbeitsordner auf allen
            # Plattformen neben dem Programm — das letzte Update von
            # dort macht noch die Vorversion, also mitputzen.
            laden.aufraeumen(ziel.parent / ARBEITSORDNER)
            tausch.helfer_verwerfen(ziel)
    except Exception:
        pass


def suche(*, mit_vorabversionen: bool = False) -> Angebot | None:
    """Neueres, verifiziertes Angebot — nur im gefrorenen Binary.

    Aus dem Quellcode gestartet gibt es nichts zu tauschen; dort ist
    `git pull` der Weg (DEVELOPER.md „Selbst-Updater“).
    """
    if eigenes_programm() is None:
        return None
    return suche_update(mit_vorabversionen=mit_vorabversionen)


def durchfuehren(angebot: Angebot,
                 fortschritt: Callable[[int, int], None] | None = None,
                 ) -> bool:
    """Angebot einspielen.

    True  = getauscht (Linux/macOS), neustart() startet die neue Fassung
    False = Helfer tauscht nach Prozessende und startet selbst neu
            (Windows) — der Aufrufer muss sich nur noch beenden

    Für den Aufrufer ist beides gleich: neustart() aufrufen (unter
    Windows ein No-op) und sich beenden. Wirft UpdateFehler mit
    nutzertauglichem Text; das Programm auf der Platte ist danach in
    jedem Fall noch startbar (tausch.py).
    """
    ziel = eigenes_programm()
    ziel_plattform = plattform()
    if ziel is None or ziel_plattform is None:
        raise UpdateFehler("Update nur im ausgelieferten Programm möglich — "
                           "im Quellcode-Checkout bitte »git pull«.")
    if not beschreibbar(ziel):
        # Früh scheitern, BEVOR 240 MB geladen sind
        raise UpdateFehler(
            f"Kein Schreibrecht in {ziel.parent} — bitte die neue Version "
            f"von Hand von der Release-Seite laden.")

    arbeit = arbeitsordner(ziel)
    laden.aufraeumen(arbeit)
    arbeit.mkdir(parents=True, exist_ok=True)
    try:
        archiv = laden.hole(angebot, arbeit, fortschritt)
        neu = laden.packe_aus(archiv, arbeit / "neu", ziel_plattform)
        sofort = tausch.ersetze(ziel, neu)
    except (laden.LadeFehler, tausch.TauschFehler) as e:
        laden.aufraeumen(arbeit)
        raise UpdateFehler(str(e)) from e
    if sofort:
        # Getauscht — Reste weg. Unter Windows bleibt der Ordner stehen,
        # der Helfer braucht die neue Exe noch; beim nächsten Start
        # räumt beim_start_aufraeumen() ihn ab.
        laden.aufraeumen(arbeit)
    return sofort


def neustart() -> None:
    """Die neue Fassung starten; der Aufrufer beendet danach diesen
    Prozess (GUI: Fenster zerstören, Terminal: return).

    Unter Windows gibt es nichts zu tun: Dort wartet der Helfer aus
    tausch.py auf unser Prozessende, tauscht und startet die neue Exe
    selbst — ein zweiter Start hier ergäbe zwei Instanzen.
    """
    if sys.platform == "win32":
        return
    ziel = eigenes_programm()
    if ziel is not None:
        tausch.neu_starten(ziel)


def hinweis_zeilen(angebot: Angebot) -> list[str]:
    """Terminal-Hinweis — dieselbe Botschaft wie die Info-Leiste."""
    vorab = " (Vorabversion)" if angebot.vorabversion else ""
    return [f"Version {version_anzeige(angebot.version)}{vorab} ist verfügbar "
            f"(installiert: {version_anzeige(eigene_version())}).",
            "Aktualisieren mit: bmtools --update"]
