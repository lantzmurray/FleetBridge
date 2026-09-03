"""Optional Strands layer around FieldBridge's deterministic safety floor."""

from __future__ import annotations

import json
from typing import Any

from .tools import create_handoff_draft, inspect_contract, inspect_routing, safety_boundary

SYSTEM_PROMPT = """You are FieldBridge, a public-safe field-service handoff agent.
Use the supplied tools to inspect only synthetic contract policies and ticket data.
Never claim to dispatch a technician, order a part, contact a customer, change a
ticket, close a ticket, or access a real system. Return a concise, structured
explanation of the draft decision and clearly surface every human-review reason.
If the handoff tool rejects input, ask for a corrected synthetic payload instead
of guessing missing facts."""


def build_agent() -> Any:
    """Build a Strands agent when the optional SDK and model credentials exist.

    The project remains fully runnable and testable without a model call. The
    tool wrappers expose only immutable policy inspection and draft generation.
    """

    try:
        from strands import Agent, tool
    except ImportError as error:
        raise RuntimeError(
            "Install the project dependencies to enable the Strands demo."
        ) from error

    @tool
    def contract_policy(contract_id: str) -> str:
        """Inspect one approved synthetic contract profile."""

        return json.dumps(inspect_contract(contract_id), sort_keys=True)

    @tool
    def routing_policy(category: str) -> str:
        """Inspect the deterministic internal owner for a supported category."""

        return json.dumps(inspect_routing(category), sort_keys=True)

    @tool
    def handoff_draft(ticket_json: str) -> str:
        """Validate one synthetic ticket JSON object and produce a draft-only handoff."""

        try:
            payload = json.loads(ticket_json)
        except json.JSONDecodeError as error:
            return f"INPUT_REJECTED: ticket_json must be valid JSON ({error.msg})."
        try:
            return json.dumps(create_handoff_draft(payload), sort_keys=True)
        except ValueError as error:
            return f"INPUT_REJECTED: {error}"

    @tool
    def fieldbridge_safety_boundary() -> str:
        """Read FieldBridge's non-negotiable no-action safety boundary."""

        return json.dumps(safety_boundary(), sort_keys=True)

    return Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[contract_policy, routing_policy, handoff_draft, fieldbridge_safety_boundary],
    )
