"""Tests Brandmeister-Client: Rate-Limit-Verhalten (HTTP 429)."""
import time

import httpx
import pytest

from bmtools.bm_api import client as bm_client
from bmtools.bm_api.client import BrandmeisterClient


def _client(handler, tmp_path) -> BrandmeisterClient:
    c = BrandmeisterClient(refresh=True)
    c._http = httpx.Client(transport=httpx.MockTransport(handler),
                           base_url=bm_client.BASE_URL)
    for cache in (c._device_cache, c._profile_cache, c._misc_cache):
        cache.dir = tmp_path
    return c


def test_429_wartet_retry_after_ab_und_drosselt(tmp_path, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"ok": 1})

    c = _client(handler, tmp_path)
    assert c._fetch_json("/x", c._misc_cache, "x") == {"ok": 1}
    assert len(calls) == 3
    assert sleeps.count(7.0) == 2          # Retry-After respektiert
    assert c._delay > bm_client.REQUEST_DELAY  # Folge-Requests gedrosselt


def test_429_dauerhaft_meldet_rate_limit_mit_cache_hinweis(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    c = _client(lambda r: httpx.Response(429), tmp_path)
    with pytest.raises(RuntimeError, match="Rate-Limit"):
        c._fetch_json("/x", c._misc_cache, "x")


def test_retry_after_als_datum_faellt_auf_obergrenze(tmp_path, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) < 2:
            return httpx.Response(
                429, headers={"Retry-After": "Mon, 27 Jul 2026 16:00:00 GMT"})
        return httpx.Response(200, json={"ok": 1})

    c = _client(handler, tmp_path)
    assert c._fetch_json("/x", c._misc_cache, "x") == {"ok": 1}
    assert bm_client.MAX_RETRY_AFTER in sleeps
