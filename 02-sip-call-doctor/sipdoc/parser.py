"""Packet capture → SIP messages, SDP and per-stream RTP statistics.

RTP payloads (the audio itself) are never retained; only header fields are read.
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from scapy.layers.inet import IP, UDP
from scapy.layers.inet6 import IPv6
from scapy.utils import PcapReader

from sipdoc.models import CallFlow, RtpStream, Sdp, SdpMedia, SipMessage

MAX_PACKETS = 500_000

_REQUEST_LINE = re.compile(rb"^([A-Z]{3,10}) (sips?:\S+) SIP/2\.0\r?\n")
_STATUS_LINE = re.compile(rb"^SIP/2\.0 (\d{3}) ([^\r\n]*)\r?\n")
_COMPACT = {
    "i": "call-id",
    "f": "from",
    "t": "to",
    "v": "via",
    "c": "content-type",
    "l": "content-length",
    "m": "contact",
    "k": "supported",
}
_URI_USER = re.compile(r"sips?:([^@;>]+)@")
_TAG = re.compile(r";\s*tag=([^;>\s]+)", re.I)

# Static RTP clock rates (RFC 3551). Dynamic payload types default to 8 kHz unless rtpmap says.
_CLOCK = {0: 8000, 3: 8000, 4: 8000, 8: 8000, 9: 8000, 13: 8000, 18: 8000}


class CaptureError(ValueError):
    pass


@dataclass
class ParsedCapture:
    packets: int = 0
    rtp_packets: int = 0
    messages: list[SipMessage] = field(default_factory=list)
    streams: list[RtpStream] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def calls(self) -> list[CallFlow]:
        by_id: dict[str, list[SipMessage]] = defaultdict(list)
        for m in self.messages:
            by_id[m.call_id].append(m)
        calls = [CallFlow(call_id=cid, messages=msgs) for cid, msgs in by_id.items()]
        _attach_streams(calls, self.streams)
        return sorted(calls, key=lambda c: c.first.ts)


# ------------------------------------------------------------------ SIP / SDP
def parse_sip(
    payload: bytes, index: int, ts: float, src: tuple[str, int], dst: tuple[str, int]
) -> SipMessage | None:
    req, resp = _REQUEST_LINE.match(payload), _STATUS_LINE.match(payload)
    if not (req or resp):
        return None
    head, _, body = payload.partition(b"\r\n\r\n")
    if not _:
        head, _, body = payload.partition(b"\n\n")
    lines = head.decode("utf-8", "replace").splitlines()[1:]
    headers: dict[str, str] = {}
    for line in lines:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = _COMPACT.get(name.strip().lower(), name.strip().lower())
        headers.setdefault(key, value.strip())
    if "call-id" not in headers or "cseq" not in headers:
        return None
    cseq_num, _, cseq_method = headers["cseq"].partition(" ")
    ctype = headers.get("content-type", "").lower()
    sdp = parse_sdp(body.decode("utf-8", "replace")) if "sdp" in ctype and body else None
    return SipMessage(
        index=index,
        ts=ts,
        src_ip=src[0],
        src_port=src[1],
        dst_ip=dst[0],
        dst_port=dst[1],
        size=len(payload),
        is_request=bool(req),
        method=req.group(1).decode() if req else None,
        status_code=int(resp.group(1)) if resp else None,
        reason=resp.group(2).decode("utf-8", "replace").strip() if resp else None,
        call_id=headers["call-id"],
        cseq_num=int(cseq_num or 0),
        cseq_method=cseq_method.strip().upper(),
        from_user=_user(headers.get("from")),
        to_user=_user(headers.get("to")),
        from_tag=_tag(headers.get("from")),
        to_tag=_tag(headers.get("to")),
        user_agent=headers.get("user-agent") or headers.get("server"),
        has_auth="authorization" in headers or "proxy-authorization" in headers,
        sdp=sdp,
    )


def parse_sdp(text: str) -> Sdp:
    sdp = Sdp()
    media: SdpMedia | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("c=") and line.split()[-1]:
            ip = line.split()[-1].split("/")[0]
            if media is None or sdp.connection_ip is None:
                sdp.connection_ip = ip
        elif line.startswith("m="):
            parts = line[2:].split()
            pts = [int(p) for p in parts[3:] if p.isdigit()]
            media = SdpMedia(kind=parts[0], port=int(parts[1]), payload_types=pts)
            sdp.media.append(media)
        elif line.startswith("a=rtpmap:") and media is not None:
            pt, _, codec = line[9:].partition(" ")
            if pt.isdigit():
                media.rtpmap[int(pt)] = codec
        elif line[2:] in ("sendrecv", "sendonly", "recvonly", "inactive") and media is not None:
            media.direction = line[2:]
    return sdp


def _user(value: str | None) -> str | None:
    m = _URI_USER.search(value or "")
    return m.group(1) if m else None


def _tag(value: str | None) -> str | None:
    m = _TAG.search(value or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------ RTP
@dataclass
class _StreamAcc:
    key: tuple
    pt: int
    clock: int = 8000
    count: int = 0
    first_ts: float = 0.0
    last_ts: float = 0.0
    base_seq: int | None = None
    max_ext: int = 0
    cycles: int = 0
    last_seq: int = 0
    jitter: float = 0.0
    max_jitter: float = 0.0
    prev_transit: float | None = None

    def add(self, seq: int, rtp_ts: int, arrival: float) -> None:
        if self.base_seq is None:
            self.base_seq, self.max_ext, self.last_seq = seq, seq, seq
            self.first_ts = arrival
        else:
            if seq < self.last_seq and self.last_seq - seq > 30000:
                self.cycles += 65536  # sequence wrapped
            ext = self.cycles + seq
            self.max_ext = max(self.max_ext, ext)
            self.last_seq = seq
        self.count += 1
        self.last_ts = arrival
        # RFC 3550 §A.8 interarrival jitter, in timestamp units.
        transit = arrival * self.clock - rtp_ts
        if self.prev_transit is not None:
            d = abs(transit - self.prev_transit)
            self.jitter += (d - self.jitter) / 16
            self.max_jitter = max(self.max_jitter, self.jitter)
        self.prev_transit = transit

    def finish(self) -> RtpStream:
        expected = self.max_ext - (self.base_seq or 0) + 1
        lost = max(expected - self.count, 0)
        loss_pct = round(100 * lost / expected, 2) if expected else 0.0
        jitter_ms = round(1000 * self.jitter / self.clock, 2)
        ssrc, src_ip, src_port, dst_ip, dst_port = self.key
        return RtpStream(
            ssrc=ssrc,
            src_ip=src_ip,
            src_port=src_port,
            dst_ip=dst_ip,
            dst_port=dst_port,
            payload_type=self.pt,
            packets=self.count,
            expected=expected,
            lost=lost,
            loss_pct=loss_pct,
            jitter_ms=jitter_ms,
            max_jitter_ms=round(1000 * self.max_jitter / self.clock, 2),
            first_ts=self.first_ts,
            last_ts=self.last_ts,
            estimated_mos=estimate_mos(jitter_ms, loss_pct),
        )


def estimate_mos(jitter_ms: float, loss_pct: float, latency_ms: float = 0.0) -> float:
    """Simplified E-model (ITU-T G.107 style approximation). Indicative only: one-way latency is
    not observable from a single capture point, so it defaults to 0."""
    effective = latency_ms + 2 * jitter_ms + 10
    r = 93.2 - effective / 40 if effective < 160 else 93.2 - (effective - 120) / 10
    r = max(0.0, min(100.0, r - 2.5 * loss_pct))
    return round(1 + 0.035 * r + 7e-6 * r * (r - 60) * (100 - r), 2)


def _looks_like_rtp(payload: bytes) -> bool:
    if len(payload) < 12 or payload[0] >> 6 != 2:
        return False
    pt = payload[1] & 0x7F
    return not (72 <= pt <= 76)  # 200-204 with marker bit = RTCP


# ------------------------------------------------------------------ capture
def parse_capture(path: Path, max_packets: int = MAX_PACKETS) -> ParsedCapture:
    out = ParsedCapture()
    streams: dict[tuple, _StreamAcc] = {}
    sip_ports: set[int] = {5060, 5061}
    try:
        reader = PcapReader(str(path))
    except Exception as exc:  # noqa: BLE001 - scapy raises several types for bad files
        raise CaptureError(f"not a readable pcap/pcapng file: {type(exc).__name__}") from exc
    with reader:
        for pkt in reader:
            out.packets += 1
            if out.packets > max_packets:
                out.warnings.append(f"capture truncated at {max_packets} packets")
                break
            ip = pkt.getlayer(IP) or pkt.getlayer(IPv6)
            udp = pkt.getlayer(UDP)
            if ip is None or udp is None:
                continue
            payload = bytes(udp.payload)
            src, dst = (ip.src, int(udp.sport)), (ip.dst, int(udp.dport))
            ts = float(pkt.time)
            msg = parse_sip(payload, len(out.messages) + 1, ts, src, dst)
            if msg is not None:
                out.messages.append(msg)
                sip_ports.update((src[1], dst[1]))
                continue
            if src[1] in sip_ports or dst[1] in sip_ports or not _looks_like_rtp(payload):
                continue
            _, pt_byte, seq, rtp_ts, ssrc = struct.unpack("!BBHII", payload[:12])
            key = (f"0x{ssrc:08x}", src[0], src[1], dst[0], dst[1])
            acc = streams.get(key)
            if acc is None:
                pt = pt_byte & 0x7F
                acc = streams[key] = _StreamAcc(key=key, pt=pt, clock=_CLOCK.get(pt, 8000))
            acc.add(seq, rtp_ts, ts)
            out.rtp_packets += 1
    if out.packets == 0:
        raise CaptureError("capture contains no packets")
    out.streams = [a.finish() for a in streams.values() if a.count >= 5]  # ignore stray UDP
    return out


def _attach_streams(calls: list[CallFlow], streams: list[RtpStream]) -> None:
    """Associate RTP streams with calls using SDP-advertised addresses, then ports, then time."""
    endpoints: dict[str, set[tuple[str, int]]] = {}
    ports: dict[str, set[int]] = {}
    for call in calls:
        eps, ps = set(), set()
        for m in call.messages:
            if m.sdp and m.sdp.audio and m.sdp.connection_ip:
                eps.add((m.sdp.connection_ip, m.sdp.audio.port))
                ps.add(m.sdp.audio.port)
        endpoints[call.call_id], ports[call.call_id] = eps, ps
    for s in streams:
        target = None
        for call in calls:
            eps = endpoints[call.call_id]
            if (s.dst_ip, s.dst_port) in eps or (s.src_ip, s.src_port) in eps:
                target = call
                break
        if target is None:  # NAT rewrites addresses but usually preserves ports
            for call in calls:
                if s.dst_port in ports[call.call_id] or s.src_port in ports[call.call_id]:
                    target = call
                    break
        if target is not None:
            target.streams.append(s)
