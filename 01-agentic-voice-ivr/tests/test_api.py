import json

import structlog

from app.observability import configure_logging, redact


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"


def test_readiness_degrades_when_dependency_down(client, app, monkeypatch):
    monkeypatch.setattr(app.state.system, "ping", lambda: (_ for _ in ()).throw(OSError()))
    assert client.get("/health/ready").status_code == 503


def test_api_key_required(client):
    assert client.post("/v1/calls").status_code == 401
    assert client.post("/v1/calls", headers={"X-API-Key": "wrong"}).status_code == 401


def test_full_call_over_http(client, headers):
    start = client.post("/v1/calls", headers=headers, json={"channel": "simulator"})
    assert start.status_code == 201
    call_id = start.json()["call_id"]
    for text in ["what's my balance", "10000001", "1234"]:
        resp = client.post(f"/v1/calls/{call_id}/turns", headers=headers, json={"text": text})
        assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] and body["completed_tasks"] == ["check_balance"]
    assert "$89.99" in body["reply"]

    detail = client.get(f"/v1/calls/{call_id}", headers=headers).json()
    assert [e["tool"] for e in detail["events"]] == ["verify_caller", "get_account_balance"]
    assert "10000001" not in json.dumps(detail) and "1234" not in json.dumps(detail)


def test_unknown_and_ended_calls(client, headers):
    resp = client.post("/v1/calls/nope/turns", headers=headers, json={"text": "hi"})
    assert resp.status_code == 404 and resp.json()["error"] == "call_not_found"
    call_id = client.post("/v1/calls", headers=headers).json()["call_id"]
    client.post(f"/v1/calls/{call_id}/turns", headers=headers, json={"text": "bye"})
    resp = client.post(f"/v1/calls/{call_id}/turns", headers=headers, json={"text": "hi"})
    assert resp.status_code == 409


def test_input_length_limited(client, headers):
    call_id = client.post("/v1/calls", headers=headers).json()["call_id"]
    resp = client.post(f"/v1/calls/{call_id}/turns", headers=headers, json={"text": "x" * 501})
    assert resp.status_code == 422


def test_request_id_propagated_and_security_headers(client):
    resp = client.get("/health/live", headers={"X-Request-ID": "abc12345-req"})
    assert resp.headers["X-Request-ID"] == "abc12345-req"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    # Malformed IDs are replaced, not reflected (log-injection defense).
    bad = client.get("/health/live", headers={"X-Request-ID": "x\nforged"})
    assert bad.headers["X-Request-ID"] != "x\nforged"


def test_metrics_exposed(client, headers):
    call_id = client.post("/v1/calls", headers=headers).json()["call_id"]
    client.post(f"/v1/calls/{call_id}/turns", headers=headers, json={"text": "is there an outage"})
    text = client.get("/metrics").text
    assert "ivr_turns_total" in text and "ivr_turn_latency_seconds_bucket" in text


def test_tools_catalog(client, headers):
    names = {t["name"] for t in client.get("/v1/tools", headers=headers).json()}
    assert {"verify_caller", "book_technician_visit", "transfer_to_agent"} <= names


def test_openapi_documents_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/calls/{call_id}/turns" in paths and "/voice/twilio/gather" in paths


def test_log_redaction(capsys):
    configure_logging("INFO")
    structlog.get_logger().info(
        "turn for 10000001",
        pin="1234",
        utterance="my pin is 1234",
        nested={"account_number": "10000001", "note": "call 5551234567"},
    )
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "turn for [NUM]"
    assert line["pin"] == line["utterance"] == "[REDACTED]"
    assert line["nested"] == {"account_number": "[REDACTED]", "note": "call [NUM]"}
    assert "T" in line["timestamp"] and "[NUM]" not in line["timestamp"]


def test_redact_handles_lists():
    assert redact(["pin 1234", 5]) == ["pin [NUM]", 5]
