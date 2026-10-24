"""Interactive call simulator for project 01."""

import pandas as pd
import streamlit as st

from app.config import Settings
from app.main import create_app

TEST_ACCOUNTS = pd.DataFrame(
    [
        {"Account": "10000001", "PIN": "1234", "Name": "Ava", "ZIP": "73301", "Note": "Active outage in her area"},
        {"Account": "10000002", "PIN": "4321", "Name": "Ben", "ZIP": "60614", "Note": "No outage"},
        {"Account": "10000099", "PIN": "9999", "Name": "Fault", "ZIP": "98101", "Note": "Billing system times out"},
    ]
)
QUICK = {
    "💳 Balance": "what's my balance",
    "📡 Outage": "is there an outage in my area",
    "🔧 Technician": "I need a technician",
    "🙋 Human": "let me talk to a person",
}


def service():
    if "ivr_service" not in st.session_state:
        st.session_state.ivr_service = create_app(Settings(log_level="WARNING")).state.service
    return st.session_state.ivr_service


def new_call() -> None:
    state = service().start_call("demo")
    st.session_state.ivr_call_id = state["call_id"]
    st.session_state.ivr_transcript = [("assistant", state["response"])]


def say(text: str) -> None:
    call_id = st.session_state.ivr_call_id
    if service().get(call_id)["status"] != "in_progress":
        return
    state = service().take_turn(call_id, text)
    st.session_state.ivr_transcript += [("user", text or "(silence)"), ("assistant", state["response"])]


if "ivr_call_id" not in st.session_state:
    new_call()

st.title("📞 Agentic Voice IVR")
st.caption(
    "You're calling Northwind Fiber, a fictional ISP. Type as a caller would speak, or key digits. "
    "Rules-based NLU and mock enterprise systems; synthetic data only."
)

with st.sidebar:
    st.subheader("Test accounts")
    st.dataframe(TEST_ACCOUNTS, hide_index=True, width="stretch")
    st.caption("Keypad menu: 1 balance · 2 outage · 3 technician · 0 agent")
    if st.button("📞 Hang up and call again", width="stretch"):
        new_call()
        st.rerun()
    st.subheader("Things to try")
    st.markdown(
        "- Say the account as words: *one zero zero zero zero zero zero one*\n"
        "- Give account and PIN together\n"
        "- Book a technician, say *no*, then *how about friday*\n"
        "- Change your mind mid-flow\n"
        "- Get the PIN wrong three times\n"
        "- Use the fault account to see a graceful failure"
    )

state = service().get(st.session_state.ivr_call_id)
chat_col, state_col = st.columns([3, 2], gap="large")

with chat_col:
    for role, text in st.session_state.ivr_transcript:
        with st.chat_message(role, avatar="🤖" if role == "assistant" else "🧑"):
            st.markdown(text)

    if state["status"] == "in_progress":
        cols = st.columns(len(QUICK))
        for col, (label, utterance) in zip(cols, QUICK.items(), strict=True):
            if col.button(label, width="stretch"):
                say(utterance)
                st.rerun()
        if prompt := st.chat_input("Say something to the IVR…"):
            say(prompt)
            st.rerun()
    elif state["status"] == "escalated":
        handoff = state.get("handoff") or {}
        st.warning(
            f"Call transferred to the **{handoff.get('queue', 'general')}** queue "
            f"(reason: `{handoff.get('reason')}`). Start a new call from the sidebar."
        )
    else:
        st.success("Call ended. Start a new call from the sidebar.")

with state_col:
    st.subheader("Agent state")
    m1, m2 = st.columns(2)
    m1.metric("Last intent", (state.get("nlu") or {}).get("intent") or "—")
    m2.metric("Collecting", state.get("expecting") or "—")
    m3, m4 = st.columns(2)
    m3.metric("Verified", "Yes" if state.get("authenticated") else "No")
    m4.metric("Call status", state["status"].replace("_", " "))
    if state.get("pending_action"):
        st.info(f"Awaiting consent to book: **{state['pending_action']['label']}**")
    st.markdown("**Tasks completed:** " + (", ".join(f"`{t}`" for t in state.get("completed_tasks", [])) or "none yet"))

    st.subheader("Tool audit trail")
    events = state.get("events", [])
    if events:
        st.dataframe(pd.DataFrame(events), hide_index=True, width="stretch")
    else:
        st.caption("No tools called yet.")
    st.caption(
        "Tool names and outcomes only. Arguments such as account numbers and PINs are never "
        "recorded, and credentials are removed from state as soon as they're verified."
    )
    if state.get("handoff"):
        st.subheader("Warm-transfer packet")
        st.json(state["handoff"])
