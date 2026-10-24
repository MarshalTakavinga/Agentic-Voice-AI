import json

import pytest

from sipdoc.analyzers.rules import SIGNATURES, is_private
from sipdoc.engine import analyze_capture, ladder_mermaid
from sipdoc.evals import CAPTURES, evaluate
from tests.conftest import capture

LABELS = json.loads((CAPTURES / "labels.json").read_text())


@pytest.mark.parametrize("name", sorted(LABELS))
def test_each_labeled_capture(name):
    report, _ = analyze_capture(capture(name))
    diag = report.calls[0]
    assert sorted({f.signature for f in diag.findings}) == LABELS[name]["signatures"]
    assert diag.root_cause == LABELS[name]["root_cause"]


def test_every_finding_carries_evidence_and_known_signature():
    for name in LABELS:
        report, _ = analyze_capture(capture(name))
        for f in report.calls[0].findings:
            assert f.signature in SIGNATURES and f.evidence and f.id.startswith("F")


def test_eval_summary_is_perfect_on_bundled_set():
    r = evaluate()
    assert r["exact_matches"] == r["captures"] == len(LABELS)
    assert r["false_positives"] == r["false_negatives"] == 0


@pytest.mark.parametrize(
    "ip,expected",
    [
        ("192.168.1.50", True),
        ("10.0.0.1", True),
        ("172.20.1.1", True),
        ("100.64.3.3", True),
        ("192.0.2.10", False),  # documentation range: Python calls it private; NAT-wise it is not
        ("203.0.113.10", False),
        ("8.8.8.8", False),
        ("fd00::1", True),
        ("2001:db8::1", False),
        ("not-an-ip", False),
        (None, False),
    ],
)
def test_is_private_means_nat_range(ip, expected):
    assert is_private(ip) is expected


def test_phone_numbers_masked_in_report():
    report, _ = analyze_capture(capture("healthy_call"))
    diag = report.calls[0]
    assert diag.caller == "***1234" and diag.callee == "***9876"
    assert "+1555010" not in report.model_dump_json()


def test_rtp_payload_not_retained():
    _, parsed = analyze_capture(capture("healthy_call"))
    assert all(not hasattr(s, "payload") for s in parsed.streams)


def test_next_steps_are_sentences_not_characters():
    report, _ = analyze_capture(capture("nat_one_way_audio"))
    assert all(len(step) > 40 for step in report.calls[0].next_steps)


def test_mermaid_ladder():
    _, parsed = analyze_capture(capture("codec_mismatch"))
    text = ladder_mermaid(parsed.calls()[0])
    assert text.startswith("sequenceDiagram") and "488 Not Acceptable Here" in text
    assert "#" not in text  # '#' breaks Mermaid entity parsing


def test_timeout_reports_retransmissions():
    report, _ = analyze_capture(capture("setup_timeout"))
    timeout = next(f for f in report.calls[0].findings if f.signature == "setup_timeout")
    assert "7 times" in timeout.detail and "no provisional response" in timeout.detail
