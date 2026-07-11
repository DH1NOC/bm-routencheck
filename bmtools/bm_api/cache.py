"""Einfacher Disk-Cache mit TTL für API-Antworten."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from platformdirs import user_cache_dir


class Cache:
    def __init__(self, ttl_seconds: float, namespace: str = "bmtools"):
        self.ttl = ttl_seconds
        self.dir = Path(user_cache_dir(namespace))
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        return self.dir / f"{digest}.json"

    def get(self, key: str):
        path = self._path(key)
        try:
            envelope = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        if time.time() - envelope["ts"] > self.ttl:
            path.unlink(missing_ok=True)
            return None
        return envelope["data"]

    def set(self, key: str, data) -> None:
        envelope = {"ts": time.time(), "key": key, "data": data}
        self._path(key).write_text(json.dumps(envelope))
