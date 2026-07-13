"""Tests CLI-Look: Banner und deutsche argparse-Texte."""
import argparse

import pytest
from rich.console import Console

from bmtools import ui


def test_banner_zeigt_titel_und_tastenhinweis():
    console = Console(record=True, width=100)
    ui.banner(console, "Titel", "Untertitel", icon="🚆")
    text = console.export_text()
    assert "Titel" in text and "Untertitel" in text
    assert "Enter bestätigen" in text


def test_argparse_spricht_deutsch(capsys):
    ui.argparse_deutsch()
    ap = argparse.ArgumentParser(prog="bm-test")
    ap.add_argument("--x")
    assert "Aufruf:" in ap.format_help()
    assert "Optionen" in ap.format_help()
    with pytest.raises(SystemExit):
        ap.parse_args(["--unbekannt"])
    assert "unbekannte Argumente" in capsys.readouterr().err
