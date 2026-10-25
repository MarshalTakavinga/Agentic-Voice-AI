from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.schemas import CallDetail, CallView, ErrorResponse, StartCallRequest, TurnRequest
from app.service import CallService, public_view

ops = APIRouter(tags=["operations"])
v1 = APIRouter(prefix="/v1", tags=["calls"])


def get_service(request: Request) -> CallService:
    return request.app.state.service


def require_api_key(request: Request, x_api_key: str = Header(default="")) -> None:
    expected = request.app.state.settings.api_key.get_secret_value()
    if not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid_api_key")


@ops.get("/health/live", summary="Liveness probe")
def live() -> dict[str, str]:
    return {"status": "ok"}


@ops.get("/health/ready", summary="Readiness probe (checks downstream adapters)")
def ready(request: Request, response: Response) -> dict[str, str]:
    try:
        system_ok = request.app.state.system.ping()
    except Exception:  # noqa: BLE001 - readiness must never raise
        system_ok = False
    state_ok = request.app.state.kv.ping()  # sessions live here; without it no turn can run
    ok = system_ok and state_ok
    if not ok:
        response.status_code = 503
    return {
        "status": "ready" if ok else "degraded",
        "nlu_provider": request.app.state.settings.nlu_provider,
        "state_backend": request.app.state.settings.state_backend,
        "state_store": "ok" if state_ok else "unavailable",
    }


@ops.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


_ERRORS = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


@v1.post(
    "/calls",
    response_model=CallView,
    status_code=201,
    responses=_ERRORS,
    dependencies=[Depends(require_api_key)],
    summary="Start a simulated call",
)
def start_call(
    body: StartCallRequest | None = None, service: CallService = Depends(get_service)
) -> dict:
    return public_view(service.start_call(channel=(body.channel if body else "api")))


@v1.post(
    "/calls/{call_id}/turns",
    response_model=CallView,
    responses=_ERRORS,
    dependencies=[Depends(require_api_key)],
    summary="Send one caller utterance",
)
def take_turn(call_id: str, body: TurnRequest, service: CallService = Depends(get_service)) -> dict:
    return public_view(service.take_turn(call_id, body.text))


@v1.get(
    "/calls/{call_id}",
    response_model=CallDetail,
    responses=_ERRORS,
    dependencies=[Depends(require_api_key)],
    summary="Call state and tool audit trail",
)
def get_call(call_id: str, service: CallService = Depends(get_service)) -> dict:
    return public_view(service.get(call_id), include_events=True)


@v1.get(
    "/tools",
    dependencies=[Depends(require_api_key)],
    summary="Tool catalog (JSON schemas usable for LLM tool calling)",
)
def list_tools(request: Request) -> list[dict]:
    return request.app.state.service.agent.tools.schemas()
