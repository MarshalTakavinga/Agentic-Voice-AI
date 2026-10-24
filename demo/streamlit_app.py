"""Agentic Voice AI — interactive demo.

Run locally:   streamlit run demo/streamlit_app.py
Everything runs in-process on synthetic data; no API keys or cloud accounts are needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
for project in ("demo", "01-agentic-voice-ivr", "02-sip-call-doctor"):
    path = str(ROOT / project)
    if path not in sys.path:
        sys.path.insert(0, path)

st.set_page_config(page_title="Agentic Voice AI · Demo", page_icon="📞", layout="wide")

HERE = Path(__file__).resolve().parent
nav = st.navigation(
    [
        st.Page(HERE / "views" / "home.py", title="Overview", icon="🏠", default=True),
        st.Page(HERE / "views" / "ivr.py", title="Agentic Voice IVR", icon="📞"),
        st.Page(HERE / "views" / "sip_doctor.py", title="SIP Call Doctor", icon="🩺"),
    ]
)
nav.run()
