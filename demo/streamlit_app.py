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

# Streamlit hot-reloads files under demo/ after a git push, but keeps already-imported project
# packages (01's `app`, 02's `sipdoc`) in memory. If their source changed, drop them so the next
# import loads the new code; otherwise new pages would call old code until a manual reboot.
PROJECT_PACKAGES = {"app": ROOT / "01-agentic-voice-ivr" / "app", "sipdoc": ROOT / "02-sip-call-doctor" / "sipdoc"}


def _source_fingerprint() -> tuple:
    return tuple((str(f), f.stat().st_mtime_ns) for pkg in PROJECT_PACKAGES.values() for f in sorted(pkg.rglob("*.py")))


@st.cache_resource
def _loaded_code() -> dict:
    # None on the first run of this script in a process: anything of ours already imported by an
    # earlier version of the app is treated as stale.
    return {"fingerprint": None}


_current = _source_fingerprint()
if _loaded_code()["fingerprint"] != _current:
    from prometheus_client import REGISTRY

    for collector in list(REGISTRY._collector_to_names):  # metrics re-register on import
        if any(n.startswith(("ivr_", "sipdoc_")) for n in REGISTRY._collector_to_names[collector]):
            REGISTRY.unregister(collector)
    for name in [m for m in sys.modules if m.split(".")[0] in PROJECT_PACKAGES]:
        del sys.modules[name]
    st.cache_resource.clear()
    _loaded_code()["fingerprint"] = _current
if st.session_state.get("code_fingerprint") != _current:
    for key in [k for k in st.session_state if k.startswith("ivr_") and k != "ivr_mode"]:
        del st.session_state[key]  # the call was built from old code; start a fresh one
    st.session_state.code_fingerprint = _current

HERE = Path(__file__).resolve().parent
nav = st.navigation(
    [
        st.Page(HERE / "views" / "home.py", title="Overview", icon="🏠", default=True),
        st.Page(HERE / "views" / "ivr.py", title="Agentic Voice IVR", icon="📞"),
        st.Page(HERE / "views" / "sip_doctor.py", title="SIP Call Doctor", icon="🩺"),
    ]
)
nav.run()
