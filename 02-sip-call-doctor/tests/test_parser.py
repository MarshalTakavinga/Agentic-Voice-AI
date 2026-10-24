import pytest

from sipdoc.parser import (
    CaptureError,
    _StreamAcc,
    estimate_mos,
    parse_capture,
    parse_sdp,
    parse_sip,
)
from tests.conftest import capture

INVITE = (
    b"INVITE sip:+15550109876@192.0.2.10 SIP/2.0\r\n"
    b"v: SIP/2.0/UDP 198.51.100.20;branch=z9hG4bK1\r\n"
    b"f: <sip:+15550101234@198.51.100.20>;tag=abc\r\n"
    b"t: <sip:+15550109876@192.0.2.10>\r\n"
    b"i: compact-1@lab\r\n"
    b"CSeq: 1 INVITE\r\n"
    b"c: application/sdp\r\n\r\n"
    b"v=0\r\nc=IN IP4 10.1.2.3\r\nm=audio 4000 RTP/AVP 0 101\r\n"
    b"a=rtpmap:101 telephone-event/8000\r\na=sendonly\r\n"
)


def test_parse_sip_with_compact_headers_and_sdp():
    m = parse_sip(INVITE, 1, 0.0, ("198.51.100.20", 5060), ("192.0.2.10", 5060))
    assert m.method == "INVITE" and m.call_id == "compact-1@lab" and m.cseq_method == "INVITE"
    assert m.from_user == "+15550101234" and m.from_tag == "abc" and m.to_tag is None
    assert m.sdp.connection_ip == "10.1.2.3"
    audio = m.sdp.audio
    assert audio.port == 4000 and audio.payload_types == [0, 101]
    assert audio.rtpmap[101] == "telephone-event/8000" and audio.direction == "sendonly"


def test_parse_response_line():
    resp = b"SIP/2.0 486 Busy Here\r\nCall-ID: x@y\r\nCSeq: 7 INVITE\r\n\r\n"
    m = parse_sip(resp, 2, 0.0, ("a", 1), ("b", 2))
    assert not m.is_request and m.status_code == 486 and m.reason == "Busy Here"
    assert m.cseq_num == 7


def test_non_sip_and_incomplete_messages_ignored():
    assert parse_sip(b"\x80\x00garbage", 1, 0, ("a", 1), ("b", 2)) is None
    assert parse_sip(b"OPTIONS sip:x SIP/2.0\r\nVia: x\r\n\r\n", 1, 0, ("a", 1), ("b", 2)) is None


def test_media_level_connection_line():
    sdp = parse_sdp("v=0\r\nm=audio 5000 RTP/AVP 8\r\nc=IN IP4 203.0.113.7\r\n")
    assert sdp.connection_ip == "203.0.113.7" and sdp.audio.payload_types == [8]


def test_sequence_wraparound_and_loss():
    acc = _StreamAcc(key=("0x1", "a", 1, "b", 2), pt=0)
    seqs = [65533, 65534, 65535, 0, 2, 3]  # seq 1 lost across the wrap
    for i, seq in enumerate(seqs):
        acc.add(seq, i * 160 if seq != 2 else 5 * 160, 1.0 + i * 0.02)
    s = acc.finish()
    assert s.expected == 7 and s.lost == 1 and s.packets == 6


def test_jitter_zero_for_perfect_pacing_and_positive_with_noise():
    perfect = _StreamAcc(key=("0x1", "a", 1, "b", 2), pt=0)
    noisy = _StreamAcc(key=("0x2", "a", 1, "b", 2), pt=0)
    for i in range(100):
        perfect.add(i, i * 160, i * 0.02)
        noisy.add(i, i * 160, i * 0.02 + (0.03 if i % 2 else 0.0))
    assert perfect.finish().jitter_ms == 0.0
    assert noisy.finish().jitter_ms > 20  # alternating 30 ms offsets converge near 30 ms


def test_mos_estimate_monotonic():
    assert estimate_mos(0, 0) > estimate_mos(40, 0) > estimate_mos(40, 5)
    assert 4.3 <= estimate_mos(0, 0) <= 4.5


def test_capture_parsing_counts_and_correlation():
    parsed = parse_capture(capture("healthy_call"))
    calls = parsed.calls()
    assert len(calls) == 1 and len(parsed.messages) == 7
    assert parsed.rtp_packets == 500 and len(calls[0].streams) == 2


def test_rejects_non_pcap(tmp_path):
    bad = tmp_path / "bad.pcap"
    bad.write_bytes(b"this is not a capture")
    with pytest.raises(CaptureError):
        parse_capture(bad)
