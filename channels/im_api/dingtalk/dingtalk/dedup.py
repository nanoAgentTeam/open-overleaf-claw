"""Simple in-memory dedup store with TTL cleanup."""

from __future__ import annotations

import threading
import time


class DedupStore:
    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, float] = {}
        self._lock = threading.Lock()

    def _cleanup(self, now: float) -> None:
        expired = [k for k, ts in self._store.items() if now - ts > self.ttl_seconds]
        for key in expired:
            self._store.pop(key, None)

    def is_processed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._cleanup(now)
            return key in self._store

    def mark_processed(self, key: str) -> None:
        with self._lock:
            self._store[key] = time.time()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
