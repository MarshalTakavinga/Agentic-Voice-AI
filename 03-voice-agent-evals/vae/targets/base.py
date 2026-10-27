from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TargetError(Exception):
    """The target failed to answer (transport error, timeout, 5xx, malformed response)."""


class CallEndedError(TargetError):
    """The target refused a turn because the call already ended."""


class TurnView(BaseModel):
    """The agent's externally visible state after one turn."""

    model_config = ConfigDict(extra="ignore")

    call_id: str
    status: str
    reply: str
    turn: int = 0
    intent: str | None = None
    nlu_source: str | None = None
    expecting: str | None = None
    authenticated: bool = False
    awaiting_confirmation: bool = False
    completed_tasks: list[str] = Field(default_factory=list)
    handoff: dict[str, Any] | None = None


class ToolEvent(BaseModel):
    """One entry of the agent's tool audit trail."""

    model_config = ConfigDict(extra="ignore")

    turn: int
    tool: str
    ok: bool
    error: str | None = None


class ToolInfo(BaseModel):
    """A tool's policy flags, as published by the agent's catalog."""

    model_config = ConfigDict(extra="ignore")

    name: str
    requires_auth: bool = False
    side_effect: bool = False


class Target(Protocol):
    name: str

    async def catalog(self) -> list[ToolInfo]: ...
    async def start_call(self) -> TurnView: ...
    async def send_turn(self, call_id: str, text: str) -> TurnView: ...
    async def tool_events(self, call_id: str) -> list[ToolEvent]: ...
    async def metrics_text(self) -> str | None: ...
    async def aclose(self) -> None: ...
