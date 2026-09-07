"""AgentCore HTTP adapter for FieldBridge's bounded scenario runner.

The public contract accepts an approved scenario identifier only. It never
accepts a free-form prompt or a customer ticket.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from fieldbridge.evidence import get_scenario
from fieldbridge.strands_layer import run_investigation

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_ALLOWED_KEYS = frozenset({"scenario_id", "correlation_id"})

app = FastAPI(title="FieldBridge AgentCore worker", docs_url=None, redoc_url=None)


@app.get("/ping")
def ping() -> dict[str, str]:
    """Return non-secret runtime metadata required by AgentCore health checks."""

    return {
        "status": "Healthy",
        "mode": "synthetic_only",
        "model_id": os.getenv("BEDROCK_MODEL_ID", "UNKNOWN"),
        "deployment_revision": os.getenv("DEPLOYMENT_REVISION", "UNKNOWN"),
    }


@app.post("/invocations")
async def invoke(request: Request) -> dict[str, Any]:
    """Investigate one allowlisted synthetic scenario."""

    try:
        body = await request.body()
        if len(body) > 4096:
            raise ValueError("request is too large")
        payload = json.loads(body)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="invalid request") from error
    if not isinstance(payload, dict) or set(payload) - _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail="invalid request")

    scenario_id = payload.get("scenario_id")
    correlation_id = payload.get("correlation_id") or str(uuid.uuid4())
    if not isinstance(scenario_id, str) or not _ID_PATTERN.fullmatch(scenario_id):
        raise HTTPException(status_code=400, detail="invalid request")
    if not isinstance(correlation_id, str) or not _CORRELATION_PATTERN.fullmatch(correlation_id):
        raise HTTPException(status_code=400, detail="invalid request")

    try:
        raw_ticket = get_scenario(scenario_id)
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=404, detail="scenario not found") from error

    result = run_investigation(raw_ticket, correlation_id=correlation_id)
    return result.model_dump(mode="json")
