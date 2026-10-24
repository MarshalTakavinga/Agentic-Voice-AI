"""Capture analysis UI for project 02."""

import html
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from sipdoc.engine import analyze_capture, ladder_mermaid, ladder_text
from sipdoc.evals import CAPTURES
from sipdoc.parser import CaptureError

MAX_UPLOAD_MB = 20
SEVERITY = {"critical": "🔴", "major": "🟠", "minor": "🟡", "info": "🔵"}
LABELS = json.loads((CAPTURES / "labels.json").read_text())


def render_mermaid(code: str, rows: int) -> None:
    page = f"""
    <div class="mermaid">{html.escape(code)}</div>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{ startOnLoad: true, theme: "neutral", securityLevel: "strict" }});
    </script>"""
    components.html(page, height=min(140 + 48 * rows, 1400), scrolling=True)


st.title("🩺 SIP Call Doctor")
st.caption(
    "Deterministic analyzers measure; the explanation cites their findings. "
    "Bundled captures are synthetic; uploads are analyzed in memory and not stored."
)

source = st.radio("Capture", ["Sample capture", "Upload your own"], horizontal=True)
path, name, expected = None, None, None
if source == "Sample capture":
    name = st.selectbox(
        "Scenario",
        list(LABELS),
        format_func=lambda n: f"{n.replace('_', ' ')}: {LABELS[n]['note']}",
    )
    path, expected = CAPTURES / f"{name}.pcap", LABELS[name]
else:
    upload = st.file_uploader("pcap / pcapng (UDP SIP and RTP)", type=["pcap", "pcapng", "cap"])
    st.caption("Tip: `tcpdump -i any -w call.pcap udp port 5060 or udp portrange 10000-20000`")
    if upload is not None:
        if upload.size > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"Please upload a capture under {MAX_UPLOAD_MB} MB.")
            st.stop()
        tmp = Path(tempfile.mkdtemp(prefix="sipdoc-demo-")) / "upload.pcap"
        tmp.write_bytes(upload.getvalue())
        path, name = tmp, upload.name

if path is None:
    st.info("Choose a sample or upload a capture to start.")
    st.stop()

try:
    report, parsed = analyze_capture(path, source_name=name)
except CaptureError as exc:
    st.error(f"Couldn't read that file: {exc}")
    st.stop()
finally:
    if source != "Sample capture":
        path.unlink(missing_ok=True)

st.markdown(
    f"**{report.source_name}**: {report.packets} packets · {report.sip_messages} SIP messages · "
    f"{report.rtp_packets} RTP packets · {len(report.calls)} dialog(s)"
)
if not report.calls:
    st.warning("No SIP dialogs found. Only SIP over UDP is parsed in this version.")
    st.stop()

flows = {c.call_id: c for c in parsed.calls()}
tabs = st.tabs([f"{d.kind} · {d.call_id[:24]}" for d in report.calls])
for tab, diag in zip(tabs, report.calls, strict=True):
    with tab:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Outcome", diag.outcome.replace("_", " "))
        c2.metric("Final status", diag.final_status or "—")
        c3.metric("Root cause", diag.root_cause or "none")
        c4.metric("Findings", len(diag.findings))

        if diag.findings:
            st.error(diag.summary, icon="🩺")
        else:
            st.success(diag.summary, icon="✅")

        if expected is not None:
            found = sorted({f.signature for f in diag.findings})
            match = found == expected["signatures"] and diag.root_cause == expected["root_cause"]
            st.caption(
                f"{'✅ Matches' if match else '❌ Differs from'} the scenario label: expected "
                f"{', '.join(expected['signatures']) or 'no findings'}"
            )

        left, right = st.columns([3, 2], gap="large")
        with left:
            st.subheader("SIP ladder")
            flow = flows[diag.call_id]
            render_mermaid(ladder_mermaid(flow), len(flow.messages) + len(flow.streams))
            with st.expander("Text ladder"):
                st.code(ladder_text(flow), language=None)
        with right:
            st.subheader("Findings")
            if not diag.findings:
                st.caption("No faults detected.")
            for f in diag.findings:
                with st.expander(f"{SEVERITY[f.severity]} [{f.id}] {f.title}", expanded=True):
                    st.markdown(f.detail)
                    st.dataframe(
                        pd.DataFrame([{"Evidence": e.ref, "Fact": e.fact} for e in f.evidence]),
                        hide_index=True,
                        width="stretch",
                    )
            if diag.next_steps:
                st.subheader("Next steps")
                st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(diag.next_steps, 1)))

        if diag.rtp_streams:
            st.subheader("RTP streams")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "SSRC": s.ssrc,
                            "From": f"{s.src_ip}:{s.src_port}",
                            "To": f"{s.dst_ip}:{s.dst_port}",
                            "Packets": s.packets,
                            "Loss %": s.loss_pct,
                            "Jitter ms": s.jitter_ms,
                            "MOS (est.)": s.estimated_mos,
                        }
                        for s in diag.rtp_streams
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption("MOS is a simplified E-model estimate assuming zero one-way latency.")
