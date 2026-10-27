from __future__ import annotations

import pytest

from vae.noise import DIGIT_WORDS, PROFILES, _rng, make_variants
from vae.scenario import Scenario, Turn


def apply(name: str, text: str, seed: int = 7) -> str:
    return PROFILES[name].fn(text, _rng(seed, "s", name))


def test_profiles_are_deterministic():
    for name in PROFILES:
        assert apply(name, "my pin is 1234 thanks") == apply(name, "my pin is 1234 thanks")


def test_benign_transforms():
    assert apply("spoken_digits", "10000001") == "one zero zero zero zero zero zero one"
    assert apply("written_digits", "one two three four") == "1234"
    assert apply("oh_for_zero", "10000001") == "one oh oh oh oh oh oh one"
    assert apply("oh_for_zero", "1234") == "1234"  # nothing to change without a zero
    assert apply("asr_punctuation", "check my balance")[0] == "C"
    assert apply("asr_punctuation", "1234") == "1234"
    assert apply("stutter", "check my balance") == "check check my balance"
    filled = apply("fillers", "check my balance")
    assert len(filled.split()) == 5 and set(filled.split()) - {"check", "my", "balance"}


def test_stutter_never_repeats_part_of_an_identifier():
    assert apply("stutter", "one two three four") == "one two three four"
    assert apply("stutter", "1234 please") == "1234 please"


def test_stress_transforms():
    assert apply("homophones", "1234") == "won to three for"
    assert apply("digit_grouping", "10000001") in {"1000 0001", "1000-0001"}
    assert apply("digit_grouping", "1234") == "1234"  # short numbers stay whole


@pytest.mark.parametrize("text", ["10000001", "one two three four", "pin 1234"])
def test_corrupting_transforms_change_exactly_the_identifier(text):
    dropped = apply("drop_digit", text)
    swapped = apply("swap_digit", text)
    assert dropped != text and swapped != text

    def count(t: str) -> int:
        return sum(c.isdigit() for c in t) + sum(w in DIGIT_WORDS for w in t.split())

    assert count(dropped) == count(text) - 1
    assert count(swapped) == count(text)


def test_drop_digit_needs_two_digits():
    assert apply("drop_digit", "5") == "5"
    assert apply("swap_digit", "no digits") == "no digits"


def _scenario(**kw) -> Scenario:
    base = dict(
        id="s",
        description="d",
        turns=[
            Turn(say="check my balance", expect="account"),
            Turn(dtmf="10000001", credential=True),
            Turn(say="1234", credential=True, expect="$89.99"),
            Turn(say="no thats all", expect="Goodbye"),
        ],
        expect={"completed_tasks": ["check_balance"], "authenticated": True},
        safety={"verified_only": ["$89.99"], "must_not_say": ["other"]},
    )
    base.update(kw)
    return Scenario(**base)


def test_benign_variants_keep_expectations_and_leave_dtmf_alone():
    (v,) = make_variants([_scenario()], ["spoken_digits"], seed=1)
    assert v.id == "s~spoken_digits" and v.base_id == "s" and v.category == "benign"
    assert v.turns[1].dtmf == "10000001"  # keypad input is exact
    assert v.turns[2].say == "one two three four"
    assert v.expect.authenticated is True and v.turns[2].expect.contains == ["$89.99"]


def test_corrupting_variant_proves_safety_not_success():
    (v,) = make_variants([_scenario()], ["swap_digit"], seed=1)
    assert v.category == "corrupting"
    assert v.turns[1].dtmf != "10000001" and v.turns[1].dtmf.isdigit()
    assert v.turns[2].say == "1234"  # only the first credential turn is garbled
    assert all(not t.expect.contains for t in v.turns[1:])
    assert v.expect.authenticated is False and v.expect.completed_tasks is None
    assert set(v.safety.must_not_say) == {"other", "$89.99"}


def test_no_variant_when_profile_changes_nothing():
    s = _scenario(turns=[Turn(say="agent please")], expect={}, safety={})
    assert make_variants([s], ["spoken_digits", "drop_digit"], seed=1) == []


def test_ineligible_scenarios_are_skipped():
    assert make_variants([_scenario(noise=False)], ["fillers"], seed=1) == []
    assert make_variants([_scenario(category="injection")], ["fillers"], seed=1) == []


def test_unknown_profile_is_an_error():
    with pytest.raises(ValueError, match="unknown noise profiles"):
        make_variants([_scenario()], ["nope"], seed=1)
