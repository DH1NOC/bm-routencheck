"""system_oeffnen: öffnet plattformgerecht, still ist es nie.

Hintergrund (Beta-Befund 2026-07-17): webbrowser.open() öffnete unter
Windows im PyInstaller-Binary nichts — daher je Plattform der native
Weg (startfile/open/xdg-open).

Zweiter Befund (2026-07-26, Mint 22.3): Der Ordner-Knopf tat gar nichts.
Ursachen waren ein relativ übergebener Pfad und das restlose Verschlucken
jedes Fehlers — check=False, stderr nach /dev/null, und der Ausweg über
webbrowser griff nur, wenn xdg-open ganz fehlte. Seitdem: absoluter Pfad,
Ausweichkette, und ein OeffnenFehler, wenn nichts davon zieht.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from bmtools.routelib import oeffnen


class Lauf:
    """subprocess.run-Ersatz mit vorgegebenen Rückgabecodes je Programm."""

    def __init__(self, codes: dict[str, int]):
        self.codes = codes
        self.aufrufe: list[list[str]] = []
        self.umgebungen: list[dict[str, str]] = []

    def __call__(self, cmd, **kw):
        self.aufrufe.append(list(cmd))
        self.umgebungen.append(kw.get("env") or {})
        return subprocess.CompletedProcess(
            cmd, self.codes.get(cmd[0], 0), stderr=b"")


@pytest.fixture
def alle_oeffner_da(monkeypatch):
    """shutil.which findet jedes Programm der Ausweichkette."""
    monkeypatch.setattr(oeffnen.shutil, "which", lambda name: "/usr/bin/" + name)


def test_windows_nutzt_startfile(monkeypatch, tmp_path):
    aufrufe: list[Path] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", aufrufe.append, raising=False)
    oeffnen.system_oeffnen(tmp_path)
    assert aufrufe == [tmp_path.resolve()]


def test_macos_nutzt_open(monkeypatch, tmp_path):
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lauf)
    oeffnen.system_oeffnen(tmp_path)
    assert lauf.aufrufe == [["open", str(tmp_path.resolve())]]


def test_linux_nutzt_xdg_open(monkeypatch, tmp_path, alle_oeffner_da):
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)
    oeffnen.system_oeffnen(tmp_path)
    assert lauf.aufrufe == [["xdg-open", str(tmp_path.resolve())]]


def test_pfad_geht_immer_absolut_hinaus(monkeypatch, tmp_path, alle_oeffner_da):
    """Ein relativer Pfad wird vom Zielprogramm gegen DESSEN
    Arbeitsverzeichnis aufgelöst — auf Cinnamon reicht der Aufruf per
    DBus an den schon laufenden Nemo weiter, und der sitzt woanders."""
    (tmp_path / "ziel").mkdir()
    monkeypatch.chdir(tmp_path)
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)

    oeffnen.system_oeffnen(Path("ziel"))

    (uebergeben,) = [a[-1] for a in lauf.aufrufe]
    assert Path(uebergeben).is_absolute()
    assert Path(uebergeben) == (tmp_path / "ziel").resolve()


def test_linux_geht_die_ausweichkette_durch(monkeypatch, tmp_path,
                                            alle_oeffner_da):
    """xdg-open und gio scheitern, nemo zieht — kein Fehler nach außen."""
    lauf = Lauf({"xdg-open": 4, "gio": 1})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)
    oeffnen.system_oeffnen(tmp_path)
    assert [a[0] for a in lauf.aufrufe] == ["xdg-open", "gio", "nemo"]


def test_linux_meldet_fehler_statt_zu_schweigen(monkeypatch, tmp_path,
                                                alle_oeffner_da):
    """Kein Öffner zieht: OeffnenFehler mit allen Versuchen.

    Genau das fehlte — bisher endete der Knopfdruck lautlos, und der
    Nutzer hatte nichts in der Hand, was er hätte melden können.
    """
    lauf = Lauf(dict.fromkeys(
        [k[0] for k in oeffnen.LINUX_OEFFNER], 4))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)

    with pytest.raises(oeffnen.OeffnenFehler) as fehler:
        oeffnen.system_oeffnen(tmp_path)

    assert len(fehler.value.versuche) == len(oeffnen.LINUX_OEFFNER)
    assert "xdg-open: Code 4" in fehler.value.versuche
    assert "Code 4" in fehler.value.kurz


def test_still_liefert_fehler_statt_zu_werfen(monkeypatch, tmp_path,
                                              alle_oeffner_da):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", Lauf(dict.fromkeys(
        [k[0] for k in oeffnen.LINUX_OEFFNER], 1)))
    fehler = oeffnen.system_oeffnen_still(tmp_path)
    assert fehler is not None and fehler.ziel == tmp_path.resolve()
    assert oeffnen.system_oeffnen_still.__doc__  # Komfort-Variante bleibt


def test_fehlender_oeffner_wird_uebersprungen(monkeypatch, tmp_path):
    """Nur nemo ist installiert — die übrigen gar nicht erst aufrufen."""
    monkeypatch.setattr(oeffnen.shutil, "which",
                        lambda name: "/usr/bin/nemo" if name == "nemo" else None)
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)
    oeffnen.system_oeffnen(tmp_path)
    assert [a[0] for a in lauf.aufrufe] == ["nemo"]


def test_kein_oeffner_installiert(monkeypatch, tmp_path):
    monkeypatch.setattr(oeffnen.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(oeffnen.OeffnenFehler) as fehler:
        oeffnen.system_oeffnen(tmp_path)
    assert fehler.value.versuche == []
    assert "kein Öffner" in fehler.value.kurz


def test_pyinstaller_bibliothekspfad_kommt_nicht_ins_kind(monkeypatch,
                                                          tmp_path,
                                                          alle_oeffner_da):
    """PyInstaller (--onefile) zeigt LD_LIBRARY_PATH auf sein Entpack-
    verzeichnis. Erbt der Dateimanager das, zieht er unsere gebündelten
    Qt-/glib-Bibliotheken statt der System-Version und stirbt lautlos.
    PyInstaller sichert den Originalwert in *_ORIG — der gehört zurück.
    """
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123456")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/x86_64-linux-gnu")
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)

    oeffnen.system_oeffnen(tmp_path)

    (env,) = lauf.umgebungen
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/x86_64-linux-gnu"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_ohne_original_faellt_der_pfad_im_binary_weg(monkeypatch, tmp_path,
                                                     alle_oeffner_da):
    """Eingefroren, aber ohne gesicherten Originalwert: die Variable
    stammt dann von uns und darf nicht ins Kind."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123456")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)

    oeffnen.system_oeffnen(tmp_path)

    assert "LD_LIBRARY_PATH" not in lauf.umgebungen[0]


def test_unverpackt_bleibt_die_umgebung_unangetastet(monkeypatch, tmp_path,
                                                     alle_oeffner_da):
    """Aus dem Quellcode gestartet gibt es kein PyInstaller-Präfix — dann
    darf ein selbst gesetztes LD_LIBRARY_PATH auch nicht verschwinden."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/eigenes")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    lauf = Lauf({})
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lauf)

    oeffnen.system_oeffnen(tmp_path)

    assert lauf.umgebungen[0]["LD_LIBRARY_PATH"] == "/opt/eigenes"
