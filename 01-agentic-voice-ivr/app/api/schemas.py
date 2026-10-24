from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StartCallRequest(BaseModel):
    channel: Literal["api", "simulator"] = "api"


class TurnRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"text": "what's my balance"}]})
    text: str = Field(
        default="",
        max_length=500,
        description="Caller utterance as transcribed by ASR, or DTMF digits.",
    )


class CallView(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "call_id": "CA3f2c...",
                    "status": "in_progress",
                    "reply": "Thanks, Ava, you're verified. Your current balance is $89.99, due on "
                    "November 9. Is there anything else I can help you with?",
                    "turn": 3,
                    "intent": "provide_info",
                    "nlu_source": "rules",
                    "expecting": None,
                    "active_intent": None,
                    "authenticated": True,
                    "awaiting_confirmation": False,
                    "completed_tasks": ["check_balance"],
                    "handoff": None,
                }
            ]
        }
    )
    call_id: str
    status: Literal["in_progress", "completed", "escalated"]
    reply: str
    turn: int
    intent: str | None
    nlu_source: str | None
    expecting: str | None
    active_intent: str | None
    authenticated: bool
    awaiting_confirmation: bool
    completed_tasks: list[str]
    handoff: dict[str, Any] | None


class CallDetail(CallView):
    events: list[dict[str, Any]]


class ErrorResponse(BaseModel):
    error: str
    request_id: str | None = None
