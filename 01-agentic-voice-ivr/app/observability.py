"""Structured logging with PII redaction, Prometheus metrics, and OpenTelemetry tracing."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from opentelemetry import trace
from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------- redaction
# Keys whose values are never written to logs, whatever they contain.
SENSITIVE_KEYS = frozenset(
    {
        "pin",
        "account_number",
        "utterance",
        "text",
        "speechresult",
        "digits",
        "x-api-key",
        "authorization",
        "password",
        "token",
    }
)
# Any run of 4+ digits in free text could be a PIN, account, card or phone number.
_DIGIT_RUN = re.compile(r"\d{4,}")


def redact_text(value: str) -> str:
    return _DIGIT_RUN.sub("[NUM]", value)


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def _redaction_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: (redact(v) if k == "event" else redact(v, k)) for k, v in event_dict.items()}


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its URLs can carry call IDs
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _redaction_processor,
            structlog.processors.TimeStamper(fmt="iso", utc=True),  # after redaction
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),  # resolves sys.stdout per logger
        cache_logger_on_first_use=False,
    )


log = structlog.get_logger("ivr")

# ---------------------------------------------------------------- metrics
_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)

TURNS = Counter("ivr_turns_total", "Conversation turns processed", ["intent", "channel"])
TURN_LATENCY = Histogram(
    "ivr_turn_latency_seconds",
    "Agent processing time per turn (excludes ASR/TTS)",
    buckets=_LATENCY_BUCKETS,
)
TOOL_CALLS = Counter("ivr_tool_calls_total", "Tool invocations", ["tool", "outcome"])
TOOL_LATENCY = Histogram(
    "ivr_tool_latency_seconds", "Tool execution time", ["tool"], buckets=_LATENCY_BUCKETS
)
CALL_OUTCOMES = Counter("ivr_call_outcomes_total", "Terminal call outcomes", ["outcome"])
NLU_FALLBACKS = Counter(
    "ivr_nlu_fallbacks_total", "LLM NLU failures that fell back to rules", ["provider"]
)

# ---------------------------------------------------------------- tracing
tracer = trace.get_tracer("agentic-voice-ivr")


def configure_tracing(console_exporter: bool) -> None:
    """Console exporter for local inspection. Swap in an OTLP exporter for Jaeger/X-Ray."""
    if not console_exporter:
        return
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    provider = TracerProvider(resource=Resource.create({"service.name": "agentic-voice-ivr"}))
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
