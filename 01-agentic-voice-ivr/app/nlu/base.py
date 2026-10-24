"""NLU contract plus deterministic normalization and entity extraction.

Design rule: LLMs may classify intent; identifiers (account numbers, PINs, ZIP codes) are
always extracted deterministically. A model must never be the source of an account number.
"""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, Field

Intent = Literal[
    "check_balance",
    "check_outage",
    "schedule_technician",
    "agent",
    "goodbye",
    "affirm",
    "deny",
    "help",
    "provide_info",
    "no_match",
]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]
Slot = Literal["account_number", "pin", "zip"]


class NLUResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    entities: dict[str, str] = Field(default_factory=dict)
    source: str = "rules"


class NLUProvider(Protocol):
    name: str

    def parse(self, utterance: str, expecting: str | None = None) -> NLUResult: ...


_WORD_DIGITS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_WORD_RE = re.compile(r"\b(" + "|".join(_WORD_DIGITS) + r")\b")
_JOIN_DIGITS = re.compile(r"(?<=\d)[\s,.\-]+(?=\d)")
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_EARLIEST = re.compile(r"\b(earliest|soonest|asap|as soon as possible|first available)\b")


def normalize(utterance: str) -> str:
    """Lowercase, map spoken digits to numerals, and join digit groups ("1 2 3 4" -> "1234")."""
    text = _WORD_RE.sub(lambda m: _WORD_DIGITS[m.group(1)], utterance.lower().strip())
    return _JOIN_DIGITS.sub("", text)


def extract_entities(text: str, expecting: str | None) -> dict[str, str]:
    entities: dict[str, str] = {}
    for run in re.findall(r"\d+", text):
        if len(run) == 8:
            entities["account_number"] = run
        elif len(run) == 5:
            entities["zip"] = run
        elif len(run) == 4 and (expecting in ("pin", "account_number") or "pin" in text):
            entities["pin"] = run
    for day in (*_DAYS, "tomorrow", "today"):
        if re.search(rf"\b{day}\b", text):
            entities["preferred_day"] = day
            break
    else:
        if _EARLIEST.search(text):
            entities["preferred_day"] = "earliest"
    return entities
