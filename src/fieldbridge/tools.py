"""Read-only tools shared by the Strands layer and local HTTP API."""

from __future__ import annotations

from typing import Any

from .engine import (
    CONTRACTS,
    SUPPORTED_CATEGORIES,
    _route_ticket,
    _routing_profile,
    decision_card_for,
    evaluate_ticket,
)
from .evidence import (
    get_case,
    get_inventory,
    get_replacement_dependencies,
    get_service_history,
    get_site_access,
    known_facts,
)
from .input_validation import ticket_from_payload
from .models import Ticket


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
        "timezone": contract["timezone"],
    }


def inspect_routing(category: str) -> dict[str, object]:
    """Return an internal ownership recommendation, not a live dispatch action."""

    if category not in SUPPORTED_CATEGORIES:
        raise ValueError("category is not an approved synthetic category")
    owner, serial_required, routing_notes = _route_ticket(category)
    profile = _routing_profile(
        Ticket(
            ticket_id="FB-ROUTING-TOOL",
            contract_id="metro-financial" if category == "enterprise_fax" else "civic-research",
            priority="P2",
            category=category,
            summary="approved routing inspection",
            serial_number=None,
            replacement_needed=False,
            part_available_locally=False,
            site_access="unknown",
        ),
        owner,
    )
    return {
        "category": category,
        "owner": owner,
        "serial_number_required": serial_required,
        "routing_notes": routing_notes,
        **profile,
        "execution_state": "draft_only",
    }


def create_handoff_draft(payload: Any) -> dict[str, object]:
    """Validate a synthetic payload and return a non-executing decision draft."""

    return evaluate_ticket(ticket_from_payload(payload)).as_dict()


def load_case(ticket_id: str) -> dict[str, object]:
    """Load one approved thin ticket without exposing hidden fixture truth."""

    return get_case(ticket_id).model_dump(mode="json")


def service_history(ticket_id: str) -> dict[str, object]:
    """Inspect bounded synthetic service history for one approved case."""

    return get_service_history(ticket_id)


def site_access_policy(site_ref: str) -> dict[str, object]:
    """Inspect bounded synthetic site-access policy."""

    return get_site_access(site_ref)


def fulfillment_requirements(contract_id: str, ticket_id: str) -> dict[str, object]:
    """Return deterministic fulfillment and restoration requirements."""

    raw_ticket = get_case(ticket_id)
    if raw_ticket.contract_id != contract_id:
        raise ValueError("contract_id does not match the approved synthetic case")
    card = decision_card_for(raw_ticket, known_facts(ticket_id))
    return {
        "ticket_id": ticket_id,
        "plan": card.fulfillment_plan,
        "part_delivery": card.part_delivery,
        "inventory": get_inventory(ticket_id),
        "replacement_dependencies": list(get_replacement_dependencies(ticket_id)),
        "restoration_steps": list(card.restoration_steps),
        "closure_proof": list(card.closure_proof),
        "execution_state": "draft_only",
    }


def validate_draft(ticket_id: str, proposal: Any) -> dict[str, object]:
    """Reject model proposals that conflict with authoritative deterministic policy."""

    if not isinstance(proposal, dict):
        raise TypeError("proposal must be a JSON object")
    authoritative = decision_card_for(get_case(ticket_id), known_facts(ticket_id))
    expected = authoritative.model_dump(mode="json")
    protected_fields = {
        "ticket_id",
        "allowed_priority",
        "sla",
        "sla_deadline",
        "sla_timezone",
        "owner",
        "access_constraint",
        "fulfillment_plan",
        "part_delivery",
        "restoration_steps",
        "closure_proof",
        "blocked_actions",
        "requires_human_approval",
        "execution_state",
        "contracted_team",
        "internal_team",
        "point_of_contact",
        "schedule_recommendation",
        "escalation_recommendation",
        "dispatch_recommendation",
    }
    conflicts = sorted(
        field
        for field in protected_fields
        if field not in proposal or proposal[field] != expected[field]
    )
    if conflicts:
        raise ValueError(
            "proposal conflicts with authoritative policy fields: " + ", ".join(conflicts)
        )
    return {**expected, "validation_status": "accepted_for_human_review"}


def safety_boundary() -> dict[str, object]:
    """Make the hard limits visible to a model, operator, and judge."""

    return {
        "synthetic_only": True,
        "allowed_operations": ["inspect", "recommend", "draft", "record_review"],
        "blocked_operations": [
            "dispatch",
            "order_parts",
            "contact_customer",
            "modify_ticket",
            "close_ticket",
        ],
        "approval_required": True,
    }
