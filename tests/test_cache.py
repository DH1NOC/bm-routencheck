"""Tests Disk-Cache (TTL, defekte Einträge)."""
import time
from pathlib import Path

from bmtools.bm_api.cache import Cache


def _cache(tmp_path: Path, ttl: float = 100.0) -> Cache:
    c = Cache(ttl)
    c.dir = tmp_path
    return c


def test_roundtrip_und_fehlender_eintrag(tmp_path: Path):
    c = _cache(tmp_path)
    assert c.get("nix") is None
    c.set("k", {"a": [1, 2, "ü"]})
    assert c.get("k") == {"a": [1, 2, "ü"]}


def test_ablauf_nach_ttl_loescht_datei(tmp_path: Path, monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    c = _cache(tmp_path, ttl=100.0)
    c.set("k", "wert")

    now += 99.0
    assert c.get("k") == "wert"
    now += 2.0  # jetzt 101 s alt
    assert c.get("k") is None
    assert list(tmp_path.iterdir()) == []  # abgelaufener Eintrag entfernt


def test_defekter_eintrag_wird_ignoriert(tmp_path: Path):
    c = _cache(tmp_path)
    c.set("k", "wert")
    [f] = tmp_path.iterdir()
    f.write_text("kein json {")
    assert c.get("k") is None
