"""LLM intent classification with deterministic guardrails and automatic fallback.

Status: the OpenAI-compatible provider is exercised in tests with a mocked HTTP transport and
works against Ollama locally; it is NOT validated against a production LLM endpoint.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.nlu.base import INTENTS, NLUResult, extract_entities, normalize
from app.nlu.rules import RulesNLU
from app.observability import NLU_FALLBACKS, log

SYSTEM_PROMPT = (
    "You are the intent classifier for Northwind Fiber's phone line. Classify the caller's "
    "latest utterance into exactly one intent from this list: " + ", ".join(INTENTS) + ". "
    "Use provide_info when the caller is only answering a question (e.g. giving a number or "
    "a day). Use no_match when the utterance is unrelated or unintelligible. "
    'Respond with JSON only: {"intent": "<intent>", "confidence": <0.0-1.0>}. '
    "Never include account numbers, PINs or other identifiers in your response."
)


def classification_prompt(utterance: str, expecting: str | None) -> str:
    context = f"The IVR just asked the caller for: {expecting}." if expecting else ""
    return f"{context}\nCaller said: {utterance!r}".strip()


class GuardedLLMNLU:
    """Base class: LLM picks the intent, rules supply entities and safety overrides."""

    name = "llm"

    def __init__(self, min_confidence: float = 0.5) -> None:
        self._rules = RulesNLU()
        self._min_confidence = min_confidence

    def classify(self, utterance: str, expecting: str | None) -> dict[str, Any]:
        raise NotImplementedError

    def parse(self, utterance: str, expecting: str | None = None) -> NLUResult:
        baseline = self._rules.parse(utterance, expecting)
        # Safety overrides: never let a model trap a caller who asked for a human, and keep
        # DTMF deterministic.
        if baseline.intent == "agent" or baseline.source == "dtmf":
            return baseline
        try:
            raw = self.classify(utterance, expecting)
            intent, confidence = raw["intent"], float(raw.get("confidence", 0))
            if intent not in INTENTS:
                raise ValueError(f"unknown intent {intent!r}")
        except Exception as exc:  # noqa: BLE001 - any provider failure degrades to rules
            NLU_FALLBACKS.labels(self.name).inc()
            log.warning("nlu_fallback", provider=self.name, error=type(exc).__name__)
            return baseline.model_copy(update={"source": "rules_fallback"})
        if confidence < self._min_confidence:
            return baseline.model_copy(update={"source": "rules_low_confidence"})
        entities = extract_entities(normalize(utterance, expecting), expecting)
        return NLUResult(intent=intent, confidence=confidence, entities=entities, source=self.name)


class OpenAICompatibleNLU(GuardedLLMNLU):
    """Any /v1/chat/completions endpoint: Ollama (free, local), vLLM, OpenAI, Azure OpenAI."""

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 4.0,
        min_confidence: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(min_confidence)
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(timeout=timeout_s)

    def classify(self, utterance: str, expecting: str | None) -> dict[str, Any]:
        resp = self._client.post(
            self._url,
            headers=self._headers,
            json={
                "model": self._model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": classification_prompt(utterance, expecting)},
                ],
            },
        )
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])
