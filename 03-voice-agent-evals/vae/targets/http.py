"""HTTP target for agents that implement the turn API (01-agentic-voice-ivr's /v1/calls)."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from vae.targets.base import CallEndedError, TargetError, ToolEvent, ToolInfo, TurnView


class HttpTarget:
    """Speaks the turn API over HTTP.

    Pass ``app`` (an ASGI application) instead of a live server to evaluate an agent in-process:
    the same requests, serialization and status codes, without opening a port.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        timeout_s: float = 10.0,
        app: Any = None,
        name: str | None = None,
    ) -> None:
        transport = httpx.ASGITransport(app=app) if app is not None else None
        self.name = name or (f"in-process:{type(app).__name__}" if app is not None else base_url)
        self._client = httpx.AsyncClient(
            base_url="http://target" if app is not None else base_url,
            transport=transport,
            headers={"X-API-Key": api_key} if api_key else {},
            timeout=timeout_s,
        )

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            resp = await self._client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise TargetError(f"{type(exc).__name__} on {method} {path}") from exc
        if resp.status_code == 409:
            raise CallEndedError(path)
        if resp.status_code >= 400:
            raise TargetError(f"HTTP {resp.status_code} on {method} {path}")
        return resp

    @staticmethod
    def _view(resp: httpx.Response) -> TurnView:
        try:
            return TurnView.model_validate(resp.json())
        except (ValueError, ValidationError) as exc:
            raise TargetError("malformed turn response") from exc

    async def catalog(self) -> list[ToolInfo]:
        resp = await self._request("GET", "/v1/tools")
        return [ToolInfo.model_validate(t) for t in resp.json()]

    async def start_call(self) -> TurnView:
        return self._view(await self._request("POST", "/v1/calls", json={"channel": "api"}))

    async def send_turn(self, call_id: str, text: str) -> TurnView:
        return self._view(
            await self._request("POST", f"/v1/calls/{call_id}/turns", json={"text": text})
        )

    async def tool_events(self, call_id: str) -> list[ToolEvent]:
        resp = await self._request("GET", f"/v1/calls/{call_id}")
        return [ToolEvent.model_validate(e) for e in resp.json().get("events", [])]

    async def metrics_text(self) -> str | None:
        try:
            resp = await self._client.get("/metrics")
        except httpx.HTTPError:
            return None
        return resp.text if resp.status_code == 200 else None

    async def aclose(self) -> None:
        await self._client.aclose()
