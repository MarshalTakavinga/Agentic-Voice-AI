from __future__ import annotations

import json

from tests.conftest import run, target_for
from vae import compare, metrics, report
from vae.runner import run_suite
from vae.scenario import Gates


def test_percentile():
    assert metrics.percentile([], 0.5) is None
    assert metrics.percentile([5.0], 0.95) == 5.0
    assert metrics.percentile([1, 2, 3, 4], 0.5) == 2.5
    assert metrics.percentile(list(range(101)), 0.95) == 95.0


def test_summary_and_escalation_confusion(mini):
    res = run(run_suite(mini, target_for(), profiles=[]))
    s = metrics.summarize(res)
    assert s["pass_rate"] == 1.0 and s["task_completion_rate"] == 1.0
    assert s["escalation"]["correct_escalations"] == 1
    assert s["latency"]["turns"] == sum(len(r.turns) for r in res.results)
    assert s["benign_robustness"] is None


def test_gates_pass_fail_and_skip(mini):
    res = run(run_suite(mini, target_for("skip_consent", "no_auth_check"), profiles=[]))
    s = metrics.summarize(res)
    gates = {g["gate"]: g for g in metrics.evaluate_gates(s, Gates(max_p95_turn_ms=10_000))}
    assert gates["unauthorized tool calls"]["result"] == "fail"
    assert gates["benign ASR-noise robustness"]["result"] == "skipped"
    assert gates["p95 turn latency (ms)"]["result"] == "pass"
    assert not metrics.gates_passed(list(gates.values()))


def test_latency_gate(mini):
    res = run(run_suite(mini, target_for(slow_ms=30), profiles=[], only=["balance"]))
    gates = metrics.evaluate_gates(metrics.summarize(res), Gates(max_p95_turn_ms=10))
    assert [g["result"] for g in gates if "latency" in g["gate"]] == ["fail"]


def test_report_renders_every_section(mini):
    res = run(run_suite(mini, target_for("leak")))
    res.summary = metrics.summarize(res)
    res.gates = metrics.evaluate_gates(res.summary, mini.gates)
    md = report.render(res)
    for heading in [
        "## Gates",
        "## Headline",
        "## By category",
        "## ASR-noise profiles",
        "## Prompt-injection",
        "## Clean scenarios",
        "## Failures",
    ]:
        assert heading in md, heading
    assert "synthetic" in md.lower()


def _dump(res) -> dict:
    res.summary = metrics.summarize(res)
    return json.loads(res.model_dump_json())


def test_compare_flags_regressions(mini):
    good = _dump(run(run_suite(mini, target_for())))
    bad = _dump(run(run_suite(mini, target_for("skip_consent", "no_auth_check"))))
    c = compare.compare(good, bad)
    assert not c.ok
    assert "never_book_unverified" in c.newly_failing
    assert any("Unauthorized" in r for r in c.regressions)
    md = compare.render(c, "base.json", "cand.json")
    assert "FAIL" in md and "never_book_unverified" in md
    assert compare.compare(bad, good).newly_passing


def test_compare_latency_floor_and_skip(mini):
    base = _dump(run(run_suite(mini, target_for(), profiles=[], only=["balance"])))
    slow = _dump(run(run_suite(mini, target_for(slow_ms=40), profiles=[], only=["balance"])))
    assert not compare.compare(base, slow).ok
    assert compare.compare(base, slow, p95_increase=None).ok
    assert compare.compare(base, base).ok
