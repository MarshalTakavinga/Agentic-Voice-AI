"""Headless UI tests using Streamlit's AppTest, plus unit tests for the voice helpers."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

DEMO = Path(__file__).resolve().parent.parent
APP = str(DEMO / "streamlit_app.py")
sys.path.insert(0, str(DEMO))

import voice  # noqa: E402

REAL_SYNTHESIZE = voice.synthesize  # captured before the autouse stub replaces it

FAKE_MP3 = b"ID3\x04\x00fake-mp3"


@pytest.fixture(autouse=True)
def stub_speech(monkeypatch):
    """No network or model downloads in tests: speech in/out are stubbed."""
    spoken = []
    monkeypatch.setattr(voice, "synthesize", lambda text, voice=None: spoken.append(text) or FAKE_MP3)
    return spoken


def _page(page: str, **state) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    at.switch_page(f"views/{page}.py").run()
    assert not at.exception, at.exception
    return at


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


# ------------------------------------------------------------------ overview
def test_home_renders():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Agentic Voice AI" in t.value for t in at.title)


# ------------------------------------------------------------------ IVR: voice mode
def test_voice_call_dial_and_greeting_is_spoken(stub_speech):
    at = _page("ivr")
    _button(at, "📞 Call Northwind Fiber").click().run()
    assert not at.exception, at.exception
    assert "Northwind Fiber" in at.chat_message[0].markdown[0].value
    assert stub_speech and "Northwind Fiber" in stub_speech[0]  # greeting sent to TTS


def test_voice_call_keypad_menu_and_pin(stub_speech):
    at = _page("ivr")
    _button(at, "📞 Call Northwind Fiber").click().run()
    for key in ["1", "#", "1", "0", "0", "0", "0", "0", "0", "1", "#", "1", "2", "3", "4", "#"]:
        _button(at, key).click().run()
        assert not at.exception, at.exception
    assert "$89.99" in at.chat_message[-1].markdown[0].value
    assert any(m.label == "Verified" and m.value == "Yes" for m in at.metric)
    assert "$89.99" in stub_speech[-1]  # the answer is spoken, not just shown


def test_keypad_star_clears_buffer():
    at = _page("ivr")
    _button(at, "📞 Call Northwind Fiber").click().run()
    _button(at, "9").click().run()
    _button(at, "*").click().run()
    _button(at, "#").click().run()  # empty input -> the IVR reprompts
    assert "didn't catch" in at.chat_message[-1].markdown[0].value


def test_hang_up_returns_to_dial_screen():
    at = _page("ivr")
    _button(at, "📞 Call Northwind Fiber").click().run()
    _button(at, "📴 Hang up").click().run()
    assert any(b.label == "📞 Call Northwind Fiber" for b in at.button)


# ------------------------------------------------------------------ IVR: text mode
def test_text_chat_full_balance_call():
    at = _page("ivr", ivr_mode="⌨️ Text chat")
    for text in ["what's my balance", "10000001", "1234"]:
        at.chat_input[0].set_value(text).run()
        assert not at.exception, at.exception
    assert "$89.99" in at.chat_message[-1].markdown[0].value


def test_text_chat_escalation():
    at = _page("ivr", ivr_mode="⌨️ Text chat")
    next(b for b in at.button if "Human" in b.label).click().run()
    assert any("transferred" in w.value for w in at.warning)


# ------------------------------------------------------------------ IVR: Claude planner
def test_planner_off_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = _page("ivr", ivr_mode="⌨️ Text chat")
    assert any("rules-only" in i.value for i in at.info)


class _ScriptedClaude:
    """Stands in for AnthropicClient; no network. Returns one tool call, real response shape."""

    def __init__(self, *args, **kwargs):
        self.model = "claude-haiku-5-5"

    def create(self, *, system, tools, messages, max_tokens):
        assert "10000001" not in str(messages)  # identifiers never reach the model
        block = {"type": "tool_use", "id": "toolu_1", "name": "transfer_to_human", "input": {"reason": "upset"}}
        return {"content": [block], "usage": {"input_tokens": 1000, "output_tokens": 30}}


def test_planner_on_handles_messy_request_and_shows_cost(monkeypatch):
    import app.agent.planner as planner

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setattr(planner, "AnthropicClient", _ScriptedClaude)
    at = _page("ivr", ivr_mode="⌨️ Text chat")
    at.chat_input[0].set_value("this is ridiculous, nothing ever works").run()
    assert not at.exception, at.exception
    assert any("transferred" in w.value for w in at.warning)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Claude calls this session"] == "1"
    assert metrics["Session cost"] == "$0.0001"  # 1000 in + 30 out tokens on Haiku 5.5


# ------------------------------------------------------------------ SIP Call Doctor
def test_sip_doctor_sample_nat():
    at = _page("sip_doctor")
    at.selectbox[0].select("nat_one_way_audio").run()
    assert not at.exception, at.exception
    assert any(m.label == "Root cause" and m.value == "media_to_private_address" for m in at.metric)


def test_sip_doctor_every_sample_matches_label():
    at = _page("sip_doctor")
    for option in at.selectbox[0].options:
        at.selectbox[0].select(option).run()
        assert not at.exception, (option, at.exception)
        assert any("Matches" in c.value for c in at.caption), option


# ------------------------------------------------------------------ voice helpers
class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self, texts):
        self.texts, self.kwargs = texts, None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter(_Seg(t) for t in self.texts), None


def test_transcribe_joins_segments_and_uses_vad():
    model = _FakeModel([" one zero zero", " zero zero zero zero one "])
    assert voice.transcribe(_wav(48000, 1), model=model) == "one zero zero zero zero zero zero one"
    assert model.kwargs["vad_filter"] is True and model.kwargs["language"] == "en"
    assert "balance" in model.kwargs["hotwords"]


def test_transcribe_empty_audio_is_silence():
    assert voice.transcribe(b"", model=_FakeModel(["ignored"])) == ""


def test_tts_failure_falls_back(monkeypatch):
    async def unreachable(text, v):
        raise OSError("network unreachable")

    monkeypatch.setattr(voice, "_edge_tts", unreachable)
    REAL_SYNTHESIZE.clear()
    assert REAL_SYNTHESIZE("hello there") is None  # page then renders the browser-speech fallback


def test_browser_fallback_escapes_script():
    out = voice.browser_speech('Hi </script><img src=x onerror=alert(1)> "q"')
    assert "</script><img" not in out and "<\\/script>" in out


def _wav(rate: int, channels: int, seconds: float = 1.0, hz: float = 440.0) -> bytes:
    import io
    import wave

    import numpy as np

    t = np.arange(int(rate * seconds)) / rate
    tone = (0.3 * np.sin(2 * np.pi * hz * t) * 32767).astype("<i2")
    frames = np.repeat(tone[:, None], channels, axis=1).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


@pytest.mark.parametrize("rate,channels", [(48000, 1), (48000, 2), (44100, 1), (16000, 1)])
def test_wav_decoding_resamples_to_16k_mono(rate, channels):
    import numpy as np

    samples = voice.wav_to_whisper(_wav(rate, channels))
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert abs(samples.size - 16000) <= 1
    peak_hz = np.argmax(np.abs(np.fft.rfft(samples))) * 16000 / samples.size
    assert abs(peak_hz - 440) < 2  # the signal survives resampling intact


def test_very_short_recording_is_treated_as_silence():
    model = _FakeModel(["should not be called"])
    assert voice.transcribe(_wav(48000, 1, seconds=0.1), model=model) == ""
    assert model.kwargs is None


def test_transcribe_passes_decoded_array_not_bytes():
    import numpy as np

    model = _FakeModel(["hi"])

    def capture(audio, **kwargs):
        model.audio = audio
        return iter([_Seg("hi")]), None

    model.transcribe = capture
    assert voice.transcribe(_wav(48000, 2), model=model) == "hi"
    assert isinstance(model.audio, np.ndarray)  # PyAV is never needed for recordings
