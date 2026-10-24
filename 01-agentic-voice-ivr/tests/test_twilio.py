import pytest
from fastapi.testclient import TestClient

from app.api.twilio import build_twiml, compute_signature
from app.config import Settings
from app.main import create_app

TOKEN = "twilio-test-token"


def test_incoming_call_returns_gather(client):
    resp = client.post("/voice/twilio/incoming", data={"CallSid": "CA100", "From": "+15550100"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/xml")
    xml = resp.text
    assert '<Gather input="speech dtmf" action="/voice/twilio/gather"' in xml
    assert "Northwind Fiber" in xml and "<Redirect" in xml


def test_gather_speech_and_dtmf(client):
    client.post("/voice/twilio/incoming", data={"CallSid": "CA200"})
    r1 = client.post("/voice/twilio/gather", data={"CallSid": "CA200", "Digits": "1"})
    assert "account number" in r1.text
    client.post("/voice/twilio/gather", data={"CallSid": "CA200", "SpeechResult": "10000001"})
    r3 = client.post("/voice/twilio/gather", data={"CallSid": "CA200", "Digits": "1234"})
    assert "$89.99" in r3.text


def test_escalation_enqueues_and_goodbye_hangs_up(client):
    client.post("/voice/twilio/incoming", data={"CallSid": "CA300"})
    r = client.post(
        "/voice/twilio/gather", data={"CallSid": "CA300", "SpeechResult": "representative"}
    )
    assert "<Enqueue>general</Enqueue>" in r.text and "<Gather" not in r.text
    client.post("/voice/twilio/incoming", data={"CallSid": "CA301"})
    r = client.post("/voice/twilio/gather", data={"CallSid": "CA301", "SpeechResult": "goodbye"})
    assert "<Hangup/>" in r.text


def test_unknown_call_sid_ends_gracefully(client):
    r = client.post("/voice/twilio/gather", data={"CallSid": "CA-unknown", "SpeechResult": "hi"})
    assert r.status_code == 200 and "<Hangup/>" in r.text


def test_twiml_escapes_content():
    xml = build_twiml({"status": "completed", "response": 'A & B <script>"'}, "Polly.Joanna")
    assert "A &amp; B &lt;script&gt;&quot;" in xml


def test_signature_matches_twilio_reference_vector():
    # Reference vector; cross-checked against twilio.request_validator.RequestValidator.
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    params = {
        "CallSid": "CA1234567890ABCDE",
        "Caller": "+12349013030",
        "Digits": "1234",
        "From": "+12349013030",
        "To": "+18005551212",
    }
    assert compute_signature(url, params, "12345") == "0/KCTR6DLpKmkAf8muzZqo1nDgQ="


@pytest.fixture
def signed_client(system):
    settings = Settings(
        api_key="k",
        log_level="WARNING",
        twilio_validate_signature=True,
        twilio_auth_token=TOKEN,
        public_base_url="https://ivr.example.com",
    )
    return TestClient(create_app(settings, system))


def test_signature_enforced(signed_client):
    params = {"CallSid": "CA400", "From": "+15550100"}
    good = compute_signature("https://ivr.example.com/voice/twilio/incoming", params, TOKEN)
    assert (
        signed_client.post(
            "/voice/twilio/incoming", data=params, headers={"X-Twilio-Signature": good}
        ).status_code
        == 200
    )
    assert (
        signed_client.post(
            "/voice/twilio/incoming", data=params, headers={"X-Twilio-Signature": "forged"}
        ).status_code
        == 403
    )
    assert signed_client.post("/voice/twilio/incoming", data=params).status_code == 403
