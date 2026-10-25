"""Milestone 3: state shared across replicas (sessions, lockout, retries, budget).

Redis behaviour is exercised with fakeredis, which implements the Redis protocol in-process.
"""

from __future__ import annotations

import os
import threading

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.adapters.mock import MockCustomerSystem
from app.agent.planner import Budget
from app.config import DEFAULT_DATA_DIR, Settings
from app.kv import InMemoryKV, LockTimeout, RedisKV
from app.main import create_app
from app.tools import lockout_key
from tests.conftest import API_KEY, FIXED_TODAY

REAL_REDIS = os.environ.get("IVR_TEST_REDIS_URL")  # set to also run against a real server


def _redis() -> RedisKV:
    if REAL_REDIS:
        kv = RedisKV.from_url(REAL_REDIS)
        kv.r.flushdb()
        return kv
    return RedisKV(fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture
def redis_kv() -> RedisKV:
    return _redis()


def _replica(kv, **overrides):
    """One app instance. Replicas share only the KV store, like pods behind a load balancer."""
    settings = Settings(api_key=API_KEY, log_level="WARNING", env="test", **overrides)
    system = MockCustomerSystem(DEFAULT_DATA_DIR, today=lambda: FIXED_TODAY)
    return create_app(settings, system, kv=kv)


# ------------------------------------------------------------------ KV contract (both backends)
@pytest.fixture(params=["memory", "redis"])
def kv(request):
    if request.param == "memory":
        return InMemoryKV()
    return _redis()


def test_kv_set_get_and_only_if_absent(kv):
    assert kv.set("k", "1", 60)
    assert not kv.set("k", "2", 60, only_if_absent=True)
    assert kv.get("k") == "1"
    kv.delete("k")
    assert kv.get("k") is None


def test_kv_counters(kv):
    assert [kv.incr("c", 60) for _ in range(3)] == [1, 2, 3]
    kv.incr_float("f", 0.25, 60)
    assert kv.incr_float("f", 0.5, 60) == pytest.approx(0.75)


def test_kv_lock_is_exclusive(kv):
    with kv.lock("l", ttl_s=5, wait_s=1):
        holder_blocked = []

        def contender():
            try:
                with kv.lock("l", ttl_s=5, wait_s=0.2):
                    holder_blocked.append(False)
            except LockTimeout:
                holder_blocked.append(True)

        t = threading.Thread(target=contender)
        t.start()
        t.join()
    assert holder_blocked == [True]


def test_in_memory_kv_expiry_and_counter_window():
    now = [0.0]
    kv = InMemoryKV(clock=lambda: now[0])
    kv.set("k", "v", 10)
    kv.incr("c", 10)
    now[0] = 5
    assert kv.incr("c", 10) == 2  # the window starts at the first increment
    now[0] = 11
    assert kv.get("k") is None and kv.incr("c", 10) == 1


# ------------------------------------------------------------------ sessions across replicas
def test_any_replica_can_take_any_turn(redis_kv):
    a = TestClient(_replica(redis_kv))
    b = TestClient(_replica(redis_kv))
    h = {"X-API-Key": API_KEY}
    call_id = a.post("/v1/calls", json={}, headers=h).json()["call_id"]
    for client, text in [(b, "what's my balance"), (a, "10000001"), (b, "1234")]:
        reply = client.post(f"/v1/calls/{call_id}/turns", json={"text": text}, headers=h)
        assert reply.status_code == 200
    assert "$89.99" in reply.json()["reply"]


def test_sessions_are_json_with_ttl_and_no_raw_identifiers_in_keys(redis_kv):
    service = _replica(redis_kv).state.service
    state = service.start_call("test")
    for text in ["balance", "10000001", "1234"]:
        service.take_turn(state["call_id"], text)
    r = redis_kv.r
    key = f"ivr:call:{state['call_id']}"
    assert 0 < r.ttl(key) <= 1800
    assert all("10000001" not in k for k in r.keys("*"))
    assert "1234" not in r.get(key)  # credentials leave state once used


def test_turns_of_one_call_are_serialized(redis_kv):
    service = _replica(redis_kv).state.service
    call_id = service.start_call("test")["call_id"]
    turns = []

    def take():
        turns.append(service.take_turn(call_id, "blah")["turn"])

    threads = [threading.Thread(target=take) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(turns) == [1, 2, 3]  # no lost update: every turn saw the previous one


# ------------------------------------------------------------------ webhook retries
def test_twilio_retry_is_replayed_not_rerun(redis_kv):
    a = TestClient(_replica(redis_kv))
    b = TestClient(_replica(redis_kv))
    a.post("/voice/twilio/incoming", data={"CallSid": "CA1"})
    first = a.post(
        "/voice/twilio/gather",
        data={"CallSid": "CA1", "SpeechResult": "what's my balance"},
        headers={"I-Twilio-Idempotency-Token": "tok-1"},
    )
    retry = b.post(  # Twilio retried; the load balancer sent it to another replica
        "/voice/twilio/gather",
        data={"CallSid": "CA1", "SpeechResult": "what's my balance"},
        headers={"I-Twilio-Idempotency-Token": "tok-1"},
    )
    assert retry.text == first.text
    service = a.app.state.service
    assert service.get("CA1")["turn"] == 1
    b.post(
        "/voice/twilio/gather",
        data={"CallSid": "CA1", "Digits": "10000001"},
        headers={"I-Twilio-Idempotency-Token": "tok-2"},
    )
    assert service.get("CA1")["turn"] == 2


# ------------------------------------------------------------------ lockout across calls
def _attempt(service, account, pin):
    state = service.start_call("test")
    for text in ["balance", account, pin]:
        state = service.take_turn(state["call_id"], text)
    return state


def test_lockout_spans_calls_and_replicas(redis_kv):
    a = _replica(redis_kv, lockout_max_failures=4).state.service
    b = _replica(redis_kv, lockout_max_failures=4).state.service
    for service in (a, b, a):
        assert not _attempt(service, "10000001", "0000")["authenticated"]
    # Four failures in three calls (the fourth one locks), then the right PIN is refused too.
    state = _attempt(b, "10000001", "0000")
    state = _attempt(a, "10000001", "1234")
    assert not state["authenticated"]
    assert state["status"] == "escalated" and state["handoff"]["reason"] == "auth_failed"
    # Other accounts are unaffected.
    assert _attempt(b, "10000002", "4321")["authenticated"]


def test_lockout_covers_unknown_accounts_identically(redis_kv):
    service = _replica(redis_kv, lockout_max_failures=2).state.service
    replies = {}
    for account in ("10000001", "19999999"):  # real and non-existent
        for _ in range(2):
            _attempt(service, account, "0000")
        replies[account] = _attempt(service, account, "0000")["response"]
    assert replies["10000001"] == replies["19999999"]  # no enumeration oracle


def test_successful_verification_resets_the_counter(redis_kv):
    service = _replica(redis_kv, lockout_max_failures=3).state.service
    _attempt(service, "10000001", "0000")
    _attempt(service, "10000001", "0000")
    assert _attempt(service, "10000001", "1234")["authenticated"]
    assert redis_kv.get(lockout_key("10000001")) is None


# ------------------------------------------------------------------ shared planner budget
def test_planner_budget_is_shared(redis_kv):
    a, b = Budget(0.01, kv=redis_kv), Budget(0.01, kv=redis_kv)
    a.spend(0.006)
    b.spend(0.006)
    assert a.spent_today == pytest.approx(0.012) and not a.available() and not b.available()


# ------------------------------------------------------------------ readiness
class _DownRedis(fakeredis.FakeRedis):
    def ping(self, **kwargs):
        raise ConnectionError("redis down")


def test_ready_is_503_when_shared_state_is_down():
    client = TestClient(_replica(RedisKV(_DownRedis(decode_responses=True))))
    resp = client.get("/health/ready")
    assert resp.status_code == 503 and resp.json()["state_store"] == "unavailable"


def test_ready_reports_backend(client):
    body = client.get("/health/ready").json()
    assert body["status"] == "ready" and body["state_backend"] == "memory"
