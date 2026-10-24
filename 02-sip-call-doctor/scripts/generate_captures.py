"""Generate labeled synthetic pcaps, one per fault scenario, plus captures/labels.json.

All addresses are documentation ranges (RFC 5737) or RFC 1918; numbers use the 555-01xx
fictional block. Usage: python scripts/generate_captures.py
"""

from __future__ import annotations

import json
import random
import struct
from pathlib import Path

from scapy.layers.inet import IP, UDP
from scapy.layers.l2 import Ether
from scapy.packet import Raw
from scapy.utils import wrpcap

OUT = Path(__file__).resolve().parent.parent / "captures"
T0 = 1_792_850_400.0  # fixed epoch for reproducibility
PBX = ("192.0.2.10", 5060)
PHONE = ("198.51.100.20", 5060)
CALLER, CALLEE = "+15550101234", "+15550109876"
RTPMAP = {
    0: "PCMU/8000",
    8: "PCMA/8000",
    18: "G729/8000",
    9: "G722/8000",
    101: "telephone-event/8000",
}


class Capture:
    def __init__(self, seed: int) -> None:
        self.pkts: list = []
        self.rng = random.Random(seed)

    def udp(self, t: float, src: tuple[str, int], dst: tuple[str, int], payload: bytes) -> None:
        # Explicit MACs: without them scapy tries ARP resolution for every packet.
        eth = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
        pkt = eth / IP(src=src[0], dst=dst[0]) / UDP(sport=src[1], dport=dst[1]) / Raw(payload)
        pkt.time = T0 + t
        self.pkts.append(pkt)

    def sip(
        self,
        t: float,
        src,
        dst,
        start: str,
        call_id: str,
        cseq: str,
        from_tag: str,
        to_tag: str | None = None,
        sdp: str | None = None,
        extra: list[str] | None = None,
    ) -> None:
        to = f"<sip:{CALLEE}@{PBX[0]}>" + (f";tag={to_tag}" if to_tag else "")
        headers = [
            start,
            f"Via: SIP/2.0/UDP {PHONE[0]}:{PHONE[1]};branch=z9hG4bK{call_id[:8]}{cseq.split()[0]}",
            "Max-Forwards: 70",
            f"From: <sip:{CALLER}@{PHONE[0]}>;tag={from_tag}",
            f"To: {to}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq}",
            f"Contact: <sip:{CALLER}@{src[0]}:{src[1]}>",
            "User-Agent: LabPhone/2.1",
            *(extra or []),
        ]
        body = sdp or ""
        if sdp:
            headers.append("Content-Type: application/sdp")
        headers.append(f"Content-Length: {len(body.encode())}")
        self.udp(t, src, dst, ("\r\n".join(headers) + "\r\n\r\n" + body).encode())

    def rtp(
        self,
        start: float,
        src,
        dst,
        ssrc: int,
        pt: int = 0,
        seconds: float = 5.0,
        loss_pct: float = 0.0,
        jitter_sigma_ms: float = 0.0,
    ) -> None:
        n = int(seconds / 0.02)
        seq0, ts0 = self.rng.randint(0, 60000), self.rng.randint(0, 2**31)
        for i in range(n):
            if loss_pct and self.rng.random() < loss_pct / 100:
                continue
            arrival = (
                start
                + i * 0.02
                + (abs(self.rng.gauss(0, jitter_sigma_ms / 1000)) if jitter_sigma_ms else 0.0)
            )
            header = struct.pack(
                "!BBHII", 0x80, pt, (seq0 + i) & 0xFFFF, (ts0 + i * 160) & 0xFFFFFFFF, ssrc
            )
            self.udp(arrival, src, dst, header + bytes(160))  # silent payload: no real audio

    def write(self, name: str) -> None:
        self.pkts.sort(key=lambda p: p.time)
        wrpcap(str(OUT / f"{name}.pcap"), self.pkts)


def sdp(ip: str, port: int, pts: list[int], direction: str = "sendrecv", pad: int = 0) -> str:
    lines = [
        "v=0",
        f"o=- 4242 4242 IN IP4 {ip}",
        "s=call",
        f"c=IN IP4 {ip}",
        "t=0 0",
        f"m=audio {port} RTP/AVP {' '.join(map(str, pts))}",
    ]
    lines += [f"a=rtpmap:{p} {RTPMAP[p]}" for p in pts if p in RTPMAP]
    lines += [f"a=x-lab-padding:{'x' * 60}" for _ in range(pad)]
    lines.append(f"a={direction}")
    return "\r\n".join(lines) + "\r\n"


def answered_call(
    cap: Capture,
    cid: str,
    caller=PHONE,
    caller_sdp_ip: str | None = None,
    rtp: str = "both",
    loss: float = 0.0,
    jitter: float = 0.0,
) -> None:
    sdp_ip = caller_sdp_ip or caller[0]
    cap.sip(
        0.00,
        caller,
        PBX,
        f"INVITE sip:{CALLEE}@{PBX[0]} SIP/2.0",
        cid,
        "1 INVITE",
        "a1",
        sdp=sdp(sdp_ip, 16384, [0, 8, 101]),
    )
    cap.sip(0.02, PBX, caller, "SIP/2.0 100 Trying", cid, "1 INVITE", "a1")
    cap.sip(0.50, PBX, caller, "SIP/2.0 180 Ringing", cid, "1 INVITE", "a1", "b1")
    cap.sip(
        2.00,
        PBX,
        caller,
        "SIP/2.0 200 OK",
        cid,
        "1 INVITE",
        "a1",
        "b1",
        sdp=sdp(PBX[0], 20000, [0, 101]),
    )
    cap.sip(2.05, caller, PBX, f"ACK sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "1 ACK", "a1", "b1")
    if rtp in ("both", "caller_only"):
        cap.rtp(2.10, (caller[0], 16384), (PBX[0], 20000), 0x1A2B3C4D)
    if rtp == "both":
        # PBX sends where the SDP told it to; behind NAT that is an unroutable private address.
        cap.rtp(
            2.11,
            (PBX[0], 20000),
            (sdp_ip, 16384),
            0x5E6F7A8B,
            loss_pct=loss,
            jitter_sigma_ms=jitter,
        )
    cap.sip(7.20, caller, PBX, f"BYE sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "2 BYE", "a1", "b1")
    cap.sip(7.25, PBX, caller, "SIP/2.0 200 OK", cid, "2 BYE", "a1", "b1")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    labels: dict[str, dict] = {}

    def done(name: str, cap: Capture, signatures: list[str], root: str | None, note: str) -> None:
        cap.write(name)
        labels[name] = {"signatures": sorted(signatures), "root_cause": root, "note": note}

    c = Capture(1)
    answered_call(c, "healthy-0001@lab")
    done("healthy_call", c, [], None, "Normal answered call with clean bidirectional RTP.")

    c = Capture(2)
    answered_call(c, "nat-0002@lab", caller=("203.0.113.10", 5060), caller_sdp_ip="192.168.1.50")
    done(
        "nat_one_way_audio",
        c,
        ["media_to_private_address", "nat_private_sdp"],
        "media_to_private_address",
        "Phone behind NAT advertises 192.168.1.50; PBX sends RTP there, caller hears nothing.",
    )

    c = Capture(3)
    answered_call(c, "oneway-0003@lab", rtp="caller_only")
    done(
        "one_way_firewall",
        c,
        ["one_way_audio"],
        "one_way_audio",
        "Answered call; PBX never sends RTP (e.g. blocked RTP port range).",
    )

    c = Capture(4)
    cid = "codec-0004@lab"
    c.sip(
        0.0,
        PHONE,
        PBX,
        f"INVITE sip:{CALLEE}@{PBX[0]} SIP/2.0",
        cid,
        "1 INVITE",
        "a1",
        sdp=sdp(PHONE[0], 16384, [18]),
    )
    c.sip(0.02, PBX, PHONE, "SIP/2.0 100 Trying", cid, "1 INVITE", "a1")
    c.sip(0.05, PBX, PHONE, "SIP/2.0 488 Not Acceptable Here", cid, "1 INVITE", "a1", "b1")
    c.sip(0.06, PHONE, PBX, f"ACK sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "1 ACK", "a1", "b1")
    done(
        "codec_mismatch",
        c,
        ["codec_mismatch"],
        "codec_mismatch",
        "Phone offers only G.729; PBX does not allow it.",
    )

    c = Capture(5)
    cid = "auth-0005@lab"
    c.sip(
        0.0,
        PHONE,
        PBX,
        f"INVITE sip:{CALLEE}@{PBX[0]} SIP/2.0",
        cid,
        "1 INVITE",
        "a1",
        sdp=sdp(PHONE[0], 16384, [0, 8]),
    )
    c.sip(
        0.02,
        PBX,
        PHONE,
        "SIP/2.0 407 Proxy Authentication Required",
        cid,
        "1 INVITE",
        "a1",
        "b1",
        extra=['Proxy-Authenticate: Digest realm="lab", nonce="abc123", algorithm=MD5'],
    )
    c.sip(0.03, PHONE, PBX, f"ACK sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "1 ACK", "a1", "b1")
    c.sip(
        0.05,
        PHONE,
        PBX,
        f"INVITE sip:{CALLEE}@{PBX[0]} SIP/2.0",
        cid,
        "2 INVITE",
        "a1",
        sdp=sdp(PHONE[0], 16384, [0, 8]),
        extra=[
            'Proxy-Authorization: Digest username="1001", realm="lab", nonce="abc123", '
            'response="0000000000000000"'
        ],
    )
    c.sip(0.07, PBX, PHONE, "SIP/2.0 403 Forbidden", cid, "2 INVITE", "a1", "b2")
    c.sip(0.08, PHONE, PBX, f"ACK sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "2 ACK", "a1", "b2")
    done(
        "auth_failure",
        c,
        ["auth_failure"],
        "auth_failure",
        "Digest challenge answered with wrong credentials, then 403.",
    )

    c = Capture(6)
    cid = "timeout-0006@lab"
    big = sdp(PHONE[0], 16384, [0, 8, 9, 18, 101], pad=14)
    for i, t in enumerate([0.0, 0.5, 1.5, 3.5, 7.5, 11.5, 15.5]):  # RFC 3261 Timer A backoff
        c.sip(
            t,
            PHONE,
            ("192.0.2.99", 5060),
            "INVITE sip:+15550104444@192.0.2.99 SIP/2.0",
            cid,
            "1 INVITE",
            "a1",
            sdp=big,
        )
        _ = i
    done(
        "setup_timeout",
        c,
        ["large_udp_sip", "setup_timeout"],
        "setup_timeout",
        "Oversized INVITE over UDP to an unreachable trunk; retransmitted, never answered.",
    )

    c = Capture(7)
    answered_call(c, "quality-0007@lab", loss=6.0, jitter=60.0)
    done(
        "poor_quality",
        c,
        ["rtp_jitter", "rtp_packet_loss"],
        "rtp_packet_loss",
        "Congested WAN: heavy packet loss and jitter toward the caller.",
    )

    c = Capture(8)
    cid = "busy-0008@lab"
    c.sip(
        0.0,
        PHONE,
        PBX,
        f"INVITE sip:{CALLEE}@{PBX[0]} SIP/2.0",
        cid,
        "1 INVITE",
        "a1",
        sdp=sdp(PHONE[0], 16384, [0, 8]),
    )
    c.sip(0.02, PBX, PHONE, "SIP/2.0 100 Trying", cid, "1 INVITE", "a1")
    c.sip(1.20, PBX, PHONE, "SIP/2.0 486 Busy Here", cid, "1 INVITE", "a1", "b1")
    c.sip(1.21, PHONE, PBX, f"ACK sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "1 ACK", "a1", "b1")
    done("busy_486", c, ["call_rejected"], "call_rejected", "Callee busy.")

    c = Capture(9)
    cid = "reg-0009@lab"
    c.sip(0.0, PHONE, PBX, f"REGISTER sip:{PBX[0]} SIP/2.0", cid, "1 REGISTER", "a1")
    c.sip(
        0.02,
        PBX,
        PHONE,
        "SIP/2.0 401 Unauthorized",
        cid,
        "1 REGISTER",
        "a1",
        "b1",
        extra=['WWW-Authenticate: Digest realm="lab", nonce="n1"'],
    )
    c.sip(
        0.05,
        PHONE,
        PBX,
        f"REGISTER sip:{PBX[0]} SIP/2.0",
        cid,
        "2 REGISTER",
        "a1",
        extra=['Authorization: Digest username="1001", realm="lab", nonce="n1", response="x"'],
    )
    c.sip(
        0.07,
        PBX,
        PHONE,
        "SIP/2.0 401 Unauthorized",
        cid,
        "2 REGISTER",
        "a1",
        "b2",
        extra=['WWW-Authenticate: Digest realm="lab", nonce="n2"'],
    )
    done(
        "register_auth_failure",
        c,
        ["auth_failure"],
        "auth_failure",
        "Registration retried with credentials and challenged again: wrong password.",
    )

    c = Capture(10)
    cid = "cancel-0010@lab"
    c.sip(
        0.0,
        PHONE,
        PBX,
        f"INVITE sip:{CALLEE}@{PBX[0]} SIP/2.0",
        cid,
        "1 INVITE",
        "a1",
        sdp=sdp(PHONE[0], 16384, [0, 8]),
    )
    c.sip(0.02, PBX, PHONE, "SIP/2.0 100 Trying", cid, "1 INVITE", "a1")
    c.sip(0.40, PBX, PHONE, "SIP/2.0 180 Ringing", cid, "1 INVITE", "a1", "b1")
    c.sip(3.00, PHONE, PBX, f"CANCEL sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "1 CANCEL", "a1")
    c.sip(3.02, PBX, PHONE, "SIP/2.0 200 OK", cid, "1 CANCEL", "a1", "b1")
    c.sip(3.03, PBX, PHONE, "SIP/2.0 487 Request Terminated", cid, "1 INVITE", "a1", "b1")
    c.sip(3.04, PHONE, PBX, f"ACK sip:{CALLEE}@{PBX[0]} SIP/2.0", cid, "1 ACK", "a1", "b1")
    done("caller_cancelled", c, [], None, "Caller hung up while ringing: normal, not a fault.")

    (OUT / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    print(f"wrote {len(labels)} captures to {OUT}")


if __name__ == "__main__":
    main()
