import httpx
import pytest

from app.nlu.base import extract_entities, normalize
from app.nlu.bedrock import BedrockNLU
from app.nlu.llm import OpenAICompatibleNLU
from app.nlu.rules import RulesNLU

nlu = RulesNLU()


@pytest.mark.parametrize(
    "text,intent",
    [
        ("what's my balance", "check_balance"),
        ("how much do I owe", "check_balance"),
        ("my internet is down", "check_outage"),
        ("no internet since this morning", "check_outage"),  # not a "deny"
        ("I need a technician", "schedule_technician"),
        ("let me speak to a representative", "agent"),
        ("I want a human about my bill", "agent"),  # explicit human request wins
        ("yes", "affirm"),
        ("nope", "deny"),
        ("no that's all", "goodbye"),
        ("what can you do", "help"),
        ("purple monkey dishwasher", "no_match"),
        ("", "no_match"),
    ],
)
def test_intents(text, intent):
    assert nlu.parse(text).intent == intent


@pytest.mark.parametrize(
    "digit,intent",
    [("1", "check_balance"), ("2", "check_outage"), ("3", "schedule_technician"), ("0", "agent")],
)
def test_dtmf_menu(digit, intent):
    result = nlu.parse(digit)
    assert result.intent == intent and result.source == "dtmf"


def test_dtmf_digit_not_treated_as_menu_while_collecting_slot():
    assert nlu.parse("1", expecting="pin").intent == "no_match"


def test_normalize_spoken_and_grouped_digits():
    assert normalize("One two three FOUR") == "1234"
    assert normalize("1 0 0-0 0 0 0 1") == "10000001"
    assert normalize("someone") == "someone"  # word boundaries respected


def test_entities_depend_on_expected_slot():
    assert extract_entities("1234", expecting="pin") == {"pin": "1234"}
    assert extract_entities("1234", expecting=None) == {}
    assert extract_entities("account 10000001 pin 4321", None) == {
        "account_number": "10000001",
        "pin": "4321",
    }
    assert extract_entities("zip 60614", None) == {"zip": "60614"}
    assert extract_entities("how about friday", None) == {"preferred_day": "friday"}
    assert extract_entities("whatever is soonest", None) == {"preferred_day": "earliest"}


def test_provide_info_when_only_entities():
    result = nlu.parse("10000001", expecting="account_number")
    assert result.intent == "provide_info" and result.entities["account_number"] == "10000001"


# ------------------------------------------------------------------ LLM providers (mocked)
def _llm(handler) -> OpenAICompatibleNLU:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleNLU("http://llm.test/v1", "m", client=client)


def _chat(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_llm_intent_used_and_entities_stay_deterministic():
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode()
        return _chat('{"intent": "check_balance", "confidence": 0.93}')

    result = _llm(handler).parse("uh what's the damage on account 10000001")
    assert result.intent == "check_balance" and result.source == "openai_compatible"
    assert result.entities == {"account_number": "10000001"}
    assert '"temperature": 0' in seen["body"].replace(":0", ": 0")


def test_llm_failure_falls_back_to_rules():
    result = _llm(lambda r: httpx.Response(503)).parse("my internet is down")
    assert result.intent == "check_outage" and result.source == "rules_fallback"


def test_llm_invalid_intent_falls_back():
    result = _llm(lambda r: _chat('{"intent": "transfer_funds", "confidence": 1}')).parse("hi")
    assert result.source == "rules_fallback"


def test_llm_low_confidence_uses_rules():
    result = _llm(lambda r: _chat('{"intent": "check_outage", "confidence": 0.2}')).parse("balance")
    assert result.intent == "check_balance" and result.source == "rules_low_confidence"


def test_llm_never_overrides_human_request():
    def handler(_r):  # pragma: no cover - must not be called
        raise AssertionError("LLM should not be consulted")

    assert _llm(handler).parse("get me a human").intent == "agent"


class _StubBedrock:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def converse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_bedrock_converse_tool_use_parsed():
    stub = _StubBedrock(
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "record_intent",
                                "input": {"intent": "schedule_technician", "confidence": 0.9},
                            }
                        }
                    ]
                }
            }
        }
    )
    result = BedrockNLU("model-x", "us-east-1", client=stub).parse("can someone come fix it")
    assert result.intent == "schedule_technician" and result.source == "bedrock"
    assert stub.kwargs["toolConfig"]["toolChoice"] == {"tool": {"name": "record_intent"}}


def test_bedrock_without_tool_use_falls_back():
    stub = _StubBedrock({"output": {"message": {"content": [{"text": "hmm"}]}}})
    assert BedrockNLU("m", "us-east-1", client=stub).parse("balance").source == "rules_fallback"


# Found by 03-voice-agent-evals' ASR-noise profiles (oh_for_zero, fillers, homophones).
@pytest.mark.parametrize(
    ("utterance", "expecting", "normalized"),
    [
        ("one oh oh oh oh oh oh one", None, "10000001"),
        ("oh oh oh oh", "pin", "0000"),
        ("um yes hmm please", None, "yes please"),
        ("uh one uh two three four", "pin", "1234"),
        ("won to three for", "pin", "1234"),
        ("won zero zero zero zero zero zero to", "account_number", "10000002"),
        ("six zero six won for", "zip", "60614"),
        ("seven three three zero won", "zip", "73301"),
    ],
)
def test_normalize_recognizer_variants(utterance, expecting, normalized):
    assert normalize(utterance, expecting) == normalized


@pytest.mark.parametrize(
    ("utterance", "expecting", "normalized"),
    [
        ("is there an outage for 60614", None, "is there an outage for 60614"),
        ("outage for seven three three zero one", "zip", "outage for 73301"),
        ("i want to check my balance", None, "i want to check my balance"),
        ("oh, i want my balance", None, "oh, i want my balance"),
        ("i need to talk to someone", "pin", "i need to talk to someone"),
    ],
)
def test_ambiguous_words_stay_words_outside_identifiers(utterance, expecting, normalized):
    assert normalize(utterance, expecting) == normalized


def test_homophone_pin_in_one_utterance_with_account():
    text = normalize(
        "my account number is won zero zero zero zero zero zero to and my pin is for three to won",
        "account_number",
    )
    assert extract_entities(text, "account_number") == {"account_number": "10000002", "pin": "4321"}
