import streamlit as st

REPO = "https://github.com/MarshalTakavinga/Agentic-Voice-AI"

st.title("Agentic Voice AI")
st.markdown("#### AI agents that are safe to put on a phone line, and the tooling to debug the phone line too.")
st.markdown(
    "This demo runs two projects from the portfolio live in your browser. Both use "
    "**synthetic data only**; no real customers, calls or accounts are involved."
)

left, right = st.columns(2, gap="large")
with left, st.container(border=True):
    st.subheader("📞 Agentic Voice IVR")
    st.markdown(
        "**Call it with your voice** (or type). Dial a fictional fiber ISP: the agent verifies you, "
        "checks balances and outages, "
        "books technicians with explicit consent, and hands off to a human with context.\n\n"
        "**Watch for:** the live state panel and tool audit trail. Every guardrail "
        "(authentication, customer binding, consent) is enforced in code, not in the prompt. "
        "When enabled, Claude handles messy requests the rules can't map, with its cost shown per turn."
    )
    st.page_link("views/ivr.py", label="Open the IVR demo", icon="➡️")

with right, st.container(border=True):
    st.subheader("🩺 SIP Call Doctor")
    st.markdown(
        "Pick a sample capture or upload your own `.pcap`. Get a SIP ladder diagram, findings "
        "tied to the exact packets that prove them, a root cause, and runbook steps.\n\n"
        "**Watch for:** every claim cites a finding ID, and every finding cites packet evidence."
    )
    st.page_link("views/sip_doctor.py", label="Open the SIP Call Doctor demo", icon="➡️")

st.divider()
st.markdown("##### The portfolio")
st.markdown(
    "Ten projects on AI in VoIP and contact centers. The demo shows the ones that are built; "
    "the others have a specification in the repo and appear here as they ship."
)
PROJECTS = [
    (
        "01",
        "Agentic Voice IVR",
        "Verifies callers, completes multi-step requests through guarded tools, warm-transfers",
        "✅ Milestones 1–3",
        "views/ivr.py",
    ),
    (
        "02",
        "SIP Call Doctor",
        "Diagnoses one-way audio, NAT, codec and quality faults from packet captures",
        "✅ Milestone 1",
        "views/sip_doctor.py",
    ),
    ("03", "Voice Agent Evals", "Regression and load testing for voice agents", "Planned", None),
    ("04", "Contact Center Copilot", "Real-time agent assist with permission-aware cited RAG", "Planned", None),
    ("05", "Voice PII Guard", "Redacts PII across audio, transcripts, logs and LLM tool payloads", "Planned", None),
    (
        "06",
        "Contact Center Tool Gateway",
        "MCP server for CRM/ACD actions with scopes, consent and audit",
        "Planned",
        None,
    ),
    ("07", "Voice Agent Orchestrator", "Supervisor and specialist agents with least-privilege tools", "Planned", None),
    ("08", "IVR Modernizer", "Converts DTMF/VoiceXML trees into conversational flows", "Planned", None),
    ("09", "VoIP Quality Sentinel", "Anomaly detection on MOS, jitter, loss and PDD", "Planned", None),
    ("10", "Smart Call Router", "Explainable routing evaluated in a discrete-event simulator", "Planned", None),
]
for num, name, what, status, page in PROJECTS:
    c_name, c_what, c_status = st.columns([3, 6, 2], vertical_alignment="center")
    if page:
        c_name.page_link(page, label=f"{num} · {name}")
    else:
        c_name.markdown(f"{num} · {name}")
    c_what.caption(what)
    c_status.markdown(f"**{status}**" if status.startswith("✅") else status)

st.divider()
st.markdown("##### Design principles")
c1, c2, c3 = st.columns(3)
c1.markdown("**Guardrails in code, not prompts.** Models propose; code decides.")
c2.markdown("**Measure deterministically, explain with AI.** No invented numbers.")
c3.markdown("**Honest engineering.** Simulated integrations are labeled as simulated.")

st.caption(
    f"Source, tests and CI: [{REPO.removeprefix('https://')}]({REPO}). "
    "The IVR runs on deterministic rules unless a Claude key is configured; the SIP narrator is deterministic."
)
