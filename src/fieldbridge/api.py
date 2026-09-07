"""Public-safe HTTP surface and judge-facing UI for FieldBridge."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from .run_service import (
    LocalRunService,
    RunConflictError,
    RunNotFoundError,
    RunValidationError,
    ScenarioNotFoundError,
)
from .runtime_config import build_quota_service, build_run_service
from .tools import safety_boundary
from .workflow import QuotaService

WEB_ROOT = Path(__file__).with_name("web")


class ScenarioRunRequest(BaseModel):
    """The public runner accepts only a pre-approved synthetic scenario ID."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str


class ReviewRequest(BaseModel):
    """A bounded review decision; it never causes an operational action."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "request_changes", "reject"]
    reason_code: Literal[
        "evidence_verified",
        "insufficient_evidence",
        "policy_exception",
        "routing_correction",
    ]


class CorrectionRequest(BaseModel):
    """A fixed synthetic evidence packet; no contact data or free text is accepted."""

    model_config = ConfigDict(extra="forbid")

    correction_id: Literal["serial_and_user_confirmed"]


app = FastAPI(
    title="FieldBridge",
    version="0.2.0",
    description=(
        "FieldBridge investigates bounded synthetic field-service scenarios and prepares "
        "human-reviewable decision packets. It never executes operational actions."
    ),
)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")
app.state.run_service = build_run_service()
app.state.quota_service = build_quota_service()


def set_run_service(service: object) -> None:
    """Inject a workflow-backed service without coupling routes to its implementation."""

    app.state.run_service = service


def set_quota_service(service: QuotaService) -> None:
    """Inject a quota adapter while keeping raw source addresses out of storage."""

    app.state.quota_service = service


def _service(request: Request) -> LocalRunService:
    return request.app.state.run_service


def _quota_service(request: Request) -> QuotaService:
    return request.app.state.quota_service


def _client_source(request: Request) -> str:
    """Derive a stable quota source without storing raw addresses.

    Behind the submitted API Gateway/Lambda topology every direct peer is the
    gateway itself, so the first ``X-Forwarded-For`` entry is the caller. The
    value is only ever HMAC-derived inside the quota service.
    """

    forwarded = request.headers.get("X-Forwarded-For", "")
    first_hop = forwarded.split(",")[0].strip() if forwarded else ""
    if first_hop:
        return first_hop
    return request.client.host if request.client is not None else "unknown-source"


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, _error: RequestValidationError
) -> Response:
    """Reject unapproved public fields without echoing request values."""

    return Response(
        content='{"detail":"request does not meet FieldBridge policy"}',
        status_code=400,
        media_type="application/json",
    )


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    """Apply a strict browser security baseline to every public response."""

    if request.method in {"POST", "PUT", "PATCH"} and len(await request.body()) > 4096:
        response = JSONResponse(status_code=413, content={"detail": "request body too large"})
    else:
        response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    """Serve the zero-build, judge-facing operations console."""

    return FileResponse(WEB_ROOT / "index.html", media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False, status_code=204)
def favicon() -> Response:
    """Avoid a noisy browser 404 without adding an external asset."""

    return Response(status_code=204)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "synthetic_draft_only"}


@app.get("/api/v1/boundary")
def boundary() -> dict[str, object]:
    return safety_boundary()


@app.get("/api/v1/scenarios")
def scenarios(request: Request) -> dict[str, object]:
    return {"scenarios": _service(request).list_scenarios()}


@app.post("/api/v1/demo/reset")
def reset_demo(request: Request) -> dict[str, object]:
    try:
        _service(request).reset()
    except RunConflictError as error:
        raise HTTPException(status_code=409, detail="shared demo ledger cannot be reset") from error
    return {"status": "reset", "synthetic_only": True}


@app.post("/api/v1/runs", status_code=status.HTTP_201_CREATED)
def create_run(
    payload: ScenarioRunRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    if idempotency_key is None or not 8 <= len(idempotency_key) <= 128:
        raise HTTPException(status_code=400, detail="valid idempotency key required")
    source_identifier = _client_source(request)
    quota = _quota_service(request).check_and_consume(source_identifier)
    if not quota.allowed:
        raise HTTPException(status_code=429, detail="public demo run quota exceeded")
    try:
        return _service(request).create_run(payload.scenario_id, idempotency_key)
    except ScenarioNotFoundError as error:
        raise HTTPException(status_code=404, detail="scenario not found") from error
    except RunValidationError as error:
        raise HTTPException(status_code=400, detail="invalid run request") from error
    except RunConflictError as error:
        raise HTTPException(status_code=409, detail="idempotency conflict") from error


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, object]:
    try:
        return _service(request).get_run(run_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error


@app.get("/api/v1/runs/{run_id}/events")
def get_run_events(run_id: str, request: Request) -> dict[str, object]:
    try:
        return {"events": _service(request).get_events(run_id)}
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error


@app.post("/api/v1/runs/{run_id}/reviews")
def review_run(
    run_id: str, payload: ReviewRequest, request: Request
) -> dict[str, object]:
    try:
        return _service(request).review_run(run_id, payload.decision, payload.reason_code)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except RunConflictError as error:
        raise HTTPException(status_code=409, detail="run is not reviewable") from error


@app.post("/api/v1/runs/{run_id}/corrections")
def correct_run(
    run_id: str, payload: CorrectionRequest, request: Request
) -> dict[str, object]:
    try:
        return _service(request).apply_correction(run_id, payload.correction_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail="unsupported synthetic correction") from error
    except RunConflictError as error:
        raise HTTPException(status_code=409, detail="run is not correctable") from error
