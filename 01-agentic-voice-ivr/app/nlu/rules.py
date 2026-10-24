"""Deterministic NLU: free, fast, testable. Also the safety net for LLM providers."""

from __future__ import annotations

import re

from app.nlu.base import NLUResult, extract_entities, normalize

# Order matters: an explicit request for a human always wins; business intents are checked
# before affirm/deny so "no internet" is an outage, not a "no".
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "agent",
        re.compile(
            r"\b(agent|representative|human|operator|real person|live person|someone real|"
            r"talk to (a |an )?person|customer service)\b"
        ),
    ),
    (
        "check_outage",
        re.compile(
            r"\b(outage|outages|internet (is )?(down|out)|service (is )?(down|out)|no (internet|"
            r"service|signal|connection)|not working|offline|connection (is )?(down|dropping))\b"
        ),
    ),
    (
        "schedule_technician",
        re.compile(
            r"\b(technician|tech visit|send someone|repair (visit|appointment)|schedule|"
            r"appointment|someone to come out|service call)\b"
        ),
    ),
    (
        "check_balance",
        re.compile(
            r"\b(balance|how much do i owe|what do i owe|amount due|my bill|bill amount|owe)\b"
        ),
    ),
    (
        "goodbye",
        re.compile(
            r"\b(bye|goodbye|that'?s all|that is all|nothing else|i'?m done|hang up|that'?s it)\b"
        ),
    ),
    (
        "affirm",
        re.compile(
            r"^(yes|yeah|yep|yup|correct|sure|confirm|that works|ok|okay|please do|book it|"
            r"sounds good)\b"
        ),
    ),
    ("deny", re.compile(r"^(no|nope|nah|cancel|don'?t|not now|negative)\b")),
    ("help", re.compile(r"\b(help|options|what can you do|menu|repeat)\b")),
]

# Classic DTMF menu, honored when the IVR is not collecting a specific slot.
_DTMF = {"1": "check_balance", "2": "check_outage", "3": "schedule_technician", "0": "agent"}


class RulesNLU:
    name = "rules"

    def parse(self, utterance: str, expecting: str | None = None) -> NLUResult:
        text = normalize(utterance)
        entities = extract_entities(text, expecting)
        if expecting is None and text in _DTMF:
            return NLUResult(intent=_DTMF[text], confidence=1.0, source="dtmf")  # type: ignore[arg-type]
        for intent, pattern in _PATTERNS:
            if pattern.search(text):
                return NLUResult(intent=intent, confidence=0.85, entities=entities)  # type: ignore[arg-type]
        if entities:
            return NLUResult(intent="provide_info", confidence=0.9, entities=entities)
        return NLUResult(intent="no_match", confidence=0.0)
