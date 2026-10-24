import json

import structlog

from sipdoc.cli import main as cli_main
from sipdoc.observability import configure_logging, redact_text
from tests.conftest import capture


def _upload(client, headers, name="nat_one_way_audio", filename=None):
    with capture(name).open("rb") as fh:
        return client.post(
            "/v1/analyses",
            headers=headers,
            files={"capture": (filename or f"{name}.pcap", fh, "application/octet-stream")},
        )


def test_health_and_metrics(client, headers):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["narrator"] == "template"
    _upload(client, headers)
    assert "sipdoc_findings_total" in client.get("/metrics").text


def test_api_key_required(client):
    assert client.get("/v1/signatures").status_code == 401


def test_upload_analyze_fetch_and_ladder(client, headers):
    resp = _upload(client, headers)
    assert resp.status_code == 201
    report = resp.json()
    diag = report["calls"][0]
    assert diag["root_cause"] == "media_to_private_address"
    aid, cid = report["analysis_id"], diag["call_id"]
    assert client.get(f"/v1/analyses/{aid}", headers=headers).json()["analysis_id"] == aid
    ladder = client.get(f"/v1/analyses/{aid}/calls/{cid}/ladder", headers=headers)
    assert ladder.text.startswith("sequenceDiagram")
    text = client.get(f"/v1/analyses/{aid}/calls/{cid}/ladder?fmt=text", headers=headers)
    assert "INVITE (SDP)" in text.text
    assert client.get(f"/v1/analyses/{aid}/calls/nope/ladder", headers=headers).status_code == 404
    assert client.get("/v1/analyses/missing", headers=headers).status_code == 404


def test_rejects_wrong_type_bad_content_and_oversize(client, headers, tmp_path):
    assert _upload(client, headers, filename="notes.txt").status_code == 415
    resp = client.post(
        "/v1/analyses",
        headers=headers,
        files={"capture": ("x.pcap", b"not a pcap", "application/octet-stream")},
    )
    assert resp.status_code == 422
    from fastapi.testclient import TestClient

    from sipdoc.api.app import create_app
    from sipdoc.config import Settings

    small = TestClient(
        create_app(Settings(api_key="test-key", max_upload_mb=1, log_level="WARNING"))
    )
    big = b"\x00" * (1024 * 1024 + 10)
    resp = small.post(
        "/v1/analyses",
        headers=headers,
        files={"capture": ("big.pcap", big, "application/octet-stream")},
    )
    assert resp.status_code == 413


def test_signature_catalog(client, headers):
    names = {s["name"] for s in client.get("/v1/signatures", headers=headers).json()}
    assert {"nat_private_sdp", "one_way_audio", "codec_mismatch"} <= names


def test_store_evicts_oldest():
    from fastapi.testclient import TestClient

    from sipdoc.api.app import create_app
    from sipdoc.config import Settings

    c = TestClient(create_app(Settings(api_key="k", max_stored_analyses=1, log_level="WARNING")))
    h = {"X-API-Key": "k"}
    first = _upload(c, h).json()["analysis_id"]
    _upload(c, h, "busy_486")
    assert c.get(f"/v1/analyses/{first}", headers=h).status_code == 404


def test_cli_text_json_and_exit_codes(capsys):
    assert cli_main(["analyze", str(capture("healthy_call"))]) == 0
    assert cli_main(["analyze", str(capture("codec_mismatch"))]) == 1
    out = capsys.readouterr().out
    assert "codec_mismatch" in out or "No common codec" in out
    assert cli_main(["analyze", str(capture("busy_486")), "--format", "json"]) == 1
    payload = capsys.readouterr().out
    assert json.loads(payload)["calls"][0]["root_cause"] == "call_rejected"
    assert cli_main(["analyze", str(capture("busy_486")), "--format", "mermaid"]) == 1
    assert cli_main(["analyze", "missing.pcap"]) == 2


def test_log_redaction(capsys):
    assert (
        redact_text("call from sip:+15550101234@host to 15550109876")
        == "call from sip:[USER]@host to [NUM]"
    )
    configure_logging("INFO")
    structlog.get_logger().info("x", caller="sip:alice@example.com")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["caller"] == "sip:[USER]@example.com"
