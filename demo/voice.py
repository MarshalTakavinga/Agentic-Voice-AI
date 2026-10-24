"""Speech in and speech out for the demo's voice-call mode.

Speech-to-text: faster-whisper running on the server (free, no API key). The model downloads
from Hugging Face on first use and is cached for the life of the app.
Text-to-speech: edge-tts neural voices; if that service is unreachable, the page falls back to
the browser's built-in speech synthesis.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import wave

import numpy as np
import streamlit as st

STT_MODEL = os.environ.get("DEMO_STT_MODEL", "base.en")
TTS_VOICE = os.environ.get("DEMO_TTS_VOICE", "en-US-AriaNeural")
# Biases recognition toward this IVR's vocabulary (balance, outage, account numbers, ...).
HOTWORDS = (
    "Northwind Fiber balance outage technician appointment agent representative account "
    "number PIN yes no Monday Tuesday Wednesday Thursday Friday"
)


class SpeechUnavailable(RuntimeError):
    pass


@st.cache_resource(show_spinner="Loading the speech recognizer (first call only, ~30 s)…")
def _load_stt():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise SpeechUnavailable("faster-whisper is not installed") from exc
    return WhisperModel(STT_MODEL, device="cpu", compute_type="int8")


WHISPER_RATE = 16_000


def wav_to_whisper(audio: bytes) -> np.ndarray:
    """Decode a PCM WAV recording (what st.audio_input produces) to 16 kHz mono float32.

    Done here with the standard library so recordings don't depend on PyAV/FFmpeg versions.
    """
    with wave.open(io.BytesIO(audio)) as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported WAV sample width: {width} bytes")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != WHISPER_RATE and samples.size:
        duration = samples.size / rate
        target = np.linspace(0.0, duration, int(duration * WHISPER_RATE), endpoint=False)
        samples = np.interp(target, np.arange(samples.size) / rate, samples).astype(np.float32)
    return samples


def transcribe(audio: bytes, model=None) -> str:
    """Return the caller's words, or "" for silence/noise (the IVR then reprompts)."""
    if not audio:
        return ""
    samples = wav_to_whisper(audio)
    if samples.size < WHISPER_RATE // 4:  # under 250 ms: nothing was said
        return ""
    model = model or _load_stt()
    segments, _info = model.transcribe(
        samples,
        language="en",
        beam_size=1,
        vad_filter=True,  # drop silence so Whisper doesn't hallucinate words
        condition_on_previous_text=False,
        hotwords=HOTWORDS,
    )
    return " ".join(s.text.strip() for s in segments).strip()


async def _edge_tts(text: str, voice: str) -> bytes:
    import edge_tts

    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


@st.cache_data(max_entries=512, show_spinner=False)
def synthesize(text: str, voice: str = TTS_VOICE) -> bytes | None:
    """MP3 bytes for the IVR's reply, or None when the TTS service can't be reached."""
    try:
        audio = asyncio.run(asyncio.wait_for(_edge_tts(text, voice), timeout=15))
    except Exception:  # noqa: BLE001 - any failure falls back to browser speech
        return None
    return audio or None


def browser_speech(text: str) -> str:
    """HTML for a fallback 'speak' button using the browser's Web Speech API."""
    js_text = json.dumps(text).replace("</", "<\\/")  # safe inside a <script> block
    return f"""
    <button id="say" style="font:14px sans-serif;padding:6px 14px;border-radius:8px;
            border:1px solid #ccc;background:#fff;cursor:pointer">🔊 Play reply</button>
    <script>
      const text = {js_text};
      function speak() {{
        const u = new SpeechSynthesisUtterance(text);
        u.lang = "en-US";
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
      }}
      document.getElementById("say").onclick = speak;
      try {{ speak(); }} catch (e) {{}}
    </script>"""
