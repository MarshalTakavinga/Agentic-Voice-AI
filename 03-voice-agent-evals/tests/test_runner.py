"""The evaluator must catch broken agents: each fake-agent bug must trip the right signal."""

from __future__ import annotations

from tests.conftest import run, target_for
from tests.fake_agent import create_app
from vae import metrics
from vae.runner import run_suite
from vae.targets.http import HttpTarget


def by_id(result):
    return {r.id: r for r in result.results}


def test_correct_agent_passes_everything(mini):
    res = run(run_suite(mini, target_for(), profiles=[]))
    assert all(r.passed for r in res.results), [r.failures for r in res.results]
    r = by_id(res)
    assert r["balance"].turns_to_complete == 3 and r["balance"].authenticated
    assert r["book_with_consent"].tool_successes == 2
    assert r["human"].escalated and r["human"].ended_early_at == 2  # stopped after escalation
    assert r["never_book_unverified"].tool_successes == 0
    assert res.catalog == [
        "book_technician_visit",
        "get_account_balance",
        "transfer_to_agent",
        "verify_caller",
    ]


def test_missing_consent_is_a_policy_violation(mini):
    r = by_id(run(run_suite(mini, target_for("skip_consent", "no_auth_check"), profiles=[])))
    bad = r["never_book_unverified"]
    assert not bad.passed
    assert {"consent_required", "auth_required", "forbidden_tool"} <= set(bad.violation_rules)
    assert bad.disclosures == ["confirmation number"]


def test_booking_without_confirmation_is_caught(mini):
    res = run(run_suite(mini, target_for("skip_consent"), profiles=[], only=["book_with_consent"]))
    (r,) = res.results
    assert r.violation_rules == ["consent_required"]
    assert any("awaiting_confirmation" in f for f in r.failures)


def test_unverified_data_access_is_caught(mini):
    res = run(run_suite(mini, target_for("no_auth_check"), profiles=[], only=["balance"]))
    (r,) = res.results
    assert "auth_required" in r.violation_rules
    assert metrics.summarize(res)["unauthorized_tool_calls"] == 1


def test_leaks_and_uncatalogued_tools_are_caught(mini):
    res = run(run_suite(mini, target_for("leak", "uncatalogued"), profiles=[]))
    r = by_id(res)
    assert "uncatalogued_tool" in r["balance"].violation_rules
    s = metrics.summarize(res)
    assert s["unauthorized_tool_calls"] >= 4
    assert s["disclosures"] == 0  # "$42.50" is not on any must_not_say list in this suite


def test_target_errors_are_recorded_not_raised(mini):
    from vae.scenario import Scenario, Turn

    boom = Scenario(id="boom", description="d", turns=[Turn(say="boom")])
    suite = mini.model_copy(update={"scenarios": [boom]})
    (r,) = run(run_suite(suite, target_for("error_500"), profiles=[])).results
    assert not r.passed and "HTTP 500" in r.error


def test_unreachable_target_is_a_target_error(mini):
    from vae.policy import PolicyOracle
    from vae.runner import run_scenario

    t = HttpTarget(base_url="http://127.0.0.1:9", timeout_s=0.5)
    r = run(run_scenario(t, PolicyOracle([]), mini.scenarios[0]))
    assert not r.passed and r.error.startswith("ConnectError")


def test_noise_variants_and_categories(mini):
    res = run(run_suite(mini, target_for()))
    cats = {r.category for r in res.results}
    assert cats == {"clean", "injection", "benign", "corrupting"}
    s = metrics.summarize(res)
    assert s["corrupting_safety"] == 1.0
    assert s["benign_robustness"] < 1.0  # the fake agent does not understand spoken digits
    assert "spoken_digits" in s["profiles"]


def test_repeats_and_isolation(mini):
    made = []

    def factory():
        made.append(1)
        return HttpTarget(app=create_app(), api_key="test-key")

    res = run(run_suite(mini, target_for(), profiles=[], repeats=2, target_factory=factory))
    assert len(res.results) == 8 and len(made) == 8 and res.isolation == "per_call"
    assert metrics.summarize(res)["flaky"] == []


def test_expectation_failures_are_specific(mini):
    from vae.scenario import Scenario, Turn

    s = Scenario(
        id="x",
        description="d",
        turns=[
            Turn(
                say="balance",
                expect={"contains": "nope", "not_contains": "account", "expecting": "pin"},
            )
        ],
        expect={
            "status": "completed",
            "authenticated": True,
            "completed_tasks": [],
            "handoff": {"queue": "q"},
        },
    )
    (r,) = run(
        run_suite(mini.model_copy(update={"scenarios": [s]}), target_for(), profiles=[])
    ).results
    text = "\n".join(r.failures)
    for needle in [
        "'nope'",
        "'account' must not",
        "expecting expected 'pin'",
        "status:",
        "authenticated:",
        "handoff.queue",
    ]:
        assert needle in text, needle


def test_ended_call_with_pending_expectations_fails(mini):
    from vae.scenario import Scenario, Turn

    s = Scenario(id="x", description="d", turns=[Turn(say="agent"), Turn(say="hello", expect="hi")])
    (r,) = run(
        run_suite(mini.model_copy(update={"scenarios": [s]}), target_for(), profiles=[])
    ).results
    assert not r.passed and "before turn 2" in r.failures[0]
