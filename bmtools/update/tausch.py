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
  ist, und der Team-Anker, ob es vom selben Apple-Team stammt wie das
  laufende; ein selbst geladenes Archiv trägt kein Quarantäne-Attribut,
  Gatekeeper prüft also nicht für uns mit.
* **Windows** — eine laufende `.exe` ist gesperrt. Ein kleiner
  Helfer wartet, bis wir beendet sind, tauscht, startet neu und löscht
  sich selbst.
"""
from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .ziel import beschreibbar

BACKUP_ENDUNG = ".vorher"
HELFER_NAME = "bm-update.cmd"


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


def _team_id(bundle: Path) -> str | None:
    """TeamIdentifier der Signatur — None bei unsigniert oder ad-hoc."""
    try:
        fertig = subprocess.run(
            ["codesign", "--display", "--verbose=2", str(bundle)],
            capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    for zeile in fertig.stderr.decode(errors="replace").splitlines():
        praefix, _, wert = zeile.partition("=")
        if praefix == "TeamIdentifier":
            wert = wert.strip()
            return wert if wert and wert != "not set" else None
    return None


def _signatur_pruefen(neu: Path, ziel: Path) -> None:
    """macOS: Ist das neue Bundle unversehrt signiert — vom selben Team?

    `codesign --verify` allein bescheinigt nur Unversehrtheit gegen
    IRGENDEINE gültige Signatur, auch eine ad-hoc-Signatur. Deshalb der
    Anker: Das neue Bundle muss vom selben Apple-Team stammen wie das
    laufende — das notarisierte laufende Bundle IST die Referenz, ein
    einkompiliertes Team braucht es dafür nicht. Trägt das laufende
    Bundle selbst kein Team (Entwickler-Build), gibt es nichts zu
    verankern; dann bleibt es bei der Unversehrtheitsprüfung.
    """
    try:
        fertig = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(neu)],
            capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        raise TauschFehler(f"codesign nicht ausführbar: {e}") from e
    if fertig.returncode != 0:
        meldung = fertig.stderr.decode(errors="replace").strip()
        raise TauschFehler(
            f"Neues Bundle ist nicht gültig signiert — Tausch abgebrochen "
            f"({meldung or 'codesign Code ' + str(fertig.returncode)})")

    eigen = _team_id(ziel)
    if eigen is None:
        return
    fremd = _team_id(neu)
    if fremd != eigen:
        raise TauschFehler(
            f"Neues Bundle ist von einem anderen Team signiert "
            f"({fremd or 'keinem'} statt {eigen}) — Tausch abgebrochen")


def _windows_helfer(ziel: Path) -> Path:
    """Batch-Datei, die nach unserem Ende tauscht und neu startet.

    Die Pfade stehen NICHT im Skript, sondern kommen als
    Umgebungsvariablen mit (BM_UPDATE_*): cmd liest Batch-Dateien in
    der OEM-Codepage, und unter C:\\Users\\Jürgen scheiterte vorher
    schon das Schreiben mit encoding="ascii" — mit unbehandeltem
    UnicodeEncodeError. Umgebungsvariablen laufen über CreateProcessW
    (volles Unicode), und weil %VAR% nur einmal expandiert wird, sind
    auch %-Zeichen und cmd-Sonderzeichen in Pfaden kein Thema mehr.
    Die Datei selbst bleibt so garantiert reines ASCII.

    Warten per ping statt `timeout /t`: timeout verweigert ohne echte
    Konsole den Dienst („Eingabeumleitung wird nicht unterstützt") —
    und der Helfer läuft absichtlich ohne Fenster.
    """
    skript = ziel.with_name(HELFER_NAME)
    skript.write_text(
        "@echo off\r\n"
        "rem Von BM-Routencheck erzeugt; loescht sich am Ende selbst.\r\n"
        "rem Pfade und PID kommen als BM_UPDATE_*-Umgebungsvariablen.\r\n"
        ":warten\r\n"
        'tasklist /FI "PID eq %BM_UPDATE_PID%" 2>nul '
        '| find "%BM_UPDATE_PID%" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  ping -n 2 127.0.0.1 >nul\r\n"
        "  goto warten\r\n"
        ")\r\n"
        'move /Y "%BM_UPDATE_ZIEL%" "%BM_UPDATE_ALT%" >nul\r\n'
        'move /Y "%BM_UPDATE_NEU%" "%BM_UPDATE_ZIEL%" >nul\r\n'
        'if errorlevel 1 move /Y "%BM_UPDATE_ALT%" "%BM_UPDATE_ZIEL%" '
        ">nul\r\n"
        'start "" "%BM_UPDATE_ZIEL%"\r\n'
        'del "%~f0"\r\n',
        encoding="ascii")
    return skript


def _helfer_starten(skript: Path, ziel: Path, neu: Path, alt: Path) -> None:
    """Den Helfer als eigenständigen, unsichtbaren Prozess starten.

    Eine Batch-Datei wartet nicht von selbst auf unser Ende — ohne
    diesen Start wäre sie nur eine Absichtserklärung auf der Platte.
    CREATE_NO_WINDOW gibt cmd eine eigene (unsichtbare) Konsole; der
    Prozess überlebt unser Ende, genau dafür ist er da.
    """
    umgebung = {**os.environ,
                "BM_UPDATE_PID": str(os.getpid()),
                "BM_UPDATE_ZIEL": str(ziel),
                "BM_UPDATE_NEU": str(neu),
                "BM_UPDATE_ALT": str(alt)}
    try:
        subprocess.Popen(["cmd", "/c", str(skript)],
                         env=umgebung,
                         creationflags=getattr(subprocess,
                                               "CREATE_NO_WINDOW", 0),
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError as e:
        raise TauschFehler(f"Update-Helfer nicht startbar: {e}") from e


def helfer_verwerfen(ziel: Path) -> None:
    """Beim Start: liegengebliebenes Helfer-Skript entsorgen.

    Bleibt nur zurück, wenn der Helfer zwischen Schreiben und
    Selbstlöschen abgebrochen wurde — im Normalfall gibt es hier nichts
    zu tun.
    """
    with contextlib.suppress(OSError):
        ziel.with_name(HELFER_NAME).unlink(missing_ok=True)


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
        _signatur_pruefen(neu, ziel)

    if sys.platform == "win32":
        _helfer_starten(_windows_helfer(ziel), ziel, neu, alt)
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
    """Die frisch getauschte Fassung starten und uns beenden.

    macOS: NICHT direkt `open` rufen. Solange wir leben, sieht
    LaunchServices unsere Bundle-ID als laufend und AKTIVIERT nur die
    alte Instanz, statt die neue zu starten — die Selbst-Aktivierung
    mitten im Fenster-Abbau ließ die App bei »Neustart …« einfrieren
    (Beta-Befund 2026-07-27, beta.1→beta.2). Ein abgekoppelter
    sh-Helfer wartet deshalb auf unser Prozessende; erst dann startet
    `open` wirklich die neue Fassung.
    """
    if sys.platform == "darwin" and ziel.suffix == ".app":
        befehl = (f"while kill -0 {os.getpid()} 2>/dev/null; "
                  f"do sleep 0.2; done; open {shlex.quote(str(ziel))}")
        subprocess.Popen(["/bin/sh", "-c", befehl],
                         start_new_session=True,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([str(ziel)], close_fds=True)
