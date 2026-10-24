"""HTTP API. Run with: uvicorn sipdoc.api.app:app --reload"""

from __future__ import annotations

import secrets
import tempfile
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.concurrency import run_in_threadpool

from sipdoc import __version__
from sipdoc.analyzers import SIGNATURES
from sipdoc.config import Settings, get_settings
from sipdoc.engine import analyze_capture, ladder_mermaid, ladder_text
from sipdoc.models import AnalysisReport, CallFlow
from sipdoc.narrator import Narrator, OpenAICompatibleNarrator, TemplateNarrator
from sipdoc.observability import configure_logging, log
from sipdoc.parser import CaptureError

ALLOWED_SUFFIXES = {".pcap", ".pcapng", ".cap"}
DESCRIPTION = """
Upload a packet capture; get per-call diagnoses with evidence-cited findings, a SIP ladder,
and runbook steps. Analyzers are deterministic. An optional LLM narrator rewrites the summary
but is rejected unless every claim cites a finding and every number appears in the evidence.

All bundled captures are **synthetic**. See the README for validation status.
"""


class AnalysisStore:
    """Bounded in-memory store (oldest evicted). Captures themselves are never kept."""

    def __init__(self, capacity: int) -> None:
        self._items: OrderedDict[str, tuple[AnalysisReport, dict[str, CallFlow]]] = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()

    def put(self, report: AnalysisReport, calls: list[CallFlow]) -> None:
        with self._lock:
            self._items[report.analysis_id] = (report, {c.call_id: c for c in calls})
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get(self, analysis_id: str) -> tuple[AnalysisReport, dict[str, CallFlow]]:
        with self._lock:
            if analysis_id not in self._items:
                raise HTTPException(status_code=404, detail="analysis_not_found")
            return self._items[analysis_id]


def build_narrator(settings: Settings) -> Narrator:
    if settings.narrator == "openai_compatible":
        return OpenAICompatibleNarrator(
            settings.llm_base_url,
            settings.llm_model,
            settings.llm_api_key.get_secret_value(),
            settings.llm_timeout_s,
        )
    return TemplateNarrator()


def create_app(settings: Settings | None = None, narrator: Narrator | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="SIP Call Doctor", version=__version__, description=DESCRIPTION)
    store = AnalysisStore(settings.max_stored_analyses)
    narrator = narrator or build_narrator(settings)

    def require_key(x_api_key: str = Header(default="")) -> None:
        if not secrets.compare_digest(
            x_api_key.encode(), settings.api_key.get_secret_value().encode()
        ):
            raise HTTPException(status_code=401, detail="invalid_api_key")

    @app.middleware("http")
    async def context(request: Request, call_next):  # noqa: ANN001, ANN202
        rid = uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        response = await call_next(request)
        response.headers.update(
            {"X-Request-ID": rid, "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
        )
        return response

    @app.get("/health/live", tags=["operations"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["operations"])
    def ready() -> dict[str, str]:
        return {"status": "ready", "narrator": narrator.name}

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get(
        "/v1/signatures",
        tags=["analysis"],
        dependencies=[Depends(require_key)],
        summary="Fault signatures this version detects",
    )
    def signatures() -> list[dict]:
        return [
            {"name": s.name, "title": s.title, "runbook": list(s.runbook)}
            for s in SIGNATURES.values()
        ]

    @app.post(
        "/v1/analyses",
        tags=["analysis"],
        status_code=201,
        response_model=AnalysisReport,
        dependencies=[Depends(require_key)],
        summary="Upload and analyze a capture",
    )
    async def create_analysis(capture: UploadFile = File(...)) -> AnalysisReport:
        name = Path(capture.filename or "capture.pcap").name
        if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
            raise HTTPException(status_code=415, detail="expected .pcap, .pcapng or .cap")
        limit = settings.max_upload_mb * 1024 * 1024
        with tempfile.TemporaryDirectory(prefix="sipdoc-") as tmp:
            path = Path(tmp) / "upload.pcap"
            size = 0
            with path.open("wb") as fh:
                while chunk := await capture.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(status_code=413, detail="capture_too_large")
                    fh.write(chunk)
            try:
                report, parsed = await run_in_threadpool(analyze_capture, path, name, narrator)
            except CaptureError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.put(report, parsed.calls())  # the upload directory is already deleted here
        return report

    @app.get(
        "/v1/analyses/{analysis_id}",
        tags=["analysis"],
        response_model=AnalysisReport,
        dependencies=[Depends(require_key)],
    )
    def get_analysis(analysis_id: str) -> AnalysisReport:
        return store.get(analysis_id)[0]

    @app.get(
        "/v1/analyses/{analysis_id}/calls/{call_id}/ladder",
        tags=["analysis"],
        response_class=PlainTextResponse,
        dependencies=[Depends(require_key)],
        summary="SIP ladder as Mermaid (default) or plain text",
    )
    def ladder(analysis_id: str, call_id: str, fmt: str = "mermaid") -> str:
        calls = store.get(analysis_id)[1]
        if call_id not in calls:
            raise HTTPException(status_code=404, detail="call_not_found")
        return ladder_text(calls[call_id]) if fmt == "text" else ladder_mermaid(calls[call_id])

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": "internal_error"})

    return app


app = create_app()
