"""Call session storage. In-memory for Milestone 1; Redis/DynamoDB implement the same Protocol."""

from __future__ import annotations

import threading
import time
from typing import Any, Protocol


class SessionStore(Protocol):
    def get(self, call_id: str) -> dict[str, Any] | None: ...

    def put(self, call_id: str, state: dict[str, Any]) -> None: ...


class InMemorySessionStore:
    """Single-process only. Horizontal scaling requires the Redis store (Milestone 3)."""

    def __init__(self, ttl_s: int = 1800, max_sessions: int = 10_000) -> None:
        self._ttl = ttl_s
        self._max = max_sessions
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, call_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._data.get(call_id)
            if item is None:
                return None
            expires, state = item
            if expires < time.monotonic():
                del self._data[call_id]
                return None
            return state

    def put(self, call_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            if len(self._data) >= self._max and call_id not in self._data:
                self._evict_expired()
            self._data[call_id] = (time.monotonic() + self._ttl, state)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        for key in [k for k, (exp, _) in self._data.items() if exp < now]:
            del self._data[key]
        if len(self._data) >= self._max:  # still full: drop the oldest-expiring session
            del self._data[min(self._data, key=lambda k: self._data[k][0])]

    def __len__(self) -> int:
        return len(self._data)
