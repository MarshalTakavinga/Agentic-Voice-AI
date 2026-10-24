"""Structured logging with phone-number redaction, and Prometheus metrics."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from prometheus_client import Counter, Histogram

# Phone numbers (E.164 or long digit runs) and SIP user parts never reach logs.
_PHONE = re.compile(r"\+?\d{6,}")
_SIP_USER = re.compile(r"(sips?:)[^@;>\s]+@")


def redact_text(value: str) -> str:
    return _PHONE.sub("[NUM]", _SIP_USER.sub(r"\1[USER]@", value))


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


def _processor(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    return {k: _redact(v) for k, v in event.items()}


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    logging.getLogger("scapy").setLevel(logging.ERROR)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _processor,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def mask_number(user: str | None) -> str | None:
    """Display form for phone numbers in reports: keep the last 4 digits."""
    if not user:
        return user
    digits = re.sub(r"\D", "", user)
    return f"***{digits[-4:]}" if len(digits) >= 6 else user


log = structlog.get_logger("sipdoc")

ANALYSES = Counter("sipdoc_analyses_total", "Captures analyzed", ["outcome"])
ANALYSIS_SECONDS = Histogram(
    "sipdoc_analysis_seconds",
    "Capture analysis time",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
FINDINGS = Counter("sipdoc_findings_total", "Findings raised", ["signature", "severity"])
NARRATOR_FALLBACKS = Counter(
    "sipdoc_narrator_fallbacks_total", "LLM narrations replaced by the template", ["reason"]
)
