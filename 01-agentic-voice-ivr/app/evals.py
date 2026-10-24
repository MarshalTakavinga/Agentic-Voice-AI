"""Scenario-based conversation evaluation. Shared by pytest and scripts/run_evals.py.

These are synthetic regression scenarios. Their pass rate measures whether the agent behaves
as designed on scripted inputs; it is not a measure of real-world containment or accuracy.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.service import CallService

SCENARIOS_PATH = Path(__file__).resolve().parent.parent / "evals" / "scenarios.json"


@dataclass
class ScenarioResult:
    id: str
    passed: bool
    turns: int
    status: str
    completed_tasks: list[str]
    failures: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def run_scenario(service: CallService, scenario: dict[str, Any]) -> ScenarioResult:
    state = service.start_call(channel="eval")
    failures: list[str] = []
    started = time.perf_counter()
    for i, turn in enumerate(scenario["turns"], start=1):
        state = service.take_turn(state["call_id"], turn["say"])
        expected = turn.get("expect")
        if expected and expected.lower() not in state["response"].lower():
            failures.append(f"turn {i}: expected {expected!r} in reply {state['response']!r}")
    elapsed = (time.perf_counter() - started) * 1000

    exp = scenario.get("expect", {})
    handoff = state.get("handoff") or {}
    checks = {
        "status": state["status"],
        "completed_tasks": state.get("completed_tasks", []),
        "authenticated": state.get("authenticated", False),
        "handoff_reason": handoff.get("reason"),
        "handoff_queue": handoff.get("queue"),
    }
    for key, actual in checks.items():
        if key in exp and exp[key] != actual:
            failures.append(f"{key}: expected {exp[key]!r}, got {actual!r}")
    return ScenarioResult(
        scenario["id"],
        not failures,
        len(scenario["turns"]),
        state["status"],
        state.get("completed_tasks", []),
        failures,
        round(elapsed, 2),
    )


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    n = len(results)
    return {
        "scenarios": n,
        "passed": sum(r.passed for r in results),
        "pass_rate": round(sum(r.passed for r in results) / n, 3) if n else 0.0,
        "escalated": sum(r.status == "escalated" for r in results),
        "avg_turns": round(sum(r.turns for r in results) / n, 2) if n else 0.0,
        "avg_agent_ms_per_turn": round(
            sum(r.latency_ms for r in results) / max(sum(r.turns for r in results), 1), 2
        ),
    }
