"""Dateien und Ordner mit dem Standardprogramm des Systems öffnen.

webbrowser.open() öffnete unter Windows im PyInstaller-Binary den
Standardbrowser nicht (Beta-Befund 2026-07-17): Die Browser-Erkennung
des Moduls greift dort ins Leere. os.startfile() bzw. open/xdg-open sind
der native „Doppelklick" und nutzen immer die Systemzuordnung — HTML
landet im Standardbrowser, Ordner im Dateimanager.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ausweichkette unter Linux, wenn xdg-open nicht zum Ziel führt. gio ist
# auf GTK-Desktops immer da; danach die Dateimanager der verbreiteten
# Desktops direkt. Reihenfolge = Wahrscheinlichkeit, nicht Vorliebe.
LINUX_OEFFNER: tuple[tuple[str, ...], ...] = (
    ("xdg-open",),
    ("gio", "open"),
    ("nemo",),        # Cinnamon (Mint)
    ("nautilus",),    # GNOME
    ("dolphin",),     # KDE
    ("thunar",),      # XFCE
    ("pcmanfm",),     # LXDE/LXQt
)


class OeffnenFehler(RuntimeError):
    """Das Ziel ließ sich mit keinem Weg öffnen.

    Trägt die versuchten Kommandos samt Ergebnis mit — genau die
    Angabe, die einem Fehlerbericht sonst fehlt.
    """

    def __init__(self, ziel: Path, versuche: list[str]) -> None:
        self.ziel = ziel
        self.versuche = versuche
        super().__init__(f"{ziel} ließ sich nicht öffnen "
                         f"({', '.join(versuche) or 'kein Öffner gefunden'})")

    @property
    def kurz(self) -> str:
        """Einzeiler für die Statusleiste."""
        return (f"Konnte nicht geöffnet werden ({'; '.join(self.versuche)})"
                if self.versuche else
                "Konnte nicht geöffnet werden (kein Öffner gefunden)")


def kind_umgebung() -> dict[str, str]:
    """Umgebung für Fremdprozesse, von PyInstaller-Resten befreit.

    Das Linux-Binary ist --onefile mit gebündeltem Qt. PyInstaller setzt
    dabei LD_LIBRARY_PATH auf sein Entpackverzeichnis und sichert den
    ursprünglichen Wert in LD_LIBRARY_PATH_ORIG. Ein von hier gestarteter
    Dateimanager erbt das und zöge sich unsere gebündelten Qt-/glib-
    Bibliotheken statt der System-Version — er stirbt dann beim Start,
    und zwar lautlos.
    """
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
                "LD_PRELOAD", "QT_PLUGIN_PATH"):
        original = env.pop(var + "_ORIG", None)
        if original is not None:
            env[var] = original
        elif getattr(sys, "frozen", False):
            # Eingefroren, aber ohne gesicherten Originalwert: die
            # Variable stammt dann von uns und gehört nicht ins Kind.
            env.pop(var, None)
    return env


def _linux_oeffnen(ziel: Path) -> tuple[bool, list[str]]:
    """Ausweichkette abarbeiten.

    Liefert (geöffnet, Protokoll der gescheiterten Versuche). Das
    Erfolgs-Flag ist getrennt, weil eine leere Versuchsliste zweierlei
    heißen kann: gleich beim ersten Anlauf geklappt — oder gar kein
    Öffner installiert.
    """
    versuche: list[str] = []
    for kommando in LINUX_OEFFNER:
        if shutil.which(kommando[0]) is None:
            continue
        try:
            fertig = subprocess.run(
                [*kommando, str(ziel)], check=False, env=kind_umgebung(),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=20)
        except (OSError, subprocess.SubprocessError) as e:
            versuche.append(f"{kommando[0]}: {e.__class__.__name__}")
            continue
        if fertig.returncode == 0:
            return True, []
        versuche.append(f"{kommando[0]}: Code {fertig.returncode}")
    return False, versuche


def system_oeffnen(ziel: Path) -> None:
    """Datei oder Ordner mit dem zugeordneten Standardprogramm öffnen.

    Wirft OeffnenFehler, wenn kein Weg zum Ziel führte. Aufrufer, denen
    das nur Komfort ist, fangen ihn ab — die Ausgaben liegen ja auf der
    Platte. Die GUI zeigt ihn dagegen an: Bisher passierte bei einem
    Fehlschlag gar nichts, nicht einmal eine Meldung (Beta-Befund
    2026-07-26, Mint 22.3: »Ordner-Knopf tut nichts«).

    Der Pfad geht immer ABSOLUT hinaus. Ein relativer Pfad wird sonst
    vom Zielprogramm gegen dessen eigenes Arbeitsverzeichnis aufgelöst —
    auf Cinnamon läuft Nemo bereits (es zeichnet den Desktop), der neue
    Aufruf reicht das Argument per DBus an die laufende Instanz weiter,
    und die sitzt woanders.
    """
    ziel = ziel.resolve()
    if sys.platform == "win32":
        try:
            os.startfile(ziel)  # genau der Doppelklick des Explorers
        except OSError as e:
            raise OeffnenFehler(ziel, [f"startfile: {e.strerror or e}"]) from e
        return
    if sys.platform == "darwin":
        try:
            fertig = subprocess.run(["open", str(ziel)], check=False,
                                    env=kind_umgebung(),
                                    stderr=subprocess.PIPE, timeout=20)
        except (OSError, subprocess.SubprocessError) as e:
            raise OeffnenFehler(ziel, [f"open: {e.__class__.__name__}"]) from e
        if fertig.returncode != 0:
            raise OeffnenFehler(ziel, [f"open: Code {fertig.returncode}"])
        return
    geoeffnet, versuche = _linux_oeffnen(ziel)
    if not geoeffnet:
        raise OeffnenFehler(ziel, versuche)


def system_oeffnen_still(ziel: Path) -> OeffnenFehler | None:
    """system_oeffnen für Aufrufer, denen das Öffnen nur Komfort ist —
    liefert den Fehler zurück, statt ihn zu werfen."""
    try:
        system_oeffnen(ziel)
    except OeffnenFehler as e:
        return e
    return None
