"""Channel-agnostic call service used by the JSON API, the Twilio webhook and the eval harness."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.graph import IVRAgent
from app.observability import log
from app.sessions import SessionStore


class CallNotFound(Exception):
    pass


class CallEnded(Exception):
    pass


class CallService:
    def __init__(self, agent: IVRAgent, store: SessionStore) -> None:
        self.agent = agent
        self.store = store

    def start_call(self, channel: str, call_id: str | None = None) -> dict[str, Any]:
        call_id = call_id or f"CA{uuid.uuid4().hex}"
        state = self.agent.new_state(call_id, channel)
        self.store.put(call_id, state)
        log.info("call_started", call_id=call_id, channel=channel)
        return state

    def get(self, call_id: str) -> dict[str, Any]:
        state = self.store.get(call_id)
        if state is None:
            raise CallNotFound(call_id)
        return state

    def take_turn(self, call_id: str, utterance: str) -> dict[str, Any]:
        state = self.get(call_id)
        if state["status"] != "in_progress":
            raise CallEnded(call_id)
        new_state = self.agent.handle_turn(state, utterance)
        self.store.put(call_id, new_state)
        log.info(
            "turn_completed",
            call_id=call_id,
            turn=new_state["turn"],
            intent=new_state["nlu"]["intent"],
            nlu_source=new_state["nlu"]["source"],
            status=new_state["status"],
        )
        return new_state


def public_view(state: dict[str, Any], include_events: bool = False) -> dict[str, Any]:
    """What callers of the API may see. Slot values (identifiers) are never returned."""
    nlu = state.get("nlu") or {}
    view = {
        "call_id": state["call_id"],
        "status": state["status"],
        "reply": state["response"],
        "turn": state["turn"],
        "intent": nlu.get("intent"),
        "nlu_source": nlu.get("source"),
        "expecting": state.get("expecting"),
        "active_intent": state.get("active_intent"),
        "authenticated": state.get("authenticated", False),
        "awaiting_confirmation": state.get("pending_action") is not None,
        "completed_tasks": state.get("completed_tasks", []),
        "handoff": state.get("handoff"),
    }
    if include_events:
        view["events"] = state.get("events", [])
    return view
