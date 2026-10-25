import pytest

from app.tools import ToolContext, build_registry


@pytest.fixture
def registry(system):
    return build_registry(system)


ANON = ToolContext(call_id="t")
AVA = ToolContext(call_id="t", authenticated=True, customer_id="C00001")


def test_verify_caller_success_and_uniform_failure(registry):
    ok = registry.call("verify_caller", {"account_number": "10000001", "pin": "1234"}, ANON)
    assert ok.ok and ok.data["verified"] and ok.data["customer_id"] == "C00001"
    wrong_pin = registry.call("verify_caller", {"account_number": "10000001", "pin": "0000"}, ANON)
    no_account = registry.call("verify_caller", {"account_number": "19999999", "pin": "0000"}, ANON)
    # Same response whether the account exists or not: no enumeration oracle.
    assert wrong_pin.data == no_account.data == {"verified": False, "locked": False}


def test_invalid_arguments_rejected(registry):
    result = registry.call("verify_caller", {"account_number": "123", "pin": "1234"}, ANON)
    assert not result.ok and result.error == "invalid_arguments"


def test_auth_required(registry):
    result = registry.call("get_account_balance", {"customer_id": "C00001"}, ANON)
    assert result.error == "authentication_required"


def test_customer_binding_blocks_cross_account_access(registry):
    result = registry.call("get_account_balance", {"customer_id": "C00002"}, AVA)
    assert result.error == "customer_mismatch"


def test_side_effect_requires_confirmation(registry):
    slots = registry.call("find_technician_slots", {"customer_id": "C00001"}, AVA)
    slot_id = slots.data["slots"][0]["slot_id"]
    args = {"customer_id": "C00001", "slot_id": slot_id}
    assert registry.call("book_technician_visit", args, AVA).error == "confirmation_required"
    confirmed = AVA.model_copy(update={"confirmed": True})
    booked = registry.call("book_technician_visit", args, confirmed)
    assert booked.ok and booked.data["confirmation"].startswith("NW")
    # A retry within the same call is idempotent: same appointment, not a second booking.
    again = registry.call("book_technician_visit", args, confirmed)
    assert again.ok and again.data["confirmation"] == booked.data["confirmation"]
    # Another call cannot double-book the window.
    other_call = confirmed.model_copy(update={"call_id": "other"})
    assert registry.call("book_technician_visit", args, other_call).error == "slot_unavailable"


def test_slots_skip_weekends_and_honor_preferred_day(registry):
    slots = registry.call("find_technician_slots", {"customer_id": "C00001"}, AVA).data["slots"]
    assert len(slots) == 3 and slots[0]["label"].startswith("Thursday, October 22")
    friday = registry.call(
        "find_technician_slots", {"customer_id": "C00001", "preferred_day": "friday"}, AVA
    )
    assert all(s["label"].startswith("Friday") for s in friday.data["slots"])
    saturday = registry.call(
        "find_technician_slots", {"customer_id": "C00001", "preferred_day": "saturday"}, AVA
    )
    assert saturday.data["slots"] == []


def test_upstream_error_is_contained(registry):
    ctx = ToolContext(call_id="t", authenticated=True, customer_id="C00003")
    result = registry.call("get_account_balance", {"customer_id": "C00003"}, ctx)
    assert not result.ok and result.error == "upstream_unavailable"


def test_unknown_tool(registry):
    assert registry.call("delete_account", {}, AVA).error == "unknown_tool"


def test_schemas_are_llm_ready(registry):
    schemas = {s["name"]: s for s in registry.schemas()}
    assert schemas["book_technician_visit"]["side_effect"] is True
    assert schemas["verify_caller"]["input_schema"]["properties"]["pin"]["pattern"] == r"^\d{4}$"
