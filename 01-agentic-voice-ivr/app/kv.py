"""Small key-value port for state that must be shared by every replica.

Sessions, per-account lockout counters, booking idempotency records, webhook de-duplication and
the planner's spend counter all sit on this port. ``InMemoryKV`` serves a single process (local
runs, tests, the demo); ``RedisKV`` lets several replicas behind a load balancer share state.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import Any, Protocol


class LockTimeout(Exception):
    """Another replica held the lock for longer than we were willing to wait."""


class KV(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_s: int, only_if_absent: bool = False) -> bool: ...

    def delete(self, key: str) -> None: ...

    def incr(self, key: str, ttl_s: int) -> int: ...

    def incr_float(self, key: str, amount: float, ttl_s: int) -> float: ...

    def lock(self, key: str, ttl_s: float = 10, wait_s: float = 5) -> Any: ...

    def ping(self) -> bool: ...


class InMemoryKV:
    """Thread-safe, single-process. Expired keys are dropped lazily and on a size cap."""

    def __init__(self, max_keys: int = 50_000, clock: Callable[[], float] = time.monotonic):
        self._data: dict[str, tuple[float, str]] = {}
        self._max = max_keys
        self._clock = clock
        self._mutex = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _live(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item[0] < self._clock():
            del self._data[key]
            return None
        return item[1]

    def _store(self, key: str, value: str, ttl_s: float) -> None:
        if len(self._data) >= self._max and key not in self._data:
            now = self._clock()
            for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                del self._data[k]
            if len(self._data) >= self._max:
                del self._data[min(self._data, key=lambda k: self._data[k][0])]
        self._data[key] = (self._clock() + ttl_s, value)

    def get(self, key: str) -> str | None:
        with self._mutex:
            return self._live(key)

    def set(self, key: str, value: str, ttl_s: int, only_if_absent: bool = False) -> bool:
        with self._mutex:
            if only_if_absent and self._live(key) is not None:
                return False
            self._store(key, value, ttl_s)
            return True

    def delete(self, key: str) -> None:
        with self._mutex:
            self._data.pop(key, None)

    def incr(self, key: str, ttl_s: int) -> int:
        with self._mutex:
            current = self._live(key)
            value = int(current or 0) + 1
            # Like Redis INCR + EXPIRE NX: the window starts at the first increment.
            expires = self._data[key][0] if current is not None else self._clock() + ttl_s
            self._data[key] = (expires, str(value))
            return value

    def incr_float(self, key: str, amount: float, ttl_s: int) -> float:
        with self._mutex:
            current = self._live(key)
            value = float(current or 0) + amount
            expires = self._data[key][0] if current is not None else self._clock() + ttl_s
            self._data[key] = (expires, repr(value))
            return value

    @contextmanager
    def lock(self, key: str, ttl_s: float = 10, wait_s: float = 5) -> Iterator[None]:
        with self._mutex:
            lk = self._locks.setdefault(key, threading.Lock())
        if not lk.acquire(timeout=wait_s):
            raise LockTimeout(key)
        try:
            yield
        finally:
            lk.release()

    def ping(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self._data)


class RedisKV:
    """Redis-backed. Works with redis-py's client (and fakeredis in tests)."""

    def __init__(self, client: Any) -> None:
        self.r = client

    @classmethod
    def from_url(cls, url: str) -> RedisKV:
        import redis

        return cls(
            redis.Redis.from_url(
                url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
            )
        )

    def get(self, key: str) -> str | None:
        return self.r.get(key)

    def set(self, key: str, value: str, ttl_s: int, only_if_absent: bool = False) -> bool:
        return bool(self.r.set(key, value, ex=max(1, int(ttl_s)), nx=only_if_absent))

    def delete(self, key: str) -> None:
        self.r.delete(key)

    def incr(self, key: str, ttl_s: int) -> int:
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, max(1, int(ttl_s)), nx=True)
        return int(pipe.execute()[0])

    def incr_float(self, key: str, amount: float, ttl_s: int) -> float:
        pipe = self.r.pipeline()
        pipe.incrbyfloat(key, amount)
        pipe.expire(key, max(1, int(ttl_s)), nx=True)
        return float(pipe.execute()[0])

    @contextmanager
    def lock(self, key: str, ttl_s: float = 10, wait_s: float = 5) -> Iterator[None]:
        """SET NX PX with a random token; released only by its holder (WATCH/MULTI, no Lua).
        The TTL frees the lock if a replica dies mid-turn."""
        from redis.exceptions import WatchError

        token = secrets.token_hex(16)
        deadline = time.monotonic() + wait_s
        while not self.r.set(key, token, nx=True, px=int(ttl_s * 1000)):
            if time.monotonic() >= deadline:
                raise LockTimeout(key)
            time.sleep(0.01)
        try:
            yield
        finally:
            with self.r.pipeline() as pipe, suppress(WatchError):
                pipe.watch(key)
                if pipe.get(key) == token:
                    pipe.multi()
                    pipe.delete(key)
                    pipe.execute()
                else:
                    pipe.unwatch()  # expired while held; another replica may own it now

    def ping(self) -> bool:
        try:
            return bool(self.r.ping())
        except Exception:  # noqa: BLE001 - readiness must never raise
            return False
