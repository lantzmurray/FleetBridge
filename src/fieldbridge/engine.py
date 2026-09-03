"""Deterministic contract and routing policy for FieldBridge.

The deterministic layer is the safety floor. A Strands agent may inspect this
output and draft an explanation, but cannot alter contract rules or execute a
dispatch, customer contact, part order, or closure.
"""

from __future__ import annotations

from .models import HandoffDecision, Ticket


CONTRACTS = {
    "northstar-health": {
        "allowed_priorities": {"P1", "P2"},
        "sla": {"P1": "resolve within 4 hours", "P2": "end of next business day"},
        "hot_swap": True,
        "local_courier": True,
    },
    "civic-research": {
        "allowed_priorities": {"P2"},
        "sla": {"P2": "end of next business day"},
        "hot_swap": False,
        "local_courier": False,
    },
    "metro-financial": {
        "allowed_priorities": {"P2"},
        "sla": {"P2": "end of next business day"},
        "hot_swap": False,
        "local_courier": False,
    },
}

_PLATFORM_ROUTES = {
    "enterprise_fax": (
        "enterprise_fax_support",
        False,
        "Route to the internal enterprise fax team; do not redirect this platform issue to local IT.",
    ),
    "managed_print_access": (
        "managed_print_platform_support",
        True,
        "Route to the internal platform team with the original ticket cross-reference.",
    ),
}


def evaluate_ticket(ticket: Ticket) -> HandoffDecision:
    """Produce a public-safe, draft-only handoff decision for one ticket."""

    contract = _contract_for(ticket.contract_id)
    normalized_priority, review_reasons = _normalize_priority(ticket, contract)
    if ticket.site_access == "unknown":
        review_reasons.append("site access must be confirmed")

    owner, serial_required, routing_notes = _route_ticket(ticket.category)
    required_steps = _base_steps(ticket, owner)
    if not ticket.actual_user_known:
        required_steps.extend(("recover an actual-user contact", "draft a customer update"))
        review_reasons.append("actual-user contact is missing")

    fulfillment, part_delivery, fulfillment_steps, closure_requirements = _plan_fulfillment(ticket, contract)
    required_steps.extend(fulfillment_steps)
    draft_handoff = _draft_handoff(ticket, owner, normalized_priority, required_steps, review_reasons)

    return HandoffDecision(
        ticket_id=ticket.ticket_id,
        owner=owner,
        normalized_priority=normalized_priority,
        sla=contract["sla"][normalized_priority],
        recommended_fulfillment=fulfillment,
        part_delivery=part_delivery,
        serial_number_required=serial_required,
        required_steps=tuple(required_steps),
        closure_requirements=tuple(closure_requirements),
        routing_notes=routing_notes,
        review_reasons=tuple(review_reasons),
        requires_human_review=bool(review_reasons),
        requires_human_approval=True,
        execution_state="draft_only",
        draft_handoff=draft_handoff,
    )


def _contract_for(contract_id: str) -> dict[str, object]:
    try:
        return CONTRACTS[contract_id]
    except KeyError as error:
        raise ValueError(f"Unknown synthetic contract profile: {contract_id}") from error


def _normalize_priority(ticket: Ticket, contract: dict[str, object]) -> tuple[str, list[str]]:
    allowed_priorities = contract["allowed_priorities"]
    if ticket.priority in allowed_priorities:
        return ticket.priority, []
    return "P2", [f"contract does not offer {ticket.priority}"]


def _route_ticket(category: str) -> tuple[str, bool, str]:
    if category in _PLATFORM_ROUTES:
        return _PLATFORM_ROUTES[category]
    return (
        "field_service_dispatch",
        True,
        "Route to field service dispatch with the device and service history attached.",
    )


def _base_steps(ticket: Ticket, owner: str) -> list[str]:
    if owner != "field_service_dispatch":
        return ["preserve the original ticket cross-reference", "confirm the platform owner accepts the case"]
    steps = ["confirm device and service history", "confirm site access and scheduling window"]
    if ticket.replacement_needed:
        steps.append("validate replacement compatibility before scheduling")
    return steps


def _plan_fulfillment(
    ticket: Ticket, contract: dict[str, object]
) -> tuple[str, str, list[str], list[str]]:
    if not ticket.replacement_needed:
        return (
            "diagnostic_follow_up",
            "overnight_part_order_if_needed",
            [],
            ["evidence supports the recommended repair", "customer update is reviewed"],
        )

    if contract["hot_swap"]:
        delivery = "local_courier_candidate" if ticket.part_available_locally else "overnight_part_order"
        return (
            "local_hot_swap",
            delivery,
            ["validate hot-swap compatibility before scheduling"],
            ["printing is restored", "customer update is reviewed"],
        )

    required_steps = [
        "register the replacement IP",
        "reconfigure managed print access",
        "reconfigure document workflow connections",
        "verify all dependent services after the replacement",
    ]
    return (
        "replacement_with_reconfiguration",
        "overnight_part_order",
        required_steps,
        ["verify the managed print workflow", "customer update is reviewed"],
    )


def _draft_handoff(
    ticket: Ticket,
    owner: str,
    priority: str,
    required_steps: list[str],
    review_reasons: list[str],
) -> str:
    review_text = "; ".join(review_reasons) if review_reasons else "human approval required before action"
    step_text = "; ".join(required_steps)
    return (
        f"Draft handoff for {ticket.ticket_id}: assign to {owner} at {priority}; "
        f"complete: {step_text}. Draft customer update is required. Review: {review_text}."
    )
