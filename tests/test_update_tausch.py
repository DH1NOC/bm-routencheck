"""Herunterladen, Auspacken, Ersetzen — der Teil, der etwas zerstören kann.

Der eigentliche Tausch läuft gegen Attrappen im tmp_path; nur der
Neustart bleibt Handarbeit. Jeder Test beschreibt einen Weg, auf dem
eine Installation kaputtgehen könnte.
"""
from __future__ import annotations

import hashlib
import io
import os
import tarfile
import zipfile

import httpx
import pytest

from bmtools.update import laden as ld
from bmtools.update import tausch as t
from bmtools.update import ziel as z
from bmtools.update.manifest import Artefakt
from bmtools.update.pruefen import Angebot

INHALT = b"das neue binary" * 100


def angebot(inhalt: bytes = INHALT, datei: str = "neu.bin") -> Angebot:
    return Angebot(version="0.4.1",
                   artefakt=Artefakt(datei=datei,
                                     sha256=hashlib.sha256(inhalt).hexdigest()),
                   basis_url="https://example.invalid/v0.4.1",
                   vorabversion=False)


def client_mit(inhalt: bytes) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=inhalt)))


# ------------------------------------------------------- Herunterladen

def test_geladenes_artefakt_wird_gegen_das_manifest_geprueft(tmp_path):
    with client_mit(INHALT) as c:
        pfad = ld.hole(angebot(), tmp_path, client=c)
    assert pfad.read_bytes() == INHALT


def test_untergeschobenes_artefakt_wird_verworfen(tmp_path):
    """Manifest echt, Datei ausgetauscht — muss auffliegen, und die
    unbrauchbare Datei darf nicht liegen bleiben."""
    with client_mit(b"schadsoftware") as c, \
         pytest.raises(ld.LadeFehler, match="Prüfsumme"):
        ld.hole(angebot(), tmp_path, client=c)
    assert list(tmp_path.iterdir()) == []


def test_uebergrosses_artefakt_wird_abgebrochen(tmp_path, monkeypatch):
    monkeypatch.setattr(ld, "ARTEFAKT_MAX", 1024)
    with client_mit(b"x" * 5000) as c, \
         pytest.raises(ld.LadeFehler, match="unplausibel"):
        ld.hole(angebot(b"x" * 5000), tmp_path, client=c)


# ---------------------------------------------------------- Auspacken

def test_zip_slip_wird_abgewehrt(tmp_path):
    """Ein Eintrag »../../evil« darf nie außerhalb landen."""
    archiv = tmp_path / "boese.zip"
    with zipfile.ZipFile(archiv, "w") as zf:
        zf.writestr("../../evil.txt", "aua")
    with pytest.raises(ld.LadeFehler, match="heraus"):
        ld.packe_aus(archiv, tmp_path / "ziel", z.MACOS)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_tar_mit_verknuepfung_wird_abgelehnt(tmp_path):
    archiv = tmp_path / "boese.tar.gz"
    with tarfile.open(archiv, "w:gz") as tf:
        info = tarfile.TarInfo("bmtools")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)
    with pytest.raises(ld.LadeFehler, match="Verknüpfung"):
        ld.packe_aus(archiv, tmp_path / "ziel", z.LINUX)


def test_linux_binary_wird_gefunden_und_ausfuehrbar(tmp_path):
    archiv = tmp_path / "gut.tar.gz"
    with tarfile.open(archiv, "w:gz") as tf:
        info = tarfile.TarInfo("bmtools")
        info.size = len(INHALT)
        tf.addfile(info, io.BytesIO(INHALT))
    neu = ld.packe_aus(archiv, tmp_path / "ziel", z.LINUX)
    assert neu.name == "bmtools"
    assert os.access(neu, os.X_OK)


def test_macos_bundle_wird_gefunden(tmp_path):
    archiv = tmp_path / "gut.zip"
    with zipfile.ZipFile(archiv, "w") as zf:
        zf.writestr("BM-Routencheck.app/Contents/MacOS/BM-Routencheck", "x")
    neu = ld.packe_aus(archiv, tmp_path / "ziel", z.MACOS)
    assert neu.name == "BM-Routencheck.app"


def test_archiv_ohne_programm(tmp_path):
    archiv = tmp_path / "leer.zip"
    with zipfile.ZipFile(archiv, "w") as zf:
        zf.writestr("liesmich.txt", "nichts hier")
    with pytest.raises(ld.LadeFehler, match="Bundle"):
        ld.packe_aus(archiv, tmp_path / "ziel", z.MACOS)


# ------------------------------------------------------------ Tausch

@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.setattr("bmtools.update.tausch.sys.platform", "linux")
    ziel = tmp_path / "bmtools"
    ziel.write_bytes(b"die alte fassung")
    neu = tmp_path / "arbeit" / "bmtools"
    neu.parent.mkdir()
    neu.write_bytes(INHALT)
    return ziel, neu


def test_tausch_behaelt_die_alte_fassung(installation):
    ziel, neu = installation
    assert t.ersetze(ziel, neu) is True
    assert ziel.read_bytes() == INHALT
    assert t.backup_pfad(ziel).read_bytes() == b"die alte fassung"


def test_erster_start_verwirft_die_alte_fassung(installation):
    """Dass dieser Code läuft, IST der Beweis für den gelungenen Start."""
    ziel, neu = installation
    t.ersetze(ziel, neu)
    assert t.alte_fassung_verwerfen(ziel) is True
    assert not t.backup_pfad(ziel).exists()
    assert t.alte_fassung_verwerfen(ziel) is False   # zweimal schadet nicht


def test_ohne_schreibrecht_wird_gar_nicht_erst_angefangen(installation):
    ziel, neu = installation
    ziel.parent.chmod(0o500)
    try:
        with pytest.raises(t.TauschFehler, match="Schreibrecht"):
            t.ersetze(ziel, neu)
        assert ziel.read_bytes() == b"die alte fassung"
    finally:
        ziel.parent.chmod(0o700)


def test_fehlende_neue_fassung(installation):
    ziel, neu = installation
    neu.unlink()
    with pytest.raises(t.TauschFehler, match="fehlt"):
        t.ersetze(ziel, neu)
    assert ziel.read_bytes() == b"die alte fassung"


def test_scheitert_das_einsetzen_kommt_das_alte_zurueck(installation,
                                                        monkeypatch):
    """Der schlimmste Fall: alte Fassung schon weg, neue geht nicht rein.
    Danach muss das Programm trotzdem noch da sein."""
    ziel, neu = installation
    echt = os.replace
    aufrufe = {"n": 0}

    def stolpert(a, b):
        aufrufe["n"] += 1
        if aufrufe["n"] == 2:        # der zweite Schritt scheitert
            raise OSError("Platte voll")
        echt(a, b)

    monkeypatch.setattr("bmtools.update.tausch.os.replace", stolpert)
    with pytest.raises(t.TauschFehler, match="nicht einsetzbar"):
        t.ersetze(ziel, neu)
    assert ziel.exists() and ziel.read_bytes() == b"die alte fassung"


def test_zweiter_tausch_raeumt_das_alte_backup_weg(installation):
    ziel, neu = installation
    t.ersetze(ziel, neu)
    neu2 = neu.parent / "noch_neuer"
    neu2.write_bytes(b"dritte fassung")
    t.ersetze(ziel, neu2)
    assert ziel.read_bytes() == b"dritte fassung"
    assert t.backup_pfad(ziel).read_bytes() == INHALT


def test_windows_legt_einen_helfer_an(tmp_path, monkeypatch):
    """Die laufende Exe ist gesperrt — getauscht wird nach unserem Ende."""
    monkeypatch.setattr("bmtools.update.tausch.sys.platform", "win32")
    ziel = tmp_path / "BM-Routencheck.exe"
    ziel.write_bytes(b"alt")
    neu = tmp_path / "neu.exe"
    neu.write_bytes(INHALT)

    assert t.ersetze(ziel, neu) is False     # noch nichts getauscht
    assert ziel.read_bytes() == b"alt"
    helfer = (tmp_path / "bm-update.cmd").read_text(encoding="ascii")
    assert str(os.getpid()) in helfer        # wartet auf uns
    assert str(ziel) in helfer and str(neu) in helfer
    assert "del " in helfer                  # räumt sich selbst weg


def test_macos_prueft_die_signatur_vor_dem_tausch(tmp_path, monkeypatch):
    """Ein Bundle ohne gültige Signatur wird nicht eingesetzt."""
    monkeypatch.setattr("bmtools.update.tausch.sys.platform", "darwin")
    ziel = tmp_path / "BM-Routencheck.app"
    ziel.mkdir()
    neu = tmp_path / "arbeit" / "BM-Routencheck.app"
    neu.mkdir(parents=True)

    class Fertig:
        returncode = 1
        stderr = b"code object is not signed at all"

    monkeypatch.setattr("bmtools.update.tausch.subprocess.run",
                        lambda *a, **k: Fertig())
    with pytest.raises(t.TauschFehler, match="signiert"):
        t.ersetze(ziel, neu)
    assert ziel.exists()
