"""Tests Cache-Verwaltung: Bereiche, Größen, Leeren, CLI-Subcommand."""
import sys

from bmtools import cache_admin, cli


def _fuelle_cache(monkeypatch, tmp_path):
    """user_cache_dir auf tmp_path umbiegen und alle Bereiche befüllen."""
    monkeypatch.setattr(cache_admin, "user_cache_dir",
                        lambda ns: str(tmp_path / ns))
    for ns, name, inhalt in [
        ("bmtools/devices", "a.json", b"x" * 100),
        ("bmtools/profiles", "b.json", b"x" * 50),
        ("bmtools/misc", "c.json", b"x" * 25),
        ("bmtools/fm", "d.json", b"x" * 200),
    ]:
        (tmp_path / ns).mkdir(parents=True, exist_ok=True)
        (tmp_path / ns / name).write_bytes(inhalt)
    kacheln = tmp_path / "bmtools" / "terrain" / "11"
    kacheln.mkdir(parents=True)
    (kacheln / "1_2.png").write_bytes(b"x" * 1000)
    (kacheln / "3_4.png").write_bytes(b"x" * 1000)


def test_bereiche_zaehlen_dateien_und_groesse(monkeypatch, tmp_path):
    _fuelle_cache(monkeypatch, tmp_path)
    bm, fm, terrain = cache_admin.bereiche()
    assert "Brandmeister" in bm.name
    assert (bm.dateien, bm.groesse_bytes) == (3, 175)
    assert (fm.dateien, fm.groesse_bytes) == (1, 200)
    assert "Höhenkacheln" in terrain.name
    assert (terrain.dateien, terrain.groesse_bytes) == (2, 2000)


def test_leeren_loescht_alles_und_meldet_bytes(monkeypatch, tmp_path):
    _fuelle_cache(monkeypatch, tmp_path)
    assert cache_admin.leeren() == 2375
    assert all(b.dateien == 0 for b in cache_admin.bereiche())
    assert not (tmp_path / "bmtools" / "terrain").exists()


def test_leeren_auf_leerem_cache_ist_harmlos(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_admin, "user_cache_dir",
                        lambda ns: str(tmp_path / ns))
    assert cache_admin.leeren() == 0


def test_groesse_mensch_deutsche_einheiten():
    assert cache_admin.groesse_mensch(0) == "0 B"
    assert cache_admin.groesse_mensch(999) == "999 B"
    assert cache_admin.groesse_mensch(45_600) == "45,6 kB"
    assert cache_admin.groesse_mensch(3_400_000) == "3,4 MB"
    assert cache_admin.groesse_mensch(1_230_000_000) == "1,2 GB"


def test_cli_cache_zeigt_uebersicht_ohne_zu_loeschen(
        monkeypatch, tmp_path, capsys):
    _fuelle_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["bmtools", "cache"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "Höhenkacheln" in out and "Gesamt" in out
    assert (tmp_path / "bmtools" / "fm" / "d.json").exists()


def test_cli_cache_leeren_loescht(monkeypatch, tmp_path, capsys):
    _fuelle_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["bmtools", "cache", "--leeren"])
    assert cli.main() == 0
    assert "freigegeben" in capsys.readouterr().out
    assert not (tmp_path / "bmtools" / "fm").exists()
    assert not (tmp_path / "bmtools" / "terrain").exists()


def test_cli_cache_leeren_auf_leerem_cache(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cache_admin, "user_cache_dir",
                        lambda ns: str(tmp_path / ns))
    monkeypatch.setattr(sys, "argv", ["bmtools", "cache", "--clear"])
    assert cli.main() == 0
    assert "bereits leer" in capsys.readouterr().out
