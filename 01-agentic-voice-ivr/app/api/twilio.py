"""Twilio Programmable Voice channel: webhooks that return TwiML.

Status: SIMULATED. Request/response shapes and signature validation follow Twilio's published
webhook contract and are covered by tests; live validation needs a Twilio number pointed at a
public URL (see README, "Connecting a real phone number").
"""

from __future__ import annotations

import base64
import hmac
from html import escape
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.service import CallEnded, CallNotFound

router = APIRouter(prefix="/voice/twilio", tags=["voice: twilio"])
GATHER_PATH = "/voice/twilio/gather"
SPEECH_HINTS = "balance, outage, technician, appointment, agent, representative"


def compute_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Twilio's algorithm: URL + each POST param (sorted by key) as key+value, HMAC-SHA1."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), "sha1").digest()
    return base64.b64encode(digest).decode()


def _signed_url(request: Request) -> str:
    base = request.app.state.settings.public_base_url.rstrip("/")
    if not base:
        return str(request.url)
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{base}{request.url.path}{query}"


async def _validated_form(request: Request) -> dict[str, str]:
    form = {k: str(v) for k, v in (await request.form()).items()}
    settings = request.app.state.settings
    if settings.twilio_validate_signature:
        token = settings.twilio_auth_token.get_secret_value()
        expected = compute_signature(_signed_url(request), form, token)
        provided = request.headers.get("x-twilio-signature", "")
        if not token or not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=403, detail="invalid_twilio_signature")
    return form


def build_twiml(state: dict[str, Any], voice: str) -> str:
    say = f'<Say voice="{escape(voice)}">{escape(state["response"])}</Say>'
    if state["status"] == "in_progress":
        body = (
            f'<Gather input="speech dtmf" action="{GATHER_PATH}" method="POST" '
            f'speechTimeout="auto" timeout="6" language="en-US" '
            f'hints="{SPEECH_HINTS}">{say}</Gather>'
            # No input: Twilio falls through to Redirect, which posts an empty turn.
            f'<Redirect method="POST">{GATHER_PATH}</Redirect>'
        )
    elif state["status"] == "escalated":
        queue = escape((state.get("handoff") or {}).get("queue", "general"))
        body = f"{say}<Enqueue>{queue}</Enqueue>"
    else:
        body = f"{say}<Hangup/>"
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


@router.post("/incoming", summary="Twilio voice webhook: new inbound call")
async def incoming(request: Request) -> Response:
    form = await _validated_form(request)
    service = request.app.state.service
    call_sid = form.get("CallSid") or None
    state = await run_in_threadpool(service.start_call, "twilio", call_sid)
    return _twiml(build_twiml(state, request.app.state.settings.tts_voice))


@router.post("/gather", summary="Twilio Gather action: one caller turn (speech or DTMF)")
async def gather(request: Request) -> Response:
    form = await _validated_form(request)
    service = request.app.state.service
    voice = request.app.state.settings.tts_voice
    utterance = form.get("SpeechResult") or form.get("Digits") or ""
    try:
        # Twilio marks retries of the same webhook with this header; replay instead of re-running.
        token = request.headers.get("i-twilio-idempotency-token") or None
        state = await run_in_threadpool(
            service.take_turn, form.get("CallSid", ""), utterance, token
        )
    except (CallNotFound, CallEnded):
        return _twiml(
            build_twiml(
                {
                    "status": "completed",
                    "response": "Sorry, this session has ended. Please call again.",
                },
                voice,
            )
        )
    return _twiml(build_twiml(state, voice))
