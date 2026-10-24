"""Analysis pipeline: capture → calls → findings → diagnosis, plus ladder rendering."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from sipdoc.analyzers import SIGNATURES, analyze_call, pick_root_cause
from sipdoc.analyzers.rules import answered
from sipdoc.models import AnalysisReport, CallDiagnosis, CallFlow
from sipdoc.narrator import Narrator, TemplateNarrator
from sipdoc.observability import ANALYSES, ANALYSIS_SECONDS, FINDINGS, log, mask_number
from sipdoc.parser import ParsedCapture, parse_capture


def _outcome(call: CallFlow) -> tuple[str, int | None]:
    if call.kind == "REGISTER":
        finals = [m for m in call.messages if not m.is_request and (m.status_code or 0) >= 200]
        code = finals[-1].status_code if finals else None
        return ("registered" if code == 200 else "registration_failed"), code
    finals = [
        m
        for m in call.messages
        if not m.is_request and m.cseq_method == "INVITE" and (m.status_code or 0) >= 200
    ]
    if not finals:
        return "no_final_response", None
    code = finals[-1].status_code
    if answered(call):
        return "answered", code
    return ("cancelled" if code == 487 else "failed"), code


def _context(call: CallFlow) -> str:
    outcome, code = _outcome(call)
    parts = [f"Outcome: {outcome}{f' ({code})' if code else ''}."]
    if call.streams:
        worst_loss = max(s.loss_pct for s in call.streams)
        worst_jitter = max(s.jitter_ms for s in call.streams)
        parts.append(
            f"{len(call.streams)} RTP stream(s); worst loss {worst_loss}%, "
            f"worst jitter {worst_jitter} ms."
        )
    return " ".join(parts)


def diagnose(call: CallFlow, narrator: Narrator) -> CallDiagnosis:
    findings = analyze_call(call)
    for f in findings:
        FINDINGS.labels(f.signature, f.severity).inc()
    root = pick_root_cause(findings)
    outcome, code = _outcome(call)
    steps: list[str] = []
    for f in findings:  # runbook steps for each distinct signature, root cause first
        for step in SIGNATURES[f.signature].runbook:
            if step not in steps:
                steps.append(step)
    return CallDiagnosis(
        call_id=call.call_id,
        kind=call.kind,
        caller=mask_number(call.first.from_user),
        callee=mask_number(call.first.to_user),
        started_at=call.first.ts,
        outcome=outcome,
        final_status=code,
        sip_messages=len(call.messages),
        rtp_streams=call.streams,
        findings=findings,
        root_cause=root.signature if root else None,
        summary=narrator.narrate(findings, _context(call)),
        narrator=narrator.name,
        next_steps=steps[:6],
    )


def analyze_capture(
    path: Path, source_name: str | None = None, narrator: Narrator | None = None
) -> tuple[AnalysisReport, ParsedCapture]:
    narrator = narrator or TemplateNarrator()
    started = time.perf_counter()
    try:
        parsed = parse_capture(path)
    except Exception:
        ANALYSES.labels("error").inc()
        raise
    calls = parsed.calls()
    report = AnalysisReport(
        analysis_id=f"AN{uuid.uuid4().hex[:12]}",
        source_name=source_name or path.name,
        packets=parsed.packets,
        sip_messages=len(parsed.messages),
        rtp_packets=parsed.rtp_packets,
        calls=[diagnose(c, narrator) for c in calls],
        warnings=parsed.warnings,
    )
    elapsed = time.perf_counter() - started
    ANALYSES.labels("ok").inc()
    ANALYSIS_SECONDS.observe(elapsed)
    log.info(
        "analysis_complete",
        analysis_id=report.analysis_id,
        calls=len(report.calls),
        packets=report.packets,
        seconds=round(elapsed, 3),
    )
    return report, parsed


def ladder_mermaid(call: CallFlow) -> str:
    """Mermaid sequence diagram of the SIP exchange with RTP streams as notes."""
    hosts: list[str] = []
    for m in call.messages:
        for h in (m.src, m.dst):
            if h not in hosts:
                hosts.append(h)
    alias = {h: f"H{i}" for i, h in enumerate(hosts)}
    lines = ["sequenceDiagram"]
    lines += [f"    participant {alias[h]} as {h}" for h in hosts]
    t0 = call.first.ts
    for m in call.messages:
        arrow = "->>" if m.is_request else "-->>"
        lines.append(
            f"    {alias[m.src]}{arrow}{alias[m.dst]}: {m.index}. {m.label} (+{m.ts - t0:.2f}s)"
        )
    for s in call.streams:
        src = next((h for h in hosts if h.startswith(s.src_ip + ":")), hosts[0])
        lines.append(
            f"    Note over {alias[src]}: RTP {s.ssrc} to {s.dst_ip}:{s.dst_port} "
            f"{s.packets} pkts, loss {s.loss_pct}%, jitter {s.jitter_ms} ms"
        )
    return "\n".join(lines) + "\n"


def ladder_text(call: CallFlow) -> str:
    t0 = call.first.ts
    rows = [f"{'#':>3}  {'+time':>7}  {'from':<22} {'':2} {'to':<22}  message"]
    for m in call.messages:
        rows.append(f"{m.index:>3}  {m.ts - t0:>6.2f}s  {m.src:<22} -> {m.dst:<22}  {m.label}")
    for s in call.streams:
        rows.append(
            f"     RTP {s.ssrc} {s.src_ip}:{s.src_port} -> {s.dst_ip}:{s.dst_port}  "
            f"{s.packets} pkts  loss {s.loss_pct}%  jitter {s.jitter_ms} ms  "
            f"MOS~{s.estimated_mos}"
        )
    return "\n".join(rows)
