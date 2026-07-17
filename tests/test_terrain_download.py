"""_download: Netzfehler werden wiederholt und als TerrainError gemeldet.

Hintergrund (Beta-Befund 2026-07-17): Ein httpx.ReadTimeout beim
Kachel-Download riss den ganzen Lauf ab — die Pipeline reagiert nur
auf TerrainError mit dem Horizontmodell-Fallback, rohe httpx-Fehler
liefen daran vorbei.
"""
from __future__ import annotations

import time

import httpx
import pytest

from bmtools.routelib import terrain


@pytest.fixture
def modell(tmp_path, monkeypatch):
    monkeypatch.setattr(terrain, "user_cache_dir",
                        lambda name: str(tmp_path))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return terrain.TerrainModel()


def test_transienter_fehler_wird_wiederholt(modell, monkeypatch):
    versuche = []

    def get(url):
        versuche.append(url)
        if len(versuche) < 2:
            raise httpx.ReadTimeout("langsam")
        return httpx.Response(200, content=b"png-daten")

    monkeypatch.setattr(modell._http, "get", get)
    modell._download(1, 2)
    assert len(versuche) == 2
    assert modell._tile_path(1, 2).read_bytes() == b"png-daten"
    assert modell.tiles_downloaded == 1


def test_dauerfehler_wird_zum_terrainerror(modell, monkeypatch):
    versuche = []

    def get(url):
        versuche.append(url)
        raise httpx.ReadTimeout("tot")

    monkeypatch.setattr(modell._http, "get", get)
    with pytest.raises(terrain.TerrainError, match="ReadTimeout"):
        modell._download(1, 2)
    assert len(versuche) == terrain.DOWNLOAD_VERSUCHE


def test_fehlerstatus_wird_zum_terrainerror(modell, monkeypatch):
    monkeypatch.setattr(modell._http, "get",
                        lambda url: httpx.Response(503))
    with pytest.raises(terrain.TerrainError, match="HTTP 503"):
        modell._download(1, 2)
