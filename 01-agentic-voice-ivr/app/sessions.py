"""Call session storage on the shared key-value port.

With ``InMemoryKV`` this is single-process; with ``RedisKV`` any replica can take any turn of any
call, so the load balancer needs no sticky sessions.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from typing import Any, Protocol

from app.kv import KV, InMemoryKV


class SessionStore(Protocol):
    kv: KV

    def get(self, call_id: str) -> dict[str, Any] | None: ...

    def put(self, call_id: str, state: dict[str, Any]) -> None: ...

    def lock(self, call_id: str) -> AbstractContextManager[Any]: ...


class KVSessionStore:
    """Sessions serialized as JSON with a sliding TTL. ``lock`` serializes turns of one call
    across replicas (e.g. a webhook retry racing the original request)."""

    PREFIX = "ivr:call:"

    def __init__(self, kv: KV, ttl_s: int = 1800) -> None:
        self.kv = kv
        self._ttl = ttl_s

    def get(self, call_id: str) -> dict[str, Any] | None:
        raw = self.kv.get(self.PREFIX + call_id)
        return json.loads(raw) if raw is not None else None

    def put(self, call_id: str, state: dict[str, Any]) -> None:
        self.kv.set(self.PREFIX + call_id, json.dumps(state, separators=(",", ":")), self._ttl)

    def lock(self, call_id: str) -> AbstractContextManager[Any]:
        return self.kv.lock(f"ivr:lock:{call_id}", ttl_s=10, wait_s=5)


class InMemorySessionStore(KVSessionStore):
    """Single-process store (local runs, tests, the demo)."""

    def __init__(self, ttl_s: int = 1800, max_sessions: int = 10_000) -> None:
        super().__init__(InMemoryKV(max_keys=max_sessions), ttl_s)

    def __len__(self) -> int:
        return len(self.kv)  # type: ignore[arg-type]
