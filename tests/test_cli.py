"""Tests bmtools-Menü: Beenden-Auswahl (Regression KeyError 2026-07-17)."""
import sys

import pytest
import questionary

from bmtools import cli, gui


class _Auswahl:
    """questionary.select-Stub: liefert eine feste Antwort."""
    def __init__(self, antwort):
        self._antwort = antwort

    def ask(self):
        return self._antwort


@pytest.fixture(autouse=True)
def _kein_desktop(monkeypatch):
    """Menü-Tests laufen im Terminal-Pfad — die Auto-GUI (öffnet auf
    Entwickler-Desktops sonst ein echtes Fenster) bleibt aus."""
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: False)


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


def test_terminal_flag_zeigt_menue_trotz_desktop(monkeypatch, capsys):
    # --terminal erzwingt das Terminal-Menü auch mit Desktop-Umgebung
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: True)
    monkeypatch.setattr(sys, "argv", ["bmtools", "--terminal"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(questionary, "select",
                        lambda *a, **k: _Auswahl("ende"))
    assert cli.main() == 0
    assert "73" in capsys.readouterr().out


def test_ohne_argumente_startet_gui_auf_desktop(monkeypatch):
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: True)
    aufrufe = []

    def fake_start(tool):
        aufrufe.append(tool)
        return 0

    monkeypatch.setattr("bmtools.gui.fenster.gui_starten", fake_start)
    monkeypatch.setattr(sys, "argv", ["bmtools"])
    assert cli.main() == 0
    assert aufrufe == [None]
