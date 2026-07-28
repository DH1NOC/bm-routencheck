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
    # sys.std* sind None. Drei Fälle:
    #   * --terminal (interaktiv): eigenes Konsolenfenster per
    #     AllocConsole. In der Konsole des Aufrufers ginge es nicht —
    #     PowerShell liest dort parallel seinen eigenen Prompt (beide
    #     Prozesse streiten um die Tastatur), und prompt_toolkit
    #     verlangt echte Console-Std-Handles, die nur AllocConsole
    #     setzt (Beta-Befund 2026-07-21: NoConsoleScreenBufferError).
    #   * Aufruf aus cmd/PowerShell (nicht-interaktiv, z. B. --help,
    #     Flag-Läufe): per AttachConsole an die Konsole des Aufrufers
    #     anklinken. Eigenheit der Bauart: Der Prompt des Aufrufers
    #     kehrt sofort zurück, die Ausgabe erscheint darunter.
    #   * Doppelklick im Explorer: keine Elternkonsole — Streams auf
    #     os.devnull, damit print()/rich nie an None-Streams scheitern.
    import ctypes
    _k32 = ctypes.windll.kernel32
    ATTACH_PARENT_PROCESS = ctypes.c_uint32(-1)
    if "--terminal" in sys.argv[1:] and _k32.AllocConsole():
        _k32.SetConsoleTitleW("BM-Routencheck")
        _konsole = True
    else:
        _konsole = bool(_k32.AttachConsole(ATTACH_PARENT_PROCESS))
    if _konsole:
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

    macOS/Finder startet Apps mit CWD "/" (read-only-Systemvolume,
    OSError 30), unter Windows kann die Exe in einem geschützten Ordner
    liegen — dann scheitert jeder relative Schreibzugriff.

    Die Ergebnisse selbst hängen seit 2026-07-26 nicht mehr am
    Arbeitsverzeichnis (bmtools/ausgabe.py); dieser Wächter ist nur noch
    das Netz für alles Übrige. Er weicht bewusst in denselben Ordner aus,
    damit nicht zwei Ablagen nebeneinander entstehen.
    """
    if os.access(os.getcwd(), os.W_OK):
        return
    from pathlib import Path

    try:
        from bmtools.ausgabe import fenster_ausgabeordner
        os.chdir(fenster_ausgabeordner())
    except OSError:
        os.chdir(Path.home())


if sys.platform.startswith("linux"):
    # Im Linux-Binary ist nur das Qt-Backend gebündelt — pywebview nicht
    # erst GTK probieren lassen: Das druckte bei jedem GUI-Start einen
    # ModuleNotFoundError-Traceback ins Terminal (Beta-Befund 2026-07-21).
    os.environ.setdefault("PYWEBVIEW_GUI", "qt")

if __name__ == "__main__":
    # Muss vor dem App-Start stehen: Windows/macOS starten multiprocessing-
    # Kindprozesse (Sichtfeld-Rendering, mapview.py) per Neuaufruf des
    # Binarys mit --multiprocessing-fork. Ohne freeze_support landete das
    # im bmtools-Menü statt im Worker (Beta-Befund 2026-07-17: Menü-Spam
    # und "process pool was terminated abruptly").
    multiprocessing.freeze_support()

    _schreibbares_arbeitsverzeichnis()
    # Wir laufen — also hat ein etwaiger Tausch geklappt: Sicherung der
    # Vorversion und Reste eines abgebrochenen Laufs wegräumen
    # (DEVELOPER.md „Selbst-Updater“, »behalten bis zum ersten Erfolg«). Darf den Start
    # nie aufhalten; die Funktion schluckt ihre Fehler selbst.
    from bmtools.update.ablauf import beim_start_aufraeumen
    beim_start_aufraeumen()

    from bmtools.cli import main
    sys.exit(main())
