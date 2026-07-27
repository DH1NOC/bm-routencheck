"""Das laufende Programm durch die neue Fassung ersetzen.

Der einzige Teil, der etwas kaputt machen kann — entsprechend
vorsichtig:

* Die alte Fassung wird **nicht gelöscht**, sondern nur zur Seite
  geschoben (`<name>.vorher`). Erst wenn die neue einmal gestartet ist,
  räumt `alte_fassung_verwerfen()` sie weg. Startet sie nicht, liegt
  das Alte noch da und lässt sich von Hand zurückschieben.
* Geprüft wird vorher, ob der enthaltende Ordner beschreibbar ist.
  Ist er es nicht, wird gar nicht erst angefangen.

Plattform-Eigenheiten:

* **Linux** — `os.replace()` über das laufende Binary geht: Der Prozess
  hält das alte Inode, der Name zeigt danach auf die neue Datei.
* **macOS** — dasselbe Spiel mit dem `.app`-Ordner. Vor dem Tausch
  prüft `codesign --verify`, ob das neue Bundle unversehrt signiert
  ist; ein selbst geladenes Archiv trägt kein Quarantäne-Attribut,
  Gatekeeper prüft also nicht für uns mit.
* **Windows** — eine laufende `.exe` ist gesperrt. Ein kleiner
  Helfer wartet, bis wir beendet sind, tauscht, startet neu und löscht
  sich selbst.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .ziel import beschreibbar

BACKUP_ENDUNG = ".vorher"


class TauschFehler(Exception):
    """Ersetzen nicht möglich oder gescheitert."""


def backup_pfad(ziel: Path) -> Path:
    return ziel.with_name(ziel.name + BACKUP_ENDUNG)


def alte_fassung_verwerfen(ziel: Path) -> bool:
    """Beim Start aufrufen: Wir laufen, also hat der Tausch geklappt.

    Dass dieser Code überhaupt ausgeführt wird, IST der Beweis für den
    erfolgreichen Start — eine eigene Fehlstart-Erkennung wäre nur eine
    weitere Fehlerquelle.
    """
    alt = backup_pfad(ziel)
    if not alt.exists():
        return False
    if alt.is_dir():
        shutil.rmtree(alt, ignore_errors=True)
    else:
        alt.unlink(missing_ok=True)
    return True


def _signatur_pruefen(bundle: Path) -> None:
    """macOS: Ist das neue Bundle unversehrt signiert?"""
    try:
        fertig = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(bundle)],
            capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        raise TauschFehler(f"codesign nicht ausführbar: {e}") from e
    if fertig.returncode != 0:
        meldung = fertig.stderr.decode(errors="replace").strip()
        raise TauschFehler(
            f"Neues Bundle ist nicht gültig signiert — Tausch abgebrochen "
            f"({meldung or 'codesign Code ' + str(fertig.returncode)})")


def _windows_helfer(ziel: Path, neu: Path, alt: Path) -> Path:
    """Batch-Datei, die nach unserem Ende tauscht und neu startet."""
    skript = ziel.with_name("bm-update.cmd")
    skript.write_text(
        "@echo off\r\n"
        "rem Von BM-Routencheck erzeugt; loescht sich am Ende selbst.\r\n"
        ":warten\r\n"
        f'tasklist /FI "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" '
        ">nul\r\n"
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto warten\r\n"
        ")\r\n"
        f'move /Y "{ziel}" "{alt}" >nul\r\n'
        f'move /Y "{neu}" "{ziel}" >nul\r\n'
        f'if errorlevel 1 move /Y "{alt}" "{ziel}" >nul\r\n'
        f'start "" "{ziel}"\r\n'
        'del "%~f0"\r\n',
        encoding="ascii")
    return skript


def ersetze(ziel: Path, neu: Path) -> bool:
    """`ziel` durch `neu` ersetzen. Die Naht, an der Tests ansetzen.

    True  = fertig, Neustart kann sofort erfolgen (Linux, macOS)
    False = ein Helfer übernimmt, sobald dieser Prozess endet (Windows)
    """
    if not beschreibbar(ziel):
        raise TauschFehler(
            f"Kein Schreibrecht in {ziel.parent} — bitte die neue Fassung "
            f"von Hand herunterladen")
    if not neu.exists():
        raise TauschFehler(f"Neue Fassung fehlt: {neu}")

    alt = backup_pfad(ziel)
    if alt.exists():
        if alt.is_dir():
            shutil.rmtree(alt, ignore_errors=True)
        else:
            alt.unlink(missing_ok=True)

    if sys.platform == "darwin" and ziel.suffix == ".app":
        _signatur_pruefen(neu)

    if sys.platform == "win32":
        _windows_helfer(ziel, neu, alt)
        return False

    # Erst das Alte zur Seite, dann das Neue an seinen Platz. Bricht der
    # zweite Schritt ab, wird der erste zurückgenommen — sonst stünde
    # der Nutzer ganz ohne Programm da.
    try:
        os.replace(ziel, alt)
    except OSError as e:
        raise TauschFehler(f"Alte Fassung nicht verschiebbar: {e}") from e
    try:
        os.replace(neu, ziel)
    except OSError as e:
        # Rücknahme darf ihrerseits scheitern (dieselbe volle Platte) —
        # dann bleibt wenigstens das Backup liegen
        with contextlib.suppress(OSError):
            os.replace(alt, ziel)
        raise TauschFehler(f"Neue Fassung nicht einsetzbar: {e}") from e
    return True


def neu_starten(ziel: Path) -> None:
    """Die frisch getauschte Fassung starten und uns beenden."""
    if sys.platform == "darwin" and ziel.suffix == ".app":
        subprocess.Popen(["open", str(ziel)])
    else:
        subprocess.Popen([str(ziel)], close_fds=True)
