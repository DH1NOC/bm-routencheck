"""Eigene Programmversion — Grundlage jeder Update-Entscheidung.

Ohne belastbare eigene Version gibt es keine Downgrade-Sperre. Die
Ermittlung hat zwei Quellen mit einer bewussten Rangfolge, weil
importlib.metadata im Entwicklungs-Checkout die Version des letzten
`pip install` meldet — im venv dieses Projekts 0.1.2, während
pyproject auf 0.3.0 stand (Befund 2026-07-27).
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from bmtools import version as version_mod


def test_version_kommt_aus_dem_arbeitsstand():
    """Im Checkout gilt pyproject.toml, nicht die installierte Metadate."""
    with (Path(__file__).resolve().parent.parent / "pyproject.toml").open("rb") as f:
        erwartet = tomllib.load(f)["project"]["version"]
    assert version_mod.eigene_version() == erwartet
    assert version_mod.version_bekannt()


def test_gefroren_zaehlen_nur_die_metadaten(monkeypatch):
    """Im Binary gibt es keine pyproject.toml — dort müssen die
    Paket-Metadaten greifen (release.yml: --copy-metadata)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert version_mod._aus_pyproject() is None
    # Die Metadaten sind im Testlauf vorhanden (editable install)
    assert version_mod.eigene_version() != version_mod.UNBEKANNT


def test_ohne_jede_quelle_gilt_die_version_als_unbekannt(monkeypatch):
    """Kein Absturz — aber der Updater muss schweigen können."""
    from importlib.metadata import PackageNotFoundError

    monkeypatch.setattr(version_mod, "_aus_pyproject", lambda: None)

    def nichts(_name: str) -> str:
        raise PackageNotFoundError(version_mod.PAKET)

    monkeypatch.setattr(version_mod, "_metadata_version", nichts)
    assert version_mod.eigene_version() == version_mod.UNBEKANNT
    assert not version_mod.version_bekannt()


def test_kaputte_pyproject_wirft_nicht(monkeypatch, tmp_path):
    """Unlesbare oder fehlerhafte pyproject.toml darf den Start nicht
    kosten — dann eben die Metadaten."""
    kaputt = tmp_path / "bmtools"
    kaputt.mkdir()
    (tmp_path / "pyproject.toml").write_text("das ist kein TOML = [[[")
    monkeypatch.setattr(version_mod, "__file__", str(kaputt / "version.py"))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert version_mod._aus_pyproject() is None
    assert version_mod.eigene_version() != version_mod.UNBEKANNT


def test_version_flag_in_allen_werkzeugen(capsys, monkeypatch):
    """bmtools, bahn, auto und rad melden alle dieselbe Version."""
    from bmtools.cli import main

    erwartet = f"BM-Routencheck {version_mod.eigene_version()}"
    for aufruf in (["bmtools", "--version"], ["bmtools", "bahn", "--version"],
                   ["bmtools", "auto", "--version"],
                   ["bmtools", "rad", "--version"]):
        monkeypatch.setattr(sys, "argv", aufruf)
        try:
            main()
        except SystemExit as e:      # argparse beendet nach --version
            assert e.code in (0, None)
        assert erwartet in capsys.readouterr().out
