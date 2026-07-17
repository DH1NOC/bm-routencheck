"""system_oeffnen: öffnet plattformgerecht und fällt robust zurück.

Hintergrund (Beta-Befund 2026-07-17): webbrowser.open() öffnete unter
Windows im PyInstaller-Binary nichts — daher je Plattform der native
Weg (startfile/open/xdg-open), webbrowser nur noch als letzter Ausweg.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from bmtools.routelib import oeffnen


def test_windows_nutzt_startfile(monkeypatch, tmp_path):
    aufrufe: list[Path] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", aufrufe.append, raising=False)
    oeffnen.system_oeffnen(tmp_path)
    assert aufrufe == [tmp_path]


def test_macos_nutzt_open(monkeypatch, tmp_path):
    aufrufe = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: aufrufe.append(cmd))
    oeffnen.system_oeffnen(tmp_path)
    assert aufrufe == [["open", str(tmp_path)]]


def test_linux_nutzt_xdg_open(monkeypatch, tmp_path):
    aufrufe = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: aufrufe.append(cmd))
    oeffnen.system_oeffnen(tmp_path)
    assert aufrufe == [["xdg-open", str(tmp_path)]]


def test_fallback_webbrowser_wenn_oeffner_fehlt(monkeypatch, tmp_path):
    geoeffnet: list[str] = []
    monkeypatch.setattr(sys, "platform", "linux")

    def kein_xdg_open(cmd, **kw):
        raise FileNotFoundError("xdg-open fehlt")

    monkeypatch.setattr(subprocess, "run", kein_xdg_open)
    monkeypatch.setattr(webbrowser, "open", geoeffnet.append)
    oeffnen.system_oeffnen(tmp_path)
    assert geoeffnet == [tmp_path.resolve().as_uri()]
