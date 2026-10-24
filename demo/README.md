# Interactive demo

A Streamlit app that runs projects **01 (Agentic Voice IVR)** and **02 (SIP Call Doctor)** live in the browser. Everything runs in-process on synthetic data: no API keys, no cloud accounts, no real calls.

| Page | What you can do |
|---|---|
| **Agentic Voice IVR** | Call a fictional ISP by typing as a caller. Watch the agent's state, tool audit trail and warm-transfer packet update every turn. |
| **SIP Call Doctor** | Pick one of 10 labeled sample captures or upload your own `.pcap`. See the SIP ladder diagram, packet-cited findings, root cause, next steps and RTP statistics. |

## Run locally

```powershell
cd Agentic-Voice-AI
python -m venv .venv-demo
.venv-demo\Scripts\activate          # macOS/Linux: source .venv-demo/bin/activate
pip install -r demo/requirements.txt
streamlit run demo/streamlit_app.py
```

It opens at http://localhost:8501.

## Publish a free public link (Streamlit Community Cloud)

1. Push the repo to GitHub (it must be public for the free tier).
2. Sign in at https://share.streamlit.io with GitHub and choose **Create app** → **Deploy a public app from GitHub**.
3. Repository `MarshalTakavinga/Agentic-Voice-AI`, branch `main`, main file path `demo/streamlit_app.py`.
4. Under **Advanced settings**, choose Python **3.13**.
5. Deploy, then put the resulting `*.streamlit.app` link at the top of the repo README and your profile.

Free apps go to sleep after a period without visitors and wake up in under a minute on the next visit.

## How it's built

* The app adds `01-agentic-voice-ivr/` and `02-sip-call-doctor/` to `sys.path` and calls their code directly. It doesn't use a separate copy, so the demo always reflects the tested code.
* Each browser session gets its own IVR service and call state.
* Uploaded captures go to a temporary file that is deleted right after analysis.
* SIP ladders are rendered with Mermaid in the browser; a plain-text ladder is always available underneath.

## Tests

```bash
pytest demo/tests
```

Headless tests drive the real app with Streamlit's `AppTest`. They complete a full verified balance call, trigger an escalation, and check that every sample capture's diagnosis matches its label. The `demo` workflow runs these, boots the server, and audits dependencies on every change.
