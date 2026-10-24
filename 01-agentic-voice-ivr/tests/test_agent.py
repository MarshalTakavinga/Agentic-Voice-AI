import pytest

from app.evals import load_scenarios, run_scenario
from tests.conftest import converse


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["id"])
def test_conversation_scenarios(service, scenario):
    result = run_scenario(service, scenario)
    assert result.passed, "\n".join(result.failures)


def test_credentials_are_not_retained_in_state(service):
    state = converse(service, "balance", "10000001", "1234")
    assert state["authenticated"]
    assert "pin" not in state["slots"] and "account_number" not in state["slots"]
    assert "utterance" not in state


def test_failed_credentials_are_cleared(service):
    state = converse(service, "balance", "10000001", "0000")
    assert "pin" not in state["slots"] and state["expecting"] == "account_number"


def test_audit_trail_records_tools_without_arguments(service):
    state = converse(service, "balance", "10000001", "1234")
    tools = [e["tool"] for e in state["events"]]
    assert tools == ["verify_caller", "get_account_balance"]
    assert all(set(e) == {"turn", "tool", "ok", "error"} for e in state["events"])


def test_offer_expires_if_caller_changes_subject(service):
    state = converse(service, "technician", "10000002", "4321")
    assert state["pending_action"] is not None
    state = service.take_turn(state["call_id"], "what's my balance")
    assert state["pending_action"] is None and "$42.50" in state["response"]
    # A later "yes" must not book the abandoned offer.
    state = service.take_turn(state["call_id"], "yes")
    assert "confirmation number" not in state["response"]


def test_warm_transfer_carries_context(service):
    state = converse(service, "balance", "10000001", "1234", "agent please")
    assert state["status"] == "escalated"
    assert state["handoff"]["queue"] == "general"
    assert state["handoff"]["reason"] == "caller_requested"


def test_ended_call_rejects_turns(service):
    from app.service import CallEnded

    state = converse(service, "goodbye")
    with pytest.raises(CallEnded):
        service.take_turn(state["call_id"], "hello?")
