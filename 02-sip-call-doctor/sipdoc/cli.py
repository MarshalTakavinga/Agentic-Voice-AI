"""Command line: python -m sipdoc analyze capture.pcap [--format text|json|mermaid]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sipdoc.engine import analyze_capture, ladder_mermaid, ladder_text
from sipdoc.observability import configure_logging
from sipdoc.parser import CaptureError

SEVERITY_ICON = {"critical": "!!", "major": "! ", "minor": "~ ", "info": "i "}


def render_text(report, calls) -> str:
    out = [
        f"{report.source_name}: {report.packets} packets, {report.sip_messages} SIP, "
        f"{report.rtp_packets} RTP, {len(report.calls)} dialog(s)"
    ]
    by_id = {c.call_id: c for c in calls}
    for d in report.calls:
        out += [
            "",
            "=" * 78,
            f"{d.kind} {d.call_id}  {d.caller or '?'} -> {d.callee or '?'}  "
            f"outcome={d.outcome}{f' ({d.final_status})' if d.final_status else ''}",
            "=" * 78,
            ladder_text(by_id[d.call_id]),
            "",
            f"DIAGNOSIS  {d.summary}",
        ]
        for f in d.findings:
            out.append(
                f"  {SEVERITY_ICON[f.severity]} [{f.id}] {f.severity:<8} {f.title}: {f.detail}"
            )
            out += [f"        evidence {e.ref}: {e.fact}" for e in f.evidence]
        if d.next_steps:
            out.append("  NEXT STEPS")
            out += [f"   {i}. {s}" for i, s in enumerate(d.next_steps, 1)]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sipdoc", description="Diagnose SIP/RTP captures.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyze a .pcap/.pcapng file")
    a.add_argument("capture", type=Path)
    a.add_argument("--format", choices=["text", "json", "mermaid"], default="text")
    args = parser.parse_args(argv)

    configure_logging("WARNING")
    try:
        report, parsed = analyze_capture(args.capture)
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    calls = parsed.calls()
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    elif args.format == "mermaid":
        print("\n".join(ladder_mermaid(c) for c in calls))
    else:
        print(render_text(report, calls))
    return 1 if any(d.findings for d in report.calls) else 0


if __name__ == "__main__":
    raise SystemExit(main())
