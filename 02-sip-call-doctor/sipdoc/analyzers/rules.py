"""Deterministic fault signatures. Each returns findings that carry their own evidence.

Analyzers measure; nothing downstream (including an LLM) is allowed to add measurements.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass

from sipdoc.models import CallFlow, Evidence, Finding, RtpStream, SipMessage

LOSS_MINOR, LOSS_MAJOR = 1.0, 5.0  # percent
JITTER_MINOR, JITTER_MAJOR = 30.0, 60.0  # milliseconds
UDP_MTU_RISK = 1300  # bytes; SIP over UDP above this risks IP fragmentation (RFC 3261 §18.1.1)
MIN_ANSWERED_SECONDS = 2.0

# Addresses that sit behind NAT and are unroutable on the internet. Deliberately NOT Python's
# `is_private`, which also includes documentation and benchmarking ranges.
_NAT_RANGES = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
]


def is_private(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr.version == net.version and addr in net for net in _NAT_RANGES)


@dataclass(frozen=True)
class Signature:
    name: str
    title: str
    runbook: tuple[str, ...]


SIGNATURES: dict[str, Signature] = {
    s.name: s
    for s in [
        Signature(
            "auth_failure",
            "Authentication rejected",
            (
                "Confirm the auth username, password and realm configured on the endpoint match the "
                "registrar/proxy (auth user is often different from the From user).",
                "A 403 after valid credentials usually means an IP ACL, a disabled account, or an "
                "intrusion-prevention ban (e.g. fail2ban) on the PBX — check its security log.",
                "Check for clock-skewed or reused nonces if the challenge repeats indefinitely.",
            ),
        ),
        Signature(
            "codec_mismatch",
            "No common codec",
            (
                "Compare the offered payload types with the codecs allowed on the far end "
                "(Asterisk `allow=` per endpoint, FreeSWITCH codec-prefs, SBC codec policy).",
                "Add a widely supported codec (PCMU/PCMA) to the offer, or enable transcoding on the SBC.",
                "If G.729 is involved, confirm both sides are licensed and agree on annexb.",
            ),
        ),
        Signature(
            "setup_timeout",
            "No final response to INVITE",
            (
                "Verify the destination is reachable on its SIP port/transport (firewall rules, "
                "security groups, DNS SRV/NAPTR resolution).",
                "Retransmissions with no provisional response mean the request never reached the "
                "server, or the response never came back (asymmetric routing, NAT binding expiry).",
                "Check UDP fragmentation if INVITEs are large; switch the trunk to TCP/TLS if so.",
            ),
        ),
        Signature(
            "call_rejected",
            "Call rejected by far end",
            (
                "Interpret the status code: 404 unknown number/dial plan, 480/486 user unavailable or "
                "busy, 503 overloaded or no route — check the far end's dial plan and trunk capacity.",
                "Correlate with the far end's logs using the Call-ID.",
            ),
        ),
        Signature(
            "nat_private_sdp",
            "Private address advertised in SDP",
            (
                "An endpoint behind NAT is advertising its private address for media. Configure the "
                "PBX/SBC to rewrite it: Asterisk PJSIP `external_media_address`/`local_net`, "
                "FreeSWITCH `ext-rtp-ip`, or enable symmetric RTP (`rtp_symmetric`, `comedia`).",
                "Disable or correctly configure the firewall's SIP ALG; on FortiGate review the SIP "
                "session helper and VoIP profile, since a half-working ALG commonly causes this.",
                "Prefer STUN/ICE or an SBC with media anchoring for remote endpoints.",
            ),
        ),
        Signature(
            "media_to_private_address",
            "Media sent to an unroutable address",
            (
                "RTP is being sent to a private address learned from SDP; those packets will not reach "
                "the endpoint across the internet. Fix NAT handling as for `nat_private_sdp`.",
            ),
        ),
        Signature(
            "one_way_audio",
            "Media flowing in one direction only",
            (
                "Check firewall/security-group rules for the RTP port range in both directions.",
                "Verify the SDP `c=` address and port each side advertised are reachable from the "
                "other side; check for `sendonly`/`recvonly`/`inactive` attributes (hold).",
                "Capture on both sides of the NAT/firewall to see where packets stop.",
            ),
        ),
        Signature(
            "rtp_packet_loss",
            "RTP packet loss",
            (
                "Check link utilization and errors on the media path; on SD-WAN, review the path's "
                "SLA probes and steering policy for voice.",
                "Confirm voice traffic is marked DSCP EF (46) and honored by every hop's QoS policy.",
                "Look for duplex mismatches and Wi-Fi segments on the endpoint side.",
            ),
        ),
        Signature(
            "rtp_jitter",
            "High RTP jitter",
            (
                "Prioritize voice with QoS (DSCP EF, low-latency queue) on congested links.",
                "Review the endpoint/SBC jitter buffer (adaptive, sized for observed jitter).",
                "Check for CPU saturation on media servers or transcoders.",
            ),
        ),
        Signature(
            "large_udp_sip",
            "Large SIP message over UDP",
            (
                "Messages above ~1300 bytes over UDP risk IP fragmentation and silent drops "
                "(RFC 3261 §18.1.1). Use TCP/TLS, or trim headers and SDP (remove unused codecs).",
            ),
        ),
    ]
}


# ------------------------------------------------------------------ helpers
def _invites(call: CallFlow) -> list[SipMessage]:
    return [m for m in call.messages if m.is_request and m.method == "INVITE"]


def _final_responses(call: CallFlow, method: str) -> list[SipMessage]:
    return [
        m
        for m in call.messages
        if not m.is_request and m.cseq_method == method and (m.status_code or 0) >= 200
    ]


def _ev(m: SipMessage, fact: str) -> Evidence:
    return Evidence(ref=f"msg#{m.index}", fact=fact)


def _finding(sig: str, severity: str, detail: str, evidence: list[Evidence]) -> Finding:
    return Finding(
        signature=sig,
        severity=severity,
        title=SIGNATURES[sig].title,  # type: ignore[arg-type]
        detail=detail,
        evidence=evidence,
    )


def answered(call: CallFlow) -> SipMessage | None:
    return next((m for m in _final_responses(call, "INVITE") if m.status_code == 200), None)


# ------------------------------------------------------------------ signaling analyzers
def check_setup(call: CallFlow) -> list[Finding]:
    invites = _invites(call)
    if not invites:
        return []
    finals = _final_responses(call, "INVITE")
    if not finals:
        first, last = invites[0], invites[-1]
        provisional = [
            m for m in call.messages if not m.is_request and m.status_code and m.status_code < 200
        ]
        return [
            _finding(
                "setup_timeout",
                "critical",
                f"INVITE sent {len(invites)} times over {last.ts - first.ts:.1f}s with "
                f"no final response{' and no provisional response' if not provisional else ''}.",
                [
                    _ev(first, f"INVITE {first.src} -> {first.dst}"),
                    _ev(last, f"retransmission #{len(invites) - 1}"),
                ],
            )
        ]
    final = finals[-1]
    code = final.status_code or 0
    if code == 408:
        return [
            _finding(
                "setup_timeout",
                "critical",
                "Request timed out (408).",
                [_ev(final, f"408 {final.reason}")],
            )
        ]
    if code in (488, 606):
        offer = next((m.sdp for m in invites if m.sdp and m.sdp.audio), None)
        pts = offer.audio.payload_types if offer and offer.audio else []
        codecs = (
            [offer.audio.rtpmap.get(p, f"PT {p}") for p in pts] if offer and offer.audio else []
        )
        return [
            _finding(
                "codec_mismatch",
                "critical",
                f"Far end rejected the media offer ({code}). Offered: "
                f"{', '.join(codecs) or 'unknown'}.",
                [
                    _ev(invites[0], f"SDP offer payload types {pts}"),
                    _ev(final, f"{code} {final.reason}"),
                ],
            )
        ]
    if code in (401, 407, 403):
        challenges = [m for m in call.messages if m.status_code in (401, 407)]
        authed = [m for m in invites if m.has_auth]
        if code == 403 or len(challenges) > 1 or authed:
            ev = [_ev(m, f"{m.status_code} {m.reason}") for m in challenges[:2]]
            ev += [_ev(m, "INVITE retried with credentials") for m in authed[:1]]
            ev.append(_ev(final, f"final {code} {final.reason}"))
            return [
                _finding(
                    "auth_failure",
                    "critical",
                    "Credentials were challenged and the authenticated retry was rejected."
                    if authed
                    else f"Request rejected with {code}.",
                    ev,
                )
            ]
        return []  # a single challenge without retry is normal digest negotiation in progress
    if code >= 300 and code not in (487,):  # 487 = caller cancelled: not a fault
        return [
            _finding(
                "call_rejected",
                "major" if code >= 500 else "minor",
                f"Call ended with {code} {final.reason}.",
                [_ev(final, f"{code} {final.reason} from {final.src}")],
            )
        ]
    return []


def check_register(call: CallFlow) -> list[Finding]:
    if call.kind != "REGISTER":
        return []
    finals = _final_responses(call, "REGISTER")
    rejected = [m for m in finals if m.status_code == 403]
    challenges = [m for m in finals if m.status_code in (401, 407)]
    retried = [m for m in call.messages if m.is_request and m.method == "REGISTER" and m.has_auth]
    if rejected or (retried and challenges and challenges[-1].index > retried[-1].index):
        last = (rejected or challenges)[-1]
        return [
            _finding(
                "auth_failure",
                "critical",
                "Registration failed authentication.",
                [_ev(last, f"REGISTER answered {last.status_code} {last.reason}")],
            )
        ]
    return []


def check_large_udp(call: CallFlow) -> list[Finding]:
    big = [m for m in call.messages if m.size > UDP_MTU_RISK]
    if not big:
        return []
    m = max(big, key=lambda x: x.size)
    return [
        _finding(
            "large_udp_sip",
            "minor",
            f"{len(big)} SIP message(s) exceed {UDP_MTU_RISK} bytes over UDP "
            f"(largest {m.size} bytes).",
            [_ev(m, f"{m.label} is {m.size} bytes")],
        )
    ]


def check_nat(call: CallFlow) -> list[Finding]:
    findings = []
    for m in call.messages:
        if m.sdp and is_private(m.sdp.connection_ip) and not is_private(m.src_ip):
            findings.append(
                _finding(
                    "nat_private_sdp",
                    "major",
                    f"SDP advertises private media address {m.sdp.connection_ip} but the message "
                    f"arrived from public address {m.src_ip}: the endpoint is behind NAT and its "
                    "SDP was not rewritten.",
                    [
                        _ev(m, f"SDP c={m.sdp.connection_ip} in {m.label}"),
                        _ev(m, f"signaling source {m.src}"),
                    ],
                )
            )
            break
    public_signaling = {m.src_ip for m in call.messages if not is_private(m.src_ip)}
    for s in call.streams:
        if is_private(s.dst_ip) and public_signaling and not is_private(s.src_ip):
            findings.append(
                _finding(
                    "media_to_private_address",
                    "critical",
                    f"{s.packets} RTP packets were sent to private address {s.dst_ip}:{s.dst_port}, "
                    "which is unreachable from the public internet.",
                    [
                        Evidence(
                            ref=s.ref,
                            fact=f"RTP {s.src_ip}:{s.src_port} -> "
                            f"{s.dst_ip}:{s.dst_port}, {s.packets} packets",
                        )
                    ],
                )
            )
    return findings


# ------------------------------------------------------------------ media analyzers
def check_media_direction(call: CallFlow) -> list[Finding]:
    ok = answered(call)
    if ok is None:
        return []
    end = max(m.ts for m in call.messages)
    if end - ok.ts < MIN_ANSWERED_SECONDS:
        return []
    inv = _invites(call)[0]
    caller_ip, callee_ip = inv.src_ip, ok.src_ip
    toward_callee = [s for s in call.streams if s.src_ip == caller_ip]
    toward_caller = [s for s in call.streams if s.src_ip == callee_ip]
    duration = f"{end - ok.ts:.1f}s"
    if not call.streams:
        return [
            _finding(
                "one_way_audio",
                "critical",
                f"Call was answered and lasted {duration} but no RTP was captured in "
                "either direction (no audio, or capture point misses the media path).",
                [_ev(ok, "200 OK to INVITE"), _ev(call.messages[-1], "call ended")],
            )
        ]
    for missing, present, who in (
        (toward_caller, toward_callee, "callee to caller"),
        (toward_callee, toward_caller, "caller to callee"),
    ):
        if not missing and present:
            s = present[0]
            return [
                _finding(
                    "one_way_audio",
                    "critical",
                    f"RTP observed only one way; nothing from {who} during a "
                    f"{duration} answered call.",
                    [
                        _ev(ok, "200 OK to INVITE"),
                        Evidence(
                            ref=s.ref,
                            fact=f"only stream: {s.src_ip}:{s.src_port} -> "
                            f"{s.dst_ip}:{s.dst_port}, {s.packets} pkts",
                        ),
                    ],
                )
            ]
    return []


def check_rtp_quality(call: CallFlow) -> list[Finding]:
    findings = []
    for s in call.streams:
        if s.loss_pct >= LOSS_MINOR:
            findings.append(
                _finding(
                    "rtp_packet_loss",
                    "major" if s.loss_pct >= LOSS_MAJOR else "minor",
                    f"{s.loss_pct}% loss ({s.lost} of {s.expected} packets) on "
                    f"{s.src_ip} -> {s.dst_ip}; estimated MOS {s.estimated_mos}.",
                    [_stream_ev(s, f"loss {s.loss_pct}% ({s.lost}/{s.expected})")],
                )
            )
        if s.jitter_ms >= JITTER_MINOR:
            findings.append(
                _finding(
                    "rtp_jitter",
                    "major" if s.jitter_ms >= JITTER_MAJOR else "minor",
                    f"Mean interarrival jitter {s.jitter_ms} ms (peak {s.max_jitter_ms} ms) on "
                    f"{s.src_ip} -> {s.dst_ip}.",
                    [_stream_ev(s, f"jitter {s.jitter_ms} ms, peak {s.max_jitter_ms} ms")],
                )
            )
    return findings


def _stream_ev(s: RtpStream, fact: str) -> Evidence:
    return Evidence(ref=s.ref, fact=fact)


ANALYZERS: list[Callable[[CallFlow], list[Finding]]] = [
    check_setup,
    check_register,
    check_nat,
    check_media_direction,
    check_rtp_quality,
    check_large_udp,
]

# Root-cause precedence: a failed setup explains everything after it; NAT explains one-way audio.
ROOT_CAUSE_ORDER = [
    "auth_failure",
    "codec_mismatch",
    "setup_timeout",
    "call_rejected",
    "media_to_private_address",
    "nat_private_sdp",
    "one_way_audio",
    "rtp_packet_loss",
    "rtp_jitter",
    "large_udp_sip",
]
