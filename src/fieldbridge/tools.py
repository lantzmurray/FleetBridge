"""Read-only tools shared by the Strands layer and local HTTP API."""

from __future__ import annotations

from typing import Any

from .engine import CONTRACTS, _route_ticket, evaluate_ticket
from .input_validation import ticket_from_payload


def inspect_contract(contract_id: str) -> dict[str, object]:
    """Return the approved synthetic contract policy without customer data."""

    if contract_id not in CONTRACTS:
        raise ValueError("contract_id is not an approved synthetic profile")
    contract = CONTRACTS[contract_id]
    return {
        "contract_id": contract_id,
        "allowed_priorities": sorted(contract["allowed_priorities"]),
        "sla": contract["sla"],
        "hot_swap_available": contract["hot_swap"],
        "local_courier_available": contract["local_courier"],
    }


def inspect_routing(category: str) -> dict[str, object]:
    """Return an internal ownership recommendation, not a live dispatch action."""

    owner, serial_required, routing_notes = _route_ticket(category)
    return {
        "category": category,
        "owner": owner,
        "serial_number_required": serial_required,
        "routing_notes": routing_notes,
        "execution_state": "draft_only",
    }


def create_handoff_draft(payload: Any) -> dict[str, object]:
    """Validate a synthetic payload and return a non-executing decision draft."""

    return evaluate_ticket(ticket_from_payload(payload)).as_dict()


def safety_boundary() -> dict[str, object]:
    """Make the hard limits visible to a model, operator, and judge."""

    return {
        "synthetic_only": True,
        "allowed_operations": ["inspect", "recommend", "draft"],
        "blocked_operations": ["dispatch", "order_parts", "contact_customer", "close_ticket"],
        "approval_required": True,
    }
