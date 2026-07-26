"""Wohin die Ergebnisse eines Laufs geschrieben werden.

Bewusst zwei Fälle, weil die Erwartung eine andere ist:

* **Terminal** — `./out/<strecke>/`, relativ zum Arbeitsverzeichnis. Wer
  im Terminal arbeitet, hat ein Arbeitsverzeichnis bewusst gewählt und
  erwartet die Ausgabe dort. Unverändert seit jeher.
* **Fenster** — ein fester, benannter Ordner unter „Dokumente". Beim
  Doppelklick bestimmt der Starter das Arbeitsverzeichnis, nicht das
  Programm: unter Linux ist das je nach Starter das Home- oder das
  Entpackverzeichnis, im macOS-Finder „/", unter Windows der Ort der
  Exe. Ein relatives `out/` landet dann irgendwo, und der Nutzer findet
  seine Ergebnisse nicht wieder (Beta-Befund 2026-07-26, Mint 22.3:
  Ausgaben lagen unter /home/<nutzer>/out/, gesucht wurden sie im
  selbst angelegten Programmordner).

Der frühere Wächter in packaging/entry.py griff hier nicht: Er wich nur
aus, wenn das Arbeitsverzeichnis *nicht beschreibbar* war. Ein
Home-Verzeichnis ist beschreibbar — der Fall trat also nie ein.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Kleingeschrieben und mit Bindestrichen wie der Projektname; taucht so
# im Dateimanager des Nutzers auf.
ORDNERNAME = "bm-routencheck-ergebnisse"

# Terminal-Vorgabe: relativ zum Arbeitsverzeichnis
TERMINAL_BASIS = Path("out")


def ausgabe_basis(args: Any) -> Path:
    """Basisordner, unter dem `<start>-<ziel>/` entsteht.

    EINE Entscheidungsstelle für alle Tools. Die Oberfläche legt ihren
    festen Ordner in `args.ausgabe_basis`; ohne das Feld — also im
    Terminal — bleibt es `./out`.

    Der erste Anlauf dieser Korrektur setzte den Ordner an jeder
    out_dir-Stelle einzeln und übersah dabei den Bahn-Modus: der baut
    sein out_dir nicht in der GUI, sondern tief in `rail/cli._pipeline`
    (Befund 2026-07-26, Windows). Deshalb hier gebündelt und per
    getattr tolerant — eine künftige vierte Aufrufstelle bekommt
    automatisch die Terminal-Vorgabe statt eines Absturzes.
    """
    return getattr(args, "ausgabe_basis", None) or TERMINAL_BASIS


def fenster_ausgabeordner() -> Path:
    """Fester Ausgabeordner für den Fenster-Start (alle Plattformen).

    „Dokumente" kommt von platformdirs und ist damit lokalisiert und
    OneDrive-/Umleitungs-fest. Lässt sich der Ordner nicht anlegen,
    bleibt das Home-Verzeichnis — dorthin darf jeder schreiben.
    """
    import platformdirs

    ziel = Path(platformdirs.user_documents_dir()) / ORDNERNAME
    try:
        ziel.mkdir(parents=True, exist_ok=True)
    except OSError:
        ziel = Path.home() / ORDNERNAME
        try:
            ziel.mkdir(parents=True, exist_ok=True)
        except OSError:
            return Path.home()
    return ziel
