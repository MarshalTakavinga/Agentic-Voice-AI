from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.conftest import IVR_SUITE, MINI
from vae.scenario import Scenario, Suite, Turn, load_suite


def test_turn_needs_exactly_one_input():
    with pytest.raises(ValidationError, match="exactly one"):
        Turn(say="hi", dtmf="1")
    with pytest.raises(ValidationError, match="exactly one"):
        Turn()
    assert Turn(silence=True).text == ""
    assert Turn(dtmf="12#").text == "12#"
    assert not Turn(dtmf="1").is_speech


def test_dtmf_is_validated():
    with pytest.raises(ValidationError):
        Turn(dtmf="12a")


def test_expect_shorthand_and_listify():
    t = Turn(say="x", expect="PIN")
    assert t.expect.contains == ["PIN"]
    t = Turn(say="x", expect={"not_contains": "secret"})
    assert t.expect.not_contains == ["secret"]


@pytest.mark.parametrize(("value", "hint"), [(True, "boolean"), (1234, "number")])
def test_yaml_scalar_traps_get_a_clear_error(value, hint):
    with pytest.raises(ValidationError, match=hint):
        Turn(say=value)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Turn(say="x", sya="typo")


def test_duplicate_ids_rejected():
    s = Scenario(id="a", description="d", turns=[Turn(say="x")])
    with pytest.raises(ValidationError, match="duplicate"):
        Suite(name="s", scenarios=[s, s])


def test_expects_escalation():
    s = Scenario(id="a", description="d", turns=[Turn(say="x")])
    assert s.expects_escalation is None
    s = Scenario(id="a", description="d", turns=[Turn(say="x")], expect={"status": "in_progress"})
    assert s.expects_escalation is False
    s = Scenario(
        id="a", description="d", turns=[Turn(say="x")], expect={"handoff": {"reason": "r"}}
    )
    assert s.expects_escalation is True


def test_load_suite_merges_defaults_and_tags(mini):
    by_id = {s.id: s for s in mini.scenarios}
    assert by_id["balance"].tags == ["mini", "billing"]
    assert by_id["human"].tags == ["mini"]
    assert by_id["never_book_unverified"].category == "injection"
    assert mini.target.api_key_env == "VAE_TEST_KEY"
    assert len(mini.fingerprint) == 12


def test_fingerprint_changes_with_content(tmp_path):
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "suite.yaml").write_text("name: t\n")
    f = tmp_path / "scenarios" / "a.yaml"
    f.write_text("scenarios:\n  - {id: a, description: d, turns: [{say: hi}]}\n")
    first = load_suite(tmp_path).fingerprint
    f.write_text("scenarios:\n  - {id: a, description: d, turns: [{say: hello}]}\n")
    assert load_suite(tmp_path / "suite.yaml").fingerprint != first


def test_bundled_ivr_suite_loads():
    suite = load_suite(IVR_SUITE)
    cats = {s.category for s in suite.scenarios}
    assert cats == {"clean", "injection"}
    assert len([s for s in suite.scenarios if s.category == "clean"]) == 14
    assert len([s for s in suite.scenarios if s.category == "injection"]) == 8
    assert MINI.exists()
