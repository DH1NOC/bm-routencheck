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


@pytest.fixture
def windows(tmp_path, monkeypatch):
    """Windows-Attrappe: Plattform, Exe und ein abgefangener Popen.

    Der Programmordner heißt absichtlich »Jürgen« — auf deutschen
    Windows-Systemen ist der Umlaut im Benutzerpfad der Normalfall,
    nicht der Sonderfall (Befund 2026-07-27: encoding="ascii" warf
    dort einen unbehandelten UnicodeEncodeError).
    """
    monkeypatch.setattr("bmtools.update.tausch.sys.platform", "win32")
    laeufe: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setattr(
        "bmtools.update.tausch.subprocess.Popen",
        lambda argv, **kwargs: laeufe.append((argv, kwargs.get("env") or {})))
    ordner = tmp_path / "Jürgen"
    ordner.mkdir()
    ziel = ordner / "BM-Routencheck.exe"
    ziel.write_bytes(b"alt")
    neu = ordner / "neu.exe"
    neu.write_bytes(INHALT)
    return ziel, neu, laeufe


def test_windows_legt_einen_helfer_an(windows):
    """Die laufende Exe ist gesperrt — getauscht wird nach unserem Ende.
    Die Pfade reisen als Umgebungsvariablen mit: die Batch-Datei selbst
    bleibt reines ASCII, egal wie der Benutzerpfad heißt."""
    ziel, neu, _ = windows
    assert t.ersetze(ziel, neu) is False     # noch nichts getauscht
    assert ziel.read_bytes() == b"alt"
    helfer = ziel.with_name(t.HELFER_NAME).read_text(encoding="ascii")
    assert "%BM_UPDATE_PID%" in helfer       # wartet auf uns
    assert "%BM_UPDATE_ZIEL%" in helfer and "%BM_UPDATE_NEU%" in helfer
    assert "Jürgen" not in helfer            # kein Pfad im Skript
    assert "del " in helfer                  # räumt sich selbst weg


def test_windows_startet_den_helfer(windows):
    """Das Skript muss auch LAUFEN — eine Batch-Datei wartet nicht von
    selbst auf unser Ende (Befund 2026-07-27: sie wurde nie gestartet,
    das Windows-Update war eine Attrappe). Pfade und PID kommen als
    Umgebungsvariablen mit — volles Unicode, kein cmd-Quoting."""
    ziel, neu, laeufe = windows
    t.ersetze(ziel, neu)
    assert laeufe, "Helfer wurde nie gestartet"
    argv, umgebung = laeufe[0]
    assert argv[:2] == ["cmd", "/c"]
    assert argv[2] == str(ziel.with_name(t.HELFER_NAME))
    assert umgebung["BM_UPDATE_PID"] == str(os.getpid())
    assert umgebung["BM_UPDATE_ZIEL"] == str(ziel)
    assert umgebung["BM_UPDATE_NEU"] == str(neu)
    assert umgebung["BM_UPDATE_ALT"] == str(t.backup_pfad(ziel))


def test_windows_meldet_unstartbaren_helfer(windows, monkeypatch):
    """Scheitert der Start des Helfers, ist das ein TauschFehler mit
    verständlichem Text — kein stilles »beim Beenden passiert's dann«."""
    ziel, neu, _ = windows

    def kaputt(*a, **k):
        raise OSError("cmd nicht gefunden")

    monkeypatch.setattr("bmtools.update.tausch.subprocess.Popen", kaputt)
    with pytest.raises(t.TauschFehler, match="Helfer"):
        t.ersetze(ziel, neu)


@pytest.fixture
def macos(tmp_path, monkeypatch):
    """macOS-Attrappe: laufendes und neues Bundle als Ordner."""
    monkeypatch.setattr("bmtools.update.tausch.sys.platform", "darwin")
    ziel = tmp_path / "BM-Routencheck.app"
    ziel.mkdir()
    (ziel / "alt.txt").write_text("alt")
    neu = tmp_path / "arbeit" / "BM-Routencheck.app"
    neu.mkdir(parents=True)
    (neu / "neu.txt").write_text("neu")
    return ziel, neu


def _codesign_attrappe(teams):
    """subprocess.run-Ersatz: --verify ist zufrieden, --display liefert
    je Bundle-Pfad den TeamIdentifier aus `teams`."""
    def run(argv, **kwargs):
        class Fertig:
            returncode = 0
            stderr = b""
        fertig = Fertig()
        if "--display" in argv:
            team = teams.get(argv[-1], "not set")
            fertig.stderr = f"TeamIdentifier={team}\n".encode()
        return fertig
    return run


def test_macos_prueft_die_signatur_vor_dem_tausch(macos, monkeypatch):
    """Ein Bundle ohne gültige Signatur wird nicht eingesetzt."""
    ziel, neu = macos

    class Fertig:
        returncode = 1
        stderr = b"code object is not signed at all"

    monkeypatch.setattr("bmtools.update.tausch.subprocess.run",
                        lambda *a, **k: Fertig())
    with pytest.raises(t.TauschFehler, match="signiert"):
        t.ersetze(ziel, neu)
    assert ziel.exists()


def test_macos_fremdes_team_wird_abgelehnt(macos, monkeypatch):
    """Der Anker: --verify allein nähme auch eine intakte FREMDE
    Signatur an (ad-hoc genügt ihm). Das neue Bundle muss vom selben
    Team stammen wie das laufende."""
    ziel, neu = macos
    monkeypatch.setattr("bmtools.update.tausch.subprocess.run",
                        _codesign_attrappe({str(ziel): "TEAM1234",
                                            str(neu): "BOESE666"}))
    with pytest.raises(t.TauschFehler, match="anderen Team"):
        t.ersetze(ziel, neu)
    assert (ziel / "alt.txt").exists()      # nichts getauscht


def test_macos_gleiches_team_darf_tauschen(macos, monkeypatch):
    ziel, neu = macos
    monkeypatch.setattr("bmtools.update.tausch.subprocess.run",
                        _codesign_attrappe({str(ziel): "TEAM1234",
                                            str(neu): "TEAM1234"}))
    assert t.ersetze(ziel, neu) is True
    assert (ziel / "neu.txt").exists()


def test_macos_ohne_eigenes_team_nur_unversehrtheit(macos, monkeypatch):
    """Läuft hier ein unsignierter Entwickler-Build, gibt es kein Team
    zu verankern — die Unversehrtheitsprüfung des neuen Bundles bleibt."""
    ziel, neu = macos
    monkeypatch.setattr("bmtools.update.tausch.subprocess.run",
                        _codesign_attrappe({str(neu): "TEAM1234"}))
    assert t.ersetze(ziel, neu) is True
