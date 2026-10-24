"""A scripted stand-in for the Claude Messages API, returning responses in the real format."""

from __future__ import annotations

import itertools
from typing import Any

_ids = itertools.count(1)


def tool_use(name: str, **inputs: Any) -> dict:
    return {"type": "tool_use", "id": f"toolu_{next(_ids):04d}", "name": name, "input": inputs}


def text(value: str) -> dict:
    return {"type": "text", "text": value}


class FakeClaude:
    """Returns one scripted response per create() call. Each script entry is a list of content
    blocks. Records every request so tests can inspect what the model was shown."""

    model = "claude-haiku-5-5"

    def __init__(
        self, *script: list[dict], usage: dict | None = None, error: Exception | None = None
    ):
        self.script = list(script)
        self.requests: list[dict] = []
        self.usage = usage or {"input_tokens": 900, "output_tokens": 40}
        self.error = error

    def create(self, *, system, tools, messages, max_tokens):
        self.requests.append(
            {"system": system, "tools": tools, "messages": messages, "max_tokens": max_tokens}
        )
        if self.error:
            raise self.error
        blocks = (
            self.script.pop(0)
            if self.script
            else [text("I can help with balances, outages and visits.")]
        )
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        return {
            "type": "message",
            "role": "assistant",
            "content": blocks,
            "stop_reason": stop,
            "usage": self.usage,
        }

    def sent_text(self) -> str:
        """Everything the model was shown, flattened, for redaction checks."""
        out = []
        for r in self.requests:
            for m in r["messages"]:
                out.append(m["content"] if isinstance(m["content"], str) else str(m["content"]))
        return "\n".join(out)
