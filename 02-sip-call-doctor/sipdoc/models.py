"""Data models for parsed signaling, media statistics, findings and diagnoses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "major", "minor", "info"]
SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2, "info": 3}


class SdpMedia(BaseModel):
    kind: str
    port: int
    payload_types: list[int]
    rtpmap: dict[int, str] = Field(default_factory=dict)
    direction: str = "sendrecv"


class Sdp(BaseModel):
    connection_ip: str | None = None
    media: list[SdpMedia] = Field(default_factory=list)

    @property
    def audio(self) -> SdpMedia | None:
        return next((m for m in self.media if m.kind == "audio"), None)


class SipMessage(BaseModel):
    index: int  # position in capture order, used as evidence reference "msg#N"
    ts: float
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    size: int
    is_request: bool
    method: str | None = None
    status_code: int | None = None
    reason: str | None = None
    call_id: str
    cseq_num: int
    cseq_method: str
    from_user: str | None = None
    to_user: str | None = None
    from_tag: str | None = None
    to_tag: str | None = None
    user_agent: str | None = None
    has_auth: bool = False
    sdp: Sdp | None = None

    @property
    def label(self) -> str:
        if self.is_request:
            return f"{self.method}{' (SDP)' if self.sdp else ''}"
        return f"{self.status_code} {self.reason}{' (SDP)' if self.sdp else ''}"

    @property
    def src(self) -> str:
        return f"{self.src_ip}:{self.src_port}"

    @property
    def dst(self) -> str:
        return f"{self.dst_ip}:{self.dst_port}"


class RtpStream(BaseModel):
    ssrc: str
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    payload_type: int
    packets: int
    expected: int
    lost: int
    loss_pct: float
    jitter_ms: float
    max_jitter_ms: float
    first_ts: float
    last_ts: float
    estimated_mos: float

    @property
    def ref(self) -> str:
        return f"rtp:{self.ssrc}"

    @property
    def duration_s(self) -> float:
        return round(self.last_ts - self.first_ts, 3)


class CallFlow(BaseModel):
    call_id: str
    messages: list[SipMessage]
    streams: list[RtpStream] = Field(default_factory=list)

    @property
    def first(self) -> SipMessage:
        return self.messages[0]

    @property
    def kind(self) -> str:
        return self.first.method or self.first.cseq_method


class Evidence(BaseModel):
    ref: str  # "msg#3", "rtp:0x1a2b3c4d", "sdp@msg#1"
    fact: str


class Finding(BaseModel):
    id: str = ""  # assigned per report: F1, F2, ...
    signature: str
    severity: Severity
    title: str
    detail: str
    evidence: list[Evidence]


class CallDiagnosis(BaseModel):
    call_id: str
    kind: str
    caller: str | None
    callee: str | None
    started_at: float
    outcome: str
    final_status: int | None
    sip_messages: int
    rtp_streams: list[RtpStream]
    findings: list[Finding]
    root_cause: str | None
    summary: str
    narrator: str
    next_steps: list[str]


class AnalysisReport(BaseModel):
    analysis_id: str
    source_name: str
    packets: int
    sip_messages: int
    rtp_packets: int
    calls: list[CallDiagnosis]
    warnings: list[str] = Field(default_factory=list)
