"""Turn findings into a readable diagnosis.

The template narrator is deterministic and always available. The LLM narrator writes a more
natural explanation, but its output is accepted only if it passes a grounding check:
  * every claim cites a finding ID like [F1], and only IDs that exist
  * every number in the text appears in the findings' evidence or detail
Otherwise the template output is used. An LLM can explain; it cannot measure.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from sipdoc.models import Finding
from sipdoc.observability import NARRATOR_FALLBACKS, log

_CITATION = re.compile(r"\[(F\d+)\]")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


def _lc(title: str) -> str:
    """Lowercase the first word for mid-sentence use, keeping acronyms like SDP and RTP."""
    first, _, rest = title.partition(" ")
    return f"{first.lower() if not first.isupper() else first} {rest}".strip()


class Narrator(Protocol):
    name: str

    def narrate(self, findings: list[Finding], context: str) -> str: ...


class TemplateNarrator:
    name = "template"

    def narrate(self, findings: list[Finding], context: str) -> str:
        if not findings:
            return f"No faults detected. {context}"
        root, *rest = findings
        text = f"Most likely cause: {_lc(root.title)} [{root.id}]. {root.detail} [{root.id}]"
        if rest:
            also = "; ".join(f"{_lc(f.title)} [{f.id}]" for f in rest)
            text += f" Also observed: {also}."
        return text


def grounding_errors(text: str, findings: list[Finding]) -> list[str]:
    known = {f.id for f in findings}
    cited = set(_CITATION.findall(text))
    errors = []
    if findings and not cited:
        errors.append("no citations")
    if unknown := cited - known:
        errors.append(f"unknown citations {sorted(unknown)}")
    corpus = " ".join([f.detail for f in findings] + [e.fact for f in findings for e in f.evidence])
    corpus_numbers = set(_NUMBER.findall(corpus)) | {f.id[1:] for f in findings}
    if invented := set(_NUMBER.findall(_CITATION.sub("", text))) - corpus_numbers:
        errors.append(f"ungrounded numbers {sorted(invented)}")
    return errors


class OpenAICompatibleNarrator:
    """Any /v1/chat/completions endpoint (Ollama, vLLM, OpenAI). SIMULATED: tested with a mocked
    transport only."""

    name = "openai_compatible"
    SYSTEM = (
        "You are a senior VoIP engineer. Explain the diagnosis of a SIP call to a Tier-1 "
        "support engineer in 2-4 sentences. Use ONLY the findings provided. Cite each claim "
        "with its finding ID in square brackets, e.g. [F1]. Do not introduce any number "
        'that is not in the findings. Respond with JSON: {"summary": "..."}'
    )

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 8.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(timeout=timeout_s)
        self._fallback = TemplateNarrator()

    def narrate(self, findings: list[Finding], context: str) -> str:
        if not findings:
            return self._fallback.narrate(findings, context)
        payload = [
            f.model_dump(include={"id", "signature", "severity", "detail", "evidence"})
            for f in findings
        ]
        try:
            resp = self._client.post(
                self._url,
                headers=self._headers,
                json={
                    "model": self._model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": self.SYSTEM},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                },
            )
            resp.raise_for_status()
            text = json.loads(resp.json()["choices"][0]["message"]["content"])["summary"]
        except Exception as exc:  # noqa: BLE001 - any provider failure degrades to template
            NARRATOR_FALLBACKS.labels("error").inc()
            log.warning("narrator_fallback", reason=type(exc).__name__)
            return self._fallback.narrate(findings, context)
        if errors := grounding_errors(text, findings):
            NARRATOR_FALLBACKS.labels("ungrounded").inc()
            log.warning("narrator_rejected", errors=errors)
            return self._fallback.narrate(findings, context)
        return text
