"""PyInstaller-Einstieg: startet BM-Routencheck (GUI-first, A1).

bmtools/cli.py nutzt relative Imports und taugt daher nicht direkt als
PyInstaller-Skript — dieses Mini-Skript importiert das Paket regulär.
"""
import io
import multiprocessing
import os
import sys

if sys.platform == "win32" and sys.stdout is None:
    # Windowed-Exe (--windowed, A1): Es gibt keine eigene Konsole und
    # sys.std* sind None. Zwei Fälle:
    #   * Aufruf aus cmd/PowerShell (Terminal-Fähigkeit): per
    #     AttachConsole an die Konsole des Aufrufers anklinken — Ausgabe
    #     und Eingabe landen dort. Eigenheit der Bauart: Der Prompt des
    #     Aufrufers kehrt sofort zurück, die Ausgabe erscheint darunter.
    #   * Doppelklick im Explorer: keine Elternkonsole, AttachConsole
    #     schlägt fehl — Streams auf os.devnull, damit print()/rich
    #     nie an None-Streams scheitern.
    import ctypes
    ATTACH_PARENT_PROCESS = ctypes.c_uint32(-1)
    if ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        sys.stdin = open("CONIN$", encoding="utf-8", errors="replace")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8",
                          errors="replace", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8",
                          errors="replace", buffering=1)
    else:
        sys.stdin = open(os.devnull, encoding="utf-8")
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

if sys.platform == "win32":
    # Legacy-Windows-Konsolen und Pipes melden oft cp1252 als Encoding —
    # die Emojis im Menü (🚆🚗🚴) führten dort zum UnicodeEncodeError
    # (Rauchtest-Befund 2026-07-17). UTF-8 mit Ersatzzeichen: Auf alten
    # Konsolen erscheint schlimmstenfalls ein Platzhalter, kein Absturz.
    for _strom in (sys.stdout, sys.stderr):
        if isinstance(_strom, io.TextIOWrapper):
            _strom.reconfigure(encoding="utf-8", errors="replace")

def _schreibbares_arbeitsverzeichnis() -> None:
    """App-Start ohne beschreibbares CWD abfangen (Beta-Befund 2026-07-21).

    Ergebnisse (out/…) entstehen relativ zum Arbeitsverzeichnis. Beim
    Doppelklick-Start ist das CWD aber nicht wählbar und oft nicht
    beschreibbar — macOS/Finder startet Apps mit CWD "/" (read-only-
    Systemvolume, OSError 30), unter Windows kann die Exe in einem
    geschützten Ordner liegen. Dann in Dokumente/BM-Routencheck wechseln;
    im Terminal gestartet bleibt das gewohnte ./out unberührt.
    """
    if os.access(os.getcwd(), os.W_OK):
        return
    from pathlib import Path

    import platformdirs
    ziel = Path(platformdirs.user_documents_dir()) / "BM-Routencheck"
    try:
        ziel.mkdir(parents=True, exist_ok=True)
        os.chdir(ziel)
    except OSError:
        os.chdir(Path.home())


if __name__ == "__main__":
    # Muss vor dem App-Start stehen: Windows/macOS starten multiprocessing-
    # Kindprozesse (Sichtfeld-Rendering, mapview.py) per Neuaufruf des
    # Binarys mit --multiprocessing-fork. Ohne freeze_support landete das
    # im bmtools-Menü statt im Worker (Beta-Befund 2026-07-17: Menü-Spam
    # und "process pool was terminated abruptly").
    multiprocessing.freeze_support()

    _schreibbares_arbeitsverzeichnis()
    from bmtools.cli import main
    sys.exit(main())
