# Interactive demo

**Live:** [agentic-voice-ai.streamlit.app](https://agentic-voice-ai.streamlit.app)

A Streamlit app that runs projects **01 (Agentic Voice IVR)** and **02 (SIP Call Doctor)** live in the browser. Everything runs in-process on synthetic data: no API keys, no cloud accounts, no real calls.

| Page | What you can do |
|---|---|
| **Agentic Voice IVR** | **Voice call mode:** dial in, speak through your microphone, hear the agent answer, and key digits on a DTMF keypad. **Text chat mode** is also available. The agent's state, tool audit trail and warm-transfer packet update every turn. |
| **SIP Call Doctor** | Pick one of 10 labeled sample captures or upload your own `.pcap`. See the SIP ladder diagram, packet-cited findings, root cause, next steps and RTP statistics. |

## How voice mode works

| Step | Technology | Notes |
|---|---|---|
| Record a turn | `st.audio_input` (browser microphone) | Your browser asks for mic permission once. Recordings are processed in memory and not stored. |
| Speech → text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `base.en`, on the server, CPU int8 | Free, no API key. The model (~140 MB) downloads on the first call after the app wakes, which takes about 30 s; later turns take a second or two. Voice-activity detection drops silence; hotwords bias recognition toward this IVR's vocabulary. |
| IVR logic | Project 01's LangGraph agent, unchanged | The exact code that the tests and evals cover. |
| Text → speech | [edge-tts](https://github.com/rany2/edge-tts) neural voice (`en-US-AriaNeural`) | If the service can't be reached, the page uses your browser's built-in speech instead. |
| Keypad | DTMF buttons; digits collect until **#** | The same input path Twilio uses for key presses. |

Recordings are decoded with Python's standard `wave` module, so speech recognition doesn't depend on FFmpeg or PyAV versions. This is a browser simulation of a phone call. Project 01's Twilio webhooks are the path to a real phone number; see its README.

Set `DEMO_STT_MODEL=tiny.en` for faster, less accurate recognition, or `DEMO_TTS_VOICE` to change the voice.

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

Headless tests drive the real app with Streamlit's `AppTest`. They dial a voice call and complete a verified balance check on the DTMF keypad (checking that each reply goes to speech), run text-chat calls and an escalation, and check that every sample capture's diagnosis matches its label. Unit tests cover WAV decoding and resampling, silence handling, the TTS fallback and script-safe escaping. The speech model and TTS service are stubbed in tests. The `demo` workflow runs these, boots the server, and audits dependencies on every change.
