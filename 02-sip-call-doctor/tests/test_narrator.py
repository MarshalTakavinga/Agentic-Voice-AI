import json

import httpx

from sipdoc.engine import analyze_capture
from sipdoc.models import Evidence, Finding
from sipdoc.narrator import OpenAICompatibleNarrator, TemplateNarrator, grounding_errors
from tests.conftest import capture

FINDINGS = [
    Finding(
        id="F1",
        signature="rtp_packet_loss",
        severity="major",
        title="RTP packet loss",
        detail="7.66% loss (19 of 248 packets)",
        evidence=[Evidence(ref="rtp:0x1", fact="loss 7.66% (19/248)")],
    )
]


def test_grounded_text_passes():
    assert (
        grounding_errors("Callers hear choppy audio from 7.66% packet loss [F1].", FINDINGS) == []
    )


def test_ungrounded_numbers_and_citations_rejected():
    assert "no citations" in grounding_errors("Loss is bad.", FINDINGS)
    assert any("unknown" in e for e in grounding_errors("Loss [F9].", FINDINGS))
    assert any("ungrounded" in e for e in grounding_errors("MOS dropped to 2.1 [F1].", FINDINGS))


def _narrator(content: str | None = None, status: int = 200) -> OpenAICompatibleNarrator:
    def handler(_request):
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return OpenAICompatibleNarrator(
        "http://llm.test/v1", "m", client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_llm_narration_used_when_grounded():
    text = "The far end drops 7.66% of packets toward the caller [F1]."
    out = _narrator(json.dumps({"summary": text})).narrate(FINDINGS, "")
    assert out == text


def test_llm_hallucination_replaced_by_template():
    bad = json.dumps({"summary": "Latency is 300 ms, causing echo [F1]."})
    out = _narrator(bad).narrate(FINDINGS, "")
    assert out == TemplateNarrator().narrate(FINDINGS, "")


def test_llm_outage_falls_back():
    out = _narrator(status=503).narrate(FINDINGS, "")
    assert out.startswith("Most likely cause")


def test_template_output_is_always_grounded():
    for name in ("nat_one_way_audio", "poor_quality", "setup_timeout", "auth_failure"):
        report, _ = analyze_capture(capture(name))
        d = report.calls[0]
        assert grounding_errors(d.summary, d.findings) == [], name
