"""Tests GUI-Startlogik (G1): Desktop-Erkennung und GUI/Terminal-Fallback."""
from __future__ import annotations

import os
import sys

import pytest
from rich.console import Console

from bmtools import gui
from bmtools.gui import fenster


@pytest.fixture(autouse=True)
def _saubere_umgebung(monkeypatch):
    """SSH-/Display-Variablen der Testumgebung neutralisieren."""
    for var in ("SSH_CONNECTION", "SSH_TTY", "DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# desktop_verfuegbar
# ---------------------------------------------------------------------------

def test_ssh_sitzung_zaehlt_als_terminal(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.1 50000 203.0.113.2 22")
    assert gui.desktop_verfuegbar() is False


def test_macos_hat_desktop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert gui.desktop_verfuegbar() is True


def test_windows_hat_desktop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "name", "nt")
    assert gui.desktop_verfuegbar() is True


def test_linux_ohne_display_ist_terminal(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "name", "posix")
    assert gui.desktop_verfuegbar() is False


@pytest.mark.parametrize("variable", ["DISPLAY", "WAYLAND_DISPLAY"])
def test_linux_mit_display_hat_desktop(monkeypatch, variable):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv(variable, ":0" if variable == "DISPLAY" else "wayland-0")
    assert gui.desktop_verfuegbar() is True


# ---------------------------------------------------------------------------
# start_oder_none
# ---------------------------------------------------------------------------

def test_ohne_desktop_faellt_still_auf_terminal(monkeypatch):
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: False)
    monkeypatch.setattr(
        fenster, "gui_starten",
        lambda tool: pytest.fail("GUI darf ohne Desktop nicht starten"))
    assert gui.start_oder_none(Console(), "bahn") is None


def test_desktop_startet_gui(monkeypatch):
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: True)
    aufrufe: list[str | None] = []

    def fake_start(tool):
        aufrufe.append(tool)
        return 0

    monkeypatch.setattr(fenster, "gui_starten", fake_start)
    assert gui.start_oder_none(Console(), "rad") == 0
    assert aufrufe == ["rad"]


def test_startfehler_faellt_mit_hinweis_auf_terminal(monkeypatch, capsys):
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: True)

    def kaputt(tool):
        raise gui.GuiStartFehler("kein Webview-Backend")

    monkeypatch.setattr(fenster, "gui_starten", kaputt)
    assert gui.start_oder_none(Console(), "bahn") is None
    assert "weiter im Terminal" in capsys.readouterr().out


def test_erzwungener_start_macht_fehler_hart(monkeypatch, capsys):
    # --gui: kein stiller Fallback, der Nutzer hat die GUI verlangt
    monkeypatch.setattr(gui, "desktop_verfuegbar", lambda: False)

    def kaputt(tool):
        raise gui.GuiStartFehler("pywebview ist nicht installiert")

    monkeypatch.setattr(fenster, "gui_starten", kaputt)
    assert gui.start_oder_none(Console(), None, erzwungen=True) == 1
    assert "GUI konnte nicht starten" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Frontend-Dateien (G3): lokal gebündelt, keine CDN-Zugriffe (Keyless)
# ---------------------------------------------------------------------------

def test_frontend_dateien_vorhanden():
    for name in ("index.html", "stil.css", "app.js"):
        assert (fenster.STATIC / name).is_file()


def test_hidden_schlaegt_display_regeln():
    # Regression G4-Abnahmebefund 2026-07-19: .tabs/#dialog-hintergrund
    # sind display:flex — ohne globale [hidden]-Regel überdeckte der
    # leere Dialog-Hintergrund dauerhaft die Oberfläche.
    css = (fenster.STATIC / "stil.css").read_text()
    assert "[hidden] { display: none !important; }" in css


def test_frontend_ohne_externe_urls():
    for name in ("index.html", "stil.css", "app.js"):
        inhalt = (fenster.STATIC / name).read_text()
        # Links dürfen nur in Platzhaltertexten (placeholder=…) stehen,
        # nie als geladene Ressource (src/href auf http…). Die
        # xmlns-Kennung des Icon-Sprites (U1) ist ein XML-Namespace —
        # sie wird nie geladen.
        for zeile in inhalt.splitlines():
            zeile = zeile.replace('xmlns="http://www.w3.org/2000/svg"', "")
            if "placeholder" in zeile or zeile.strip().startswith("*"):
                continue
            assert "http://" not in zeile and "https://" not in zeile, \
                f"{name}: externe Ressource? {zeile.strip()}"
