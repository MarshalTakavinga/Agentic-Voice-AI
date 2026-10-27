"""Evaluation UI for project 03: run the black-box suite against the IVR, try the noise engine."""

import asyncio
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from app.config import Settings
from app.main import create_app
from vae import metrics, report
from vae.noise import PROFILES, _rng
from vae.runner import run_suite
from vae.scenario import load_suite
from vae.targets.http import HttpTarget

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "03-voice-agent-evals" / "suites" / "ivr"
REPO = "https://github.com/MarshalTakavinga/Agentic-Voice-AI/blob/main/03-voice-agent-evals"
KEY = "demo-eval-key"


def _ivr_settings() -> Settings:
    # Pinned to the free rules NLU: visitors running the suite never spend LLM budget.
    return Settings(
        api_key=KEY,
        env="test",
        log_level="WARNING",
        nlu_provider="rules",
        planner_enabled=False,
        anthropic_api_key="",
        state_backend="memory",
    )


def run_evaluation(full: bool):
    suite = load_suite(SUITE)

    def factory() -> HttpTarget:
        return HttpTarget(app=create_app(_ivr_settings()), api_key=KEY, name="01-agentic-voice-ivr (in-process)")

    res = asyncio.run(run_suite(suite, factory(), profiles=None if full else [], concurrency=4, target_factory=factory))
    res.summary = metrics.summarize(res)
    res.gates = metrics.evaluate_gates(res.summary, suite.gates)
    return res


def pct(v) -> str:
    return "–" if v is None else f"{v:.0%}"


st.title("🧪 Voice Agent Evals")
st.caption(
    "Project 03 · drives the IVR through scripted calls from the outside, rewrites them the way speech "
    f"recognition garbles them, and checks every tool call against the IVR's published policy. [Source]({REPO})"
)

st.markdown("##### Run the suite against the IVR")
mode = st.radio(
    "Suite",
    ["Quick: 14 scenarios + 8 prompt-injection attacks (22 calls)", "Full: plus 89 ASR-noise variants (111 calls)"],
    label_visibility="collapsed",
)
st.caption(
    "Every call gets a fresh IVR, so lockouts and bookings in one scenario can't change another's outcome. "
    "Synthetic accounts only; runs on the free rules NLU."
)
if st.button("Run evaluation", type="primary"):
    with st.spinner("Calling the IVR…"):
        started = time.perf_counter()
        st.session_state.evals_result = run_evaluation(full=mode.startswith("Full"))
        st.session_state.evals_seconds = time.perf_counter() - started

res = st.session_state.get("evals_result")
if res is not None:
    s = res.summary
    passed = metrics.gates_passed(res.gates)
    (st.success if passed else st.error)(
        f"Gates {'passed' if passed else 'failed'} · {s['passed']} of {s['runs']} calls passed · "
        f"{st.session_state.evals_seconds:.1f} s"
    )
    c = st.columns(5)
    c[0].metric("Clean + injection", pct(s["pass_rate"]))
    c[1].metric("Benign noise", pct(s["benign_robustness"]))
    c[2].metric("Corrupted IDs stay safe", pct(s["corrupting_safety"]))
    c[3].metric("Unauthorized tool calls", s["unauthorized_tool_calls"])
    c[4].metric("p95 turn (ms)", f"{s['latency']['p95_ms']:.0f}")

    left, right = st.columns(2)
    with left:
        st.markdown("**Gates**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Gate": g["gate"], "Threshold": g["threshold"], "Measured": g["actual"], "Result": g["result"]}
                    for g in res.gates
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with right:
        st.markdown("**By category**")
        st.dataframe(
            pd.DataFrame(
                [{"Category": k, "Passed": v["passed"], "Runs": v["runs"]} for k, v in s["categories"].items()]
            ),
            hide_index=True,
            width="stretch",
        )
    if s["profiles"]:
        st.markdown("**ASR-noise profiles**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Profile": k, "Class": v["category"], "Passed": v["passed"], "Runs": v["runs"]}
                    for k, v in s["profiles"].items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    tools = res.server_latency.get("tools") or {}
    if tools:
        st.markdown("**Where the time goes (IVR's own Prometheus histograms)**")
        st.dataframe(
            pd.DataFrame([{"Tool": k, "Calls": v["count"], "Mean ms": v["mean_ms"]} for k, v in tools.items()]),
            hide_index=True,
            width="stretch",
        )
        st.caption("verify_caller dominates: the mock hashes PINs with PBKDF2 at 100k iterations, on purpose.")
    failed = [r for r in res.results if not r.passed]
    if failed:
        st.markdown(f"**Failures ({len(failed)})**")
        for r in failed[:20]:
            with st.expander(r.id):
                st.write(r.failures)
    st.download_button("Download the Markdown report", report.render(res), file_name="ivr-eval-report.md")

st.divider()
st.markdown("##### Try the noise engine")
text = st.text_input("Something a caller might say", "my account number is 10000002 and my pin is 4321")
if text:
    st.dataframe(
        pd.DataFrame(
            [
                {"Profile": p.name, "Class": p.category, "Recognizer might return": p.fn(text, _rng(7, "demo", p.name))}
                for p in PROFILES.values()
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Benign variants must still succeed. Corrupting variants garble the identifier itself, so they must "
        "fail safely: no verification, nothing only a verified caller may hear."
    )

st.divider()
st.markdown("##### What it found on its first run")
st.markdown(
    "The IVR passed all of its own tests. From the outside, the noise variants found that it did not "
    'understand "oh" for zero, lost digits and a "yes" when callers hesitated, and missed homophones '
    'like "for three to won". After a fix to its speech normalizer:'
)
st.dataframe(
    pd.DataFrame(
        [
            {"Measure": "Benign ASR-noise robustness", "Before": "75.4%", "After": "100%"},
            {"Measure": "Stress robustness (homophones, grouping)", "Before": "37.5%", "After": "100%"},
            {"Measure": '"oh" for zero', "Before": "0 of 10", "After": "10 of 10"},
        ]
    ),
    hide_index=True,
    width="stretch",
)
st.markdown(
    f"[Report before the fix]({REPO}/reports/ivr-report-before-normalizer-fix.md) · "
    f"[Current report]({REPO}/reports/ivr-report.md)"
)
