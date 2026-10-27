"""Async scenario runner: each scenario is one call against the target."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from vae import __version__, promscrape
from vae.noise import make_variants
from vae.policy import PolicyOracle, disclosures
from vae.scenario import Scenario, Suite, TurnExpect
from vae.targets.base import CallEndedError, Target, TargetError, TurnView

REPLY_CHARS = 300  # replies are synthetic, but keep result files compact


class TurnRecord(BaseModel):
    index: int
    sent: str
    reply: str
    latency_ms: float
    status: str
    expecting: str | None = None
    authenticated: bool = False
    awaiting_confirmation: bool = False
    completed_tasks: list[str] = Field(default_factory=list)
    nlu_source: str | None = None


class ScenarioResult(BaseModel):
    id: str
    base_id: str
    profile: str | None = None
    category: str
    tags: list[str] = Field(default_factory=list)
    repeat: int = 0
    passed: bool
    failures: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    violation_rules: list[str] = Field(default_factory=list)
    disclosures: list[str] = Field(default_factory=list)
    error: str | None = None
    turns: list[TurnRecord] = Field(default_factory=list)
    final_status: str | None = None
    authenticated: bool = False
    completed_tasks: list[str] = Field(default_factory=list)
    expected_tasks: list[str] | None = None
    turns_to_complete: int | None = None
    expected_escalation: bool | None = None
    escalated: bool = False
    handoff: dict[str, Any] | None = None
    tool_successes: int = 0
    tool_refusals: int = 0
    ended_early_at: int | None = None
    duration_ms: float = 0.0


class RunResult(BaseModel):
    suite: str
    fingerprint: str
    target: str
    vae_version: str = __version__
    started_at: str
    seed: int
    profiles: list[str]
    concurrency: int
    repeats: int
    catalog: list[str] = Field(default_factory=list)
    results: list[ScenarioResult]
    server_latency: dict[str, Any] = Field(default_factory=dict)
    wall_s: float = 0.0
    isolation: str = "shared"
    summary: dict[str, Any] = Field(default_factory=dict)
    gates: list[dict[str, Any]] = Field(default_factory=list)


def _check_turn(i: int, exp: TurnExpect, view: TurnView) -> list[str]:
    out = []
    reply = view.reply.lower()
    for s in exp.contains:
        if s.lower() not in reply:
            out.append(f"turn {i}: expected {s!r} in reply {view.reply[:120]!r}")
    for s in exp.not_contains:
        if s.lower() in reply:
            out.append(f"turn {i}: {s!r} must not be in reply")
    for key in ("expecting", "awaiting_confirmation", "status"):
        want = getattr(exp, key)
        if want is not None and getattr(view, key) != want:
            out.append(f"turn {i}: {key} expected {want!r}, got {getattr(view, key)!r}")
    return out


def _check_final(s: Scenario, view: TurnView) -> list[str]:
    e, out = s.expect, []
    if e.status is not None and view.status != e.status:
        out.append(f"status: expected {e.status!r}, got {view.status!r}")
    if e.completed_tasks is not None and view.completed_tasks != e.completed_tasks:
        out.append(f"completed_tasks: expected {e.completed_tasks}, got {view.completed_tasks}")
    if e.authenticated is not None and view.authenticated != e.authenticated:
        out.append(f"authenticated: expected {e.authenticated}, got {view.authenticated}")
    if e.handoff is not None:
        h = view.handoff or {}
        for key in ("reason", "queue"):
            want = getattr(e.handoff, key)
            if want is not None and h.get(key) != want:
                out.append(f"handoff.{key}: expected {want!r}, got {h.get(key)!r}")
    return out


async def run_scenario(
    target: Target, oracle: PolicyOracle, scenario: Scenario, repeat: int = 0
) -> ScenarioResult:
    started = time.perf_counter()
    result = ScenarioResult(
        id=scenario.id,
        base_id=scenario.base_id or scenario.id,
        profile=scenario.profile,
        category=scenario.category,
        tags=scenario.tags,
        repeat=repeat,
        passed=False,
        expected_tasks=scenario.expect.completed_tasks,
        expected_escalation=scenario.expects_escalation,
    )
    failures: list[str] = []
    try:
        view = await target.start_call()
        views = [view]
        for i, turn in enumerate(scenario.turns, start=1):
            if view.status != "in_progress":
                result.ended_early_at = i
                break
            t0 = time.perf_counter()
            try:
                view = await target.send_turn(view.call_id, turn.text)
            except CallEndedError:
                result.ended_early_at = i
                break
            latency = (time.perf_counter() - t0) * 1000
            views.append(view)
            result.turns.append(
                TurnRecord(
                    index=i,
                    sent=turn.text,
                    reply=view.reply[:REPLY_CHARS],
                    latency_ms=round(latency, 3),
                    status=view.status,
                    expecting=view.expecting,
                    authenticated=view.authenticated,
                    awaiting_confirmation=view.awaiting_confirmation,
                    completed_tasks=view.completed_tasks,
                    nlu_source=view.nlu_source,
                )
            )
            failures += _check_turn(i, turn.expect, view)
        if result.ended_early_at is not None:
            pending = scenario.turns[result.ended_early_at - 1 :]
            if any(t.expect != TurnExpect() for t in pending):
                failures.append(
                    f"call ended ({view.status}) before turn {result.ended_early_at}, "
                    "which had expectations"
                )
        failures += _check_final(scenario, view)
        events = await target.tool_events(view.call_id)
        violations = oracle.check(events, views, scenario.safety.forbidden_tools)
        spoken = [
            rec.reply
            for rec, turn in zip(result.turns, scenario.turns, strict=False)
            if not turn.setup
        ]
        leaked = disclosures(spoken, scenario.safety.must_not_say)
        result.violations = [str(v) for v in violations]
        result.violation_rules = [v.rule for v in violations]
        result.disclosures = leaked
        failures += [f"policy {v}" for v in result.violations]
        failures += [f"disclosure: {s!r} was spoken" for s in leaked]
        result.final_status = view.status
        result.authenticated = view.authenticated
        result.completed_tasks = view.completed_tasks
        result.escalated = view.status == "escalated"
        result.handoff = view.handoff
        result.tool_successes = sum(e.ok for e in events)
        result.tool_refusals = sum(not e.ok for e in events)
        want = set(scenario.expect.completed_tasks or [])
        if want:
            result.turns_to_complete = next(
                (r.index for r in result.turns if want <= set(r.completed_tasks)), None
            )
    except TargetError as exc:
        result.error = str(exc)
        failures.append(f"target error: {exc}")
    result.failures = failures
    result.passed = not failures
    result.duration_ms = round((time.perf_counter() - started) * 1000, 3)
    return result


def expand(suite: Suite, profiles: list[str] | None = None, seed: int | None = None) -> list:
    """The suite's scenarios plus their noise variants."""
    names = suite.noise.profiles if profiles is None else profiles
    seed = suite.noise.seed if seed is None else seed
    return [*suite.scenarios, *make_variants(suite.scenarios, names, seed)]


async def run_suite(
    suite: Suite,
    target: Target,
    *,
    profiles: list[str] | None = None,
    seed: int | None = None,
    concurrency: int = 8,
    repeats: int = 1,
    only: list[str] | None = None,
    target_factory: Callable[[], Target] | None = None,
) -> RunResult:
    """Run every scenario (and noise variant) as one call.

    ``target_factory`` gives each call a fresh target. Use it for stateful agents: per-account
    lockouts, bookings and other shared state otherwise let one scenario change another's
    outcome. Catalog and metrics are still read from ``target``.
    """
    names = suite.noise.profiles if profiles is None else profiles
    seed = suite.noise.seed if seed is None else seed
    scenarios = expand(suite, names, seed)
    if only:
        scenarios = [s for s in scenarios if any(s.id == o or s.base_id == o for o in only)]
    catalog = await target.catalog()
    oracle = PolicyOracle(catalog, suite.target.auth_tools, suite.target.tool_aliases)
    sm = suite.target.server_metrics
    before = await target.metrics_text() if (sm.turn_latency or sm.tool_latency) else None

    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(s: Scenario, r: int) -> ScenarioResult:
        async with sem:
            if target_factory is None:
                return await run_scenario(target, oracle, s, r)
            fresh = target_factory()
            try:
                return await run_scenario(fresh, oracle, s, r)
            finally:
                await fresh.aclose()

    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    results = await asyncio.gather(*(one(s, r) for r in range(repeats) for s in scenarios))
    wall = time.perf_counter() - t0
    after = await target.metrics_text() if before is not None else None
    server: dict[str, Any] = {}
    if sm.turn_latency:
        server["turn"] = promscrape.summarize(before, after, sm.turn_latency, None).get("all")
    if sm.tool_latency:
        server["tools"] = promscrape.summarize(before, after, sm.tool_latency, sm.tool_label)
    return RunResult(
        suite=suite.name,
        fingerprint=suite.fingerprint,
        target=target.name,
        started_at=started_at,
        seed=seed,
        profiles=names,
        concurrency=concurrency,
        repeats=repeats,
        catalog=sorted(t.name for t in catalog),
        results=list(results),
        server_latency={k: v for k, v in server.items() if v},
        wall_s=round(wall, 3),
        isolation="per_call" if target_factory else "shared",
    )
