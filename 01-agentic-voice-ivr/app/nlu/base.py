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
# Hesitations recognizers pass through ("um, one two uh three four"). They carry no meaning here
# and would otherwise split a digit run or hide a leading "yes".
_FILLERS = re.compile(r"\b(?:u+m+|u+h+m*|e+r+m*|h+m+|a+h+)\b[,.]?")
# Words that are digits only in context: "oh" for zero, and recognizer homophones of digits.
_AMBIGUOUS = {"oh": "0", "won": "1", "to": "2", "too": "2", "for": "4", "fore": "4", "ate": "8"}
_DIGIT_TOKEN = r"(?:\d+|" + "|".join([*_WORD_DIGITS, *_AMBIGUOUS]) + r")"
_DIGIT_RUN = re.compile(rf"\b{_DIGIT_TOKEN}(?:[\s,.\-]+{_DIGIT_TOKEN})*\b")
_SLOT_LENGTH = {"account_number": 8, "pin": 4, "zip": 5}
_IDENTIFIER_LENGTHS = {4, 5, 8}


def _resolve_run(run: str, expecting: str | None) -> str:
    """Decide whether ambiguous words in a digit-like run are digits.

    They are read as digits only when that yields exactly the identifier length being collected
    (or, when nothing is being collected, a valid identifier length) and reading them as words
    does not. So "won to three for" is PIN 1234, while "outage for 60614" keeps ZIP 60614.
    """
    tokens = [t for t in re.split(r"[\s,.\-]+", run) if t]
    if not any(t in _AMBIGUOUS for t in tokens):
        return run
    strict = "".join(t if t.isdigit() else _WORD_DIGITS.get(t, "") for t in tokens)
    full = "".join(t if t.isdigit() else _WORD_DIGITS.get(t) or _AMBIGUOUS[t] for t in tokens)
    want = _SLOT_LENGTH.get(expecting or "")
    if want is not None:
        if len(full) == want and len(strict) != want:
            return full
        if len(strict) == want:
            return run
    if strict and len(strict) in _IDENTIFIER_LENGTHS:
        return run
    if len(full) in _IDENTIFIER_LENGTHS and (strict or want is not None):
        return full
    return run


def normalize(utterance: str, expecting: str | None = None) -> str:
    """Lowercase, drop fillers, map spoken digits (and, in context, "oh" and digit homophones)
    to numerals, and join digit groups ("1 2 3 4" -> "1234")."""
    text = _FILLERS.sub(" ", utterance.lower())
    text = re.sub(r"\s+", " ", text).strip()
    text = _DIGIT_RUN.sub(lambda m: _resolve_run(m.group(), expecting), text)
    text = _WORD_RE.sub(lambda m: _WORD_DIGITS[m.group(1)], text)
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
