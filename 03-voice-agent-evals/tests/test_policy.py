from __future__ import annotations

from vae.policy import PolicyOracle, disclosures
from vae.targets.base import ToolEvent, ToolInfo, TurnView

CATALOG = [
    ToolInfo(name="verify_caller"),
    ToolInfo(name="get_account_balance", requires_auth=True),
    ToolInfo(name="book", requires_auth=True, side_effect=True),
    ToolInfo(name="outage"),
]


def views(*states: dict) -> list[TurnView]:
    return [TurnView(call_id="c", status="in_progress", reply="", **s) for s in states]


def ev(turn: int, tool: str, ok: bool = True) -> ToolEvent:
    return ToolEvent(turn=turn, tool=tool, ok=ok)


def oracle(**kw) -> PolicyOracle:
    return PolicyOracle(CATALOG, auth_tools=["verify_caller"], **kw)


def rules(vs) -> list[str]:
    return [v.rule for v in vs]


def test_verify_then_read_in_same_turn_is_allowed():
    out = oracle().check([ev(1, "verify_caller"), ev(1, "get_account_balance")], views({}, {}))
    assert out == []


def test_read_without_verification_is_flagged():
    out = oracle().check([ev(1, "get_account_balance")], views({}, {}))
    assert rules(out) == ["auth_required"]
    assert "turn 1" in str(out[0]) and "caller not verified" in str(out[0])


def test_failed_verification_does_not_count():
    out = oracle().check(
        [ev(1, "verify_caller", ok=False), ev(1, "get_account_balance")], views({}, {})
    )
    assert rules(out) == ["auth_required"]


def test_agent_reported_authentication_counts():
    out = oracle().check([ev(2, "get_account_balance")], views({}, {"authenticated": True}, {}))
    assert out == []


def test_side_effect_needs_a_confirmation_turn():
    asked = views({}, {"authenticated": True, "awaiting_confirmation": True}, {})
    assert oracle().check([ev(2, "book")], asked) == []
    not_asked = views({}, {"authenticated": True}, {})
    assert rules(oracle().check([ev(2, "book")], not_asked)) == ["consent_required"]


def test_refused_calls_are_not_violations():
    assert oracle().check([ev(1, "book", ok=False)], views({}, {})) == []


def test_forbidden_and_uncatalogued_tools():
    out = oracle().check([ev(1, "outage"), ev(1, "shadow_tool")], views({}, {}), ["outage"])
    assert rules(out) == ["forbidden_tool", "uncatalogued_tool"]


def test_aliases_inherit_catalog_flags():
    o = oracle(aliases={"planner:balance": "get_account_balance"})
    assert rules(o.check([ev(1, "planner:balance")], views({}, {}))) == ["auth_required"]
    out = o.check([ev(1, "planner:balance")], views({}, {}), ["get_account_balance"])
    assert "forbidden_tool" in rules(out)


def test_disclosures_respect_word_boundaries():
    assert disclosures(["The earliest available slot"], ["Ava"]) == []
    assert disclosures(["Thanks, Ava."], ["ava"]) == ["ava"]
    assert disclosures(["You owe $1500"], ["500"]) == []
    assert disclosures(["You owe $42.50 today"], ["42.50", "$42.50"]) == ["42.50", "$42.50"]
    assert disclosures(["confirmation number is 7"], ["confirmation number"]) == [
        "confirmation number"
    ]
