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
        "Call a fictional fiber ISP. The agent verifies you, checks balances and outages, "
        "books technicians with explicit consent, and hands off to a human with context.\n\n"
        "**Watch for:** the live state panel and tool audit trail. Every guardrail "
        "(authentication, customer binding, consent) is enforced in code, not in the prompt."
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
st.markdown("##### Design principles")
c1, c2, c3 = st.columns(3)
c1.markdown("**Guardrails in code, not prompts.** Models propose; code decides.")
c2.markdown("**Measure deterministically, explain with AI.** No invented numbers.")
c3.markdown("**Honest engineering.** Simulated integrations are labeled as simulated.")

st.caption(
    f"Source, tests and CI: [{REPO.removeprefix('https://')}]({REPO}). "
    "This demo uses the deterministic NLU and narrator; LLM providers are optional in the code."
)
