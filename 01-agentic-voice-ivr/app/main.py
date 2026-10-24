"""Application factory. Run with: uvicorn app.main:app --reload"""

from __future__ import annotations

import re
import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.adapters.base import CustomerSystem
from app.adapters.mock import MockCustomerSystem
from app.agent.graph import IVRAgent
from app.api import routes, twilio
from app.config import Settings, get_settings
from app.nlu import build_nlu
from app.observability import configure_logging, configure_tracing, log
from app.service import CallEnded, CallNotFound, CallService
from app.sessions import InMemorySessionStore
from app.tools import build_registry


def build_planner(settings: Settings, registry, client=None, budget=None):
    """Return a Claude planner when enabled and keyed (or given a client), else None.
    Pass a shared ``budget`` so several app instances draw on one daily spend cap."""
    key = settings.anthropic_api_key.get_secret_value()
    if not settings.planner_enabled or not (key or client):
        return None
    from app.agent.planner import AnthropicClient, Budget, Planner

    return Planner(
        client or AnthropicClient(key, settings.planner_model, settings.planner_timeout_s),
        registry,
        budget or Budget(settings.planner_daily_budget_usd),
        max_tokens=settings.planner_max_tokens,
        max_turns_per_call=settings.planner_max_turns_per_call,
    )


_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")

DESCRIPTION = """
Agentic conversational IVR for a (fictional) fiber ISP, Northwind Fiber.

* **/v1** – JSON API used by the simulator, eval harness and other services (`X-API-Key`).
* **/voice/twilio** – Twilio Programmable Voice webhooks returning TwiML (signature-validated).

All enterprise systems are **simulated** with synthetic data. See the README for which
integrations are live-tested and which are not.
"""


def create_app(
    settings: Settings | None = None, system: CustomerSystem | None = None, planner_budget=None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings.otel_console_exporter)

    system = system or MockCustomerSystem(settings.data_dir)
    registry = build_registry(system)
    agent = IVRAgent(
        build_nlu(settings), registry, settings, planner=build_planner(settings, registry)
    )
    service = CallService(agent, InMemorySessionStore(ttl_s=settings.session_ttl_s))

    app = FastAPI(title="Agentic Voice IVR", version=__version__, description=DESCRIPTION)
    app.state.settings = settings
    app.state.system = system
    app.state.service = service
    app.include_router(routes.ops)
    app.include_router(routes.v1)
    app.include_router(twilio.router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # noqa: ANN001, ANN202
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path != "/metrics":
            log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        return response

    def _error(request: Request, status: int, code: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"error": code, "request_id": getattr(request.state, "request_id", None)},
        )

    @app.exception_handler(CallNotFound)
    async def _not_found(request: Request, _exc: CallNotFound) -> JSONResponse:
        return _error(request, 404, "call_not_found")

    @app.exception_handler(CallEnded)
    async def _ended(request: Request, _exc: CallEnded) -> JSONResponse:
        return _error(request, 409, "call_ended")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=type(exc).__name__)
        return _error(request, 500, "internal_error")

    log.info(
        "app_started", version=__version__, env=settings.env, nlu_provider=settings.nlu_provider
    )
    return app


app = create_app()
