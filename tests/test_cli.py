"""Tests bmtools-Menü: Beenden-Auswahl (Regression KeyError 2026-07-17)."""
import sys

import questionary

from bmtools import cli


class _Auswahl:
    """questionary.select-Stub: liefert eine feste Antwort."""
    def __init__(self, antwort):
        self._antwort = antwort

    def ask(self):
        return self._antwort


def test_menue_beenden_beendet_ohne_keyerror(monkeypatch, capsys):
    # Regression: Choice("🚪  Beenden", value=None) fiel bei questionary
    # auf den Titel als Wert zurück → KeyError in TOOLS[tool].
    monkeypatch.setattr(sys, "argv", ["bmtools"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(questionary, "select",
                        lambda *a, **k: _Auswahl("ende"))
    assert cli.main() == 0
    assert "73" in capsys.readouterr().out


def test_menue_ctrl_c_beendet(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bmtools"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(questionary, "select",
                        lambda *a, **k: _Auswahl(None))
    assert cli.main() == 0
