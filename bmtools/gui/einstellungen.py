"""Persistente GUI-Einstellungen (U5: Splitter-Position; U6: Theme).

Kleine JSON-Datei im Benutzer-Konfigurationsordner statt
localStorage: WKWebView persistiert Web-Storage für file://-Seiten
nicht zuverlässig über Neustarts, und die Bridge braucht die Werte
(z. B. Theme) künftig auch selbst.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir


def _datei() -> Path:
    return Path(user_config_dir("bm-routencheck")) / "gui.json"


def laden() -> dict[str, Any]:
    """Alle Einstellungen; leeres Dict bei fehlender/kaputter Datei."""
    try:
        daten = json.loads(_datei().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


def setzen(name: str, wert: Any) -> None:
    """Eine Einstellung schreiben (liest-verändert-schreibt die Datei;
    die GUI ist der einzige Schreiber, ein Lock lohnt nicht)."""
    daten = laden()
    daten[name] = wert
    datei = _datei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                     encoding="utf-8")
