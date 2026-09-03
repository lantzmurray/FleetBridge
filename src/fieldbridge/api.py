"""Local-only HTTP surface for the synthetic FieldBridge demonstration."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from .tools import create_handoff_draft, safety_boundary

app = FastAPI(
    title="FieldBridge",
    version="0.1.0",
    description="Synthetic-only draft handoffs. No dispatch, part ordering, customer contact, or closure.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Expose only the local demonstration state."""

    return {"status": "ok", "mode": "synthetic_draft_only"}


@app.get("/api/v1/boundary")
def boundary() -> dict[str, object]:
    """Show the hard safety limits before an operator submits a fixture."""

    return safety_boundary()


@app.post("/api/v1/handoffs")
async def handoff(request: Request) -> dict[str, object]:
    """Create a non-persistent handoff draft from a strictly validated payload."""

    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="invalid JSON request body") from error
    try:
        return create_handoff_draft(payload)
    except ValueError as error:
        raise HTTPException(
            status_code=400, detail="request does not meet FieldBridge policy"
        ) from error
