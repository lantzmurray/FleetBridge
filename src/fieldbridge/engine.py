"""Deterministic contract and routing policy for FieldBridge.

The deterministic layer is the safety floor. A Strands agent may inspect this
output and draft an explanation, but cannot alter contract rules or execute a
dispatch, customer contact, part order, or closure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import DecisionCard, EvidenceGap, ExtractedFacts, HandoffDecision, RawTicket, Ticket

CONTRACTS = {
    "northstar-health": {
        "allowed_priorities": {"P1", "P2"},
        "sla": {"P1": "resolve within 4 hours", "P2": "end of next business day"},
        "hot_swap": True,
        "local_courier": True,
        "timezone": "America/New_York",
    },
    "civic-research": {
        "allowed_priorities": {"P2"},
        "sla": {"P2": "end of next business day"},
        "hot_swap": False,
        "local_courier": False,
        "timezone": "America/New_York",
    },
    "metro-financial": {
        "allowed_priorities": {"P2"},
        "sla": {"P2": "end of next business day"},
        "hot_swap": False,
        "local_courier": False,
        "timezone": "America/New_York",
    },
}

BLOCKED_ACTIONS = ("dispatch", "order_parts", "contact_customer", "modify_ticket", "close_ticket")


@dataclass(frozen=True)
class BusinessDayCalendar:
    """Small injectable calendar for deterministic SLA calculations."""

    holidays: frozenset[date] = frozenset()

    def is_business_day(self, value: date) -> bool:
        return value.weekday() < 5 and value not in self.holidays

    def next_business_day(self, value: date) -> date:
        candidate = value + timedelta(days=1)
        while not self.is_business_day(candidate):
            candidate += timedelta(days=1)
        return candidate


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

_CONTRACTED_TEAMS = {
    "northstar-health": "Northstar Health contracted field service",
    "civic-research": "Civic Research contracted field service",
    "metro-financial": "Metro Financial contracted platform support",
}

SUPPORTED_CATEGORIES = frozenset(
    {"device_print_unavailable", "enterprise_fax", "managed_print_access"}
)


def evaluate_ticket(
    ticket: Ticket,
    *,
    clock: Callable[[], datetime] | None = None,
    business_calendar: BusinessDayCalendar | None = None,
) -> HandoffDecision:
    """Produce a public-safe, draft-only handoff decision for one ticket."""

    contract = _contract_for(ticket.contract_id)
    normalized_priority, review_reasons = _normalize_priority(ticket, contract)
    if ticket.site_access == "unknown":
        review_reasons.append("site access must be confirmed")

    owner, serial_required, routing_notes = _route_ticket(ticket.category)
    routing = _routing_profile(ticket, owner)
    required_steps = _base_steps(ticket, owner)
    if serial_required and ticket.serial_number is None:
        required_steps.append("recover the synthetic device serial")
        review_reasons.append("device serial evidence is missing")
    if not ticket.actual_user_known:
        required_steps.extend(("recover an actual-user contact", "draft a customer update"))
        review_reasons.append("actual-user contact is missing")

    fulfillment, part_delivery, fulfillment_steps, closure_requirements = _plan_fulfillment(
        ticket, contract
    )
    required_steps.extend(fulfillment_steps)
    draft_handoff = _draft_handoff(
        ticket, owner, normalized_priority, required_steps, review_reasons
    )
    reported_at = ticket.reported_at or _utc_now(clock)
    timezone_name = str(contract["timezone"])
    deadline = compute_sla_deadline(
        reported_at,
        normalized_priority,
        timezone_name=timezone_name,
        business_calendar=business_calendar,
    )

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
        sla_deadline=deadline.isoformat(),
        sla_timezone=timezone_name,
        contracted_team=routing["contracted_team"],
        internal_team=owner,
        point_of_contact=routing["point_of_contact"],
        schedule_recommendation=routing["schedule_recommendation"],
        escalation_recommendation=routing["escalation_recommendation"],
        dispatch_recommendation=routing["dispatch_recommendation"],
    )


def compute_sla_deadline(
    reported_at: datetime,
    priority: str,
    *,
    timezone_name: str,
    business_calendar: BusinessDayCalendar | None = None,
) -> datetime:
    """Convert contract SLA language into a deterministic, timezone-aware deadline."""

    if reported_at.tzinfo is None or reported_at.utcoffset() is None:
        raise ValueError("reported_at must include a timezone")
    local_reported = reported_at.astimezone(ZoneInfo(timezone_name))
    if priority == "P1":
        return local_reported + timedelta(hours=4)
    if priority != "P2":
        raise ValueError("priority must be P1 or P2")
    calendar = business_calendar or BusinessDayCalendar()
    due_date = calendar.next_business_day(local_reported.date())
    return datetime.combine(due_date, time(17, 0), ZoneInfo(timezone_name))


def decision_card_for(
    raw_ticket: RawTicket,
    facts: ExtractedFacts,
    *,
    clock: Callable[[], datetime] | None = None,
    business_calendar: BusinessDayCalendar | None = None,
    execution_state: str | None = None,
    additional_review_reasons: tuple[str, ...] = (),
) -> DecisionCard:
    """Rebuild an agent proposal from deterministic policy and fixture evidence."""

    category = facts.category or "device_print_unavailable"
    requested_priority = facts.requested_priority or "P2"
    ticket = Ticket(
        ticket_id=raw_ticket.ticket_id,
        contract_id=raw_ticket.contract_id,
        priority=requested_priority,
        category=category,
        summary=raw_ticket.note,
        serial_number=facts.serial_number,
        replacement_needed=facts.replacement_needed is True,
        part_available_locally=facts.part_available_locally is True,
        site_access=facts.site_access or "unknown",
        actual_user_known=facts.actual_user_known is True,
        reported_at=raw_ticket.reported_at,
    )
    decision = evaluate_ticket(
        ticket,
        clock=clock,
        business_calendar=business_calendar,
    )
    missing_evidence = _evidence_gaps(facts, decision.serial_number_required)
    review_reasons = tuple(dict.fromkeys((*decision.review_reasons, *additional_review_reasons)))
    requires_review = bool(review_reasons or missing_evidence)
    resolved_state = execution_state or ("REVIEW_REQUIRED" if requires_review else "PREPARED")
    return DecisionCard(
        ticket_id=raw_ticket.ticket_id,
        requested_priority=facts.requested_priority,
        allowed_priority=decision.normalized_priority,
        sla=decision.sla,
        sla_deadline=datetime.fromisoformat(decision.sla_deadline),
        sla_timezone=decision.sla_timezone,
        owner=decision.owner,
        missing_evidence=missing_evidence,
        access_constraint=_access_constraint(facts.site_access),
        fulfillment_plan=decision.recommended_fulfillment,
        part_delivery=decision.part_delivery,
        restoration_steps=decision.required_steps,
        closure_proof=decision.closure_requirements,
        blocked_actions=BLOCKED_ACTIONS,
        review_reasons=review_reasons,
        requires_human_review=requires_review,
        requires_human_approval=True,
        execution_state=resolved_state,
        contracted_team=decision.contracted_team,
        internal_team=decision.internal_team,
        point_of_contact=decision.point_of_contact,
        schedule_recommendation=decision.schedule_recommendation,
        escalation_recommendation=decision.escalation_recommendation,
        dispatch_recommendation=decision.dispatch_recommendation,
    )


def _evidence_gaps(facts: ExtractedFacts, serial_number_required: bool) -> tuple[EvidenceGap, ...]:
    gaps: list[EvidenceGap] = []
    if serial_number_required and facts.serial_number is None:
        gaps.append(
            EvidenceGap(
                field="serial_number",
                reason="No approved synthetic device serial is present.",
                required_for="field-service dispatch draft",
            )
        )
    if facts.actual_user_known is not True:
        gaps.append(
            EvidenceGap(
                field="actual_user",
                reason="The affected user is not identified in the synthetic evidence.",
                required_for="customer update draft",
            )
        )
    if facts.site_access in {None, "unknown"}:
        gaps.append(
            EvidenceGap(
                field="site_access",
                reason="The access policy is unknown.",
                required_for="visit scheduling draft",
            )
        )
    return tuple(gaps)


def _access_constraint(access: str | None) -> str:
    constraints = {
        "escorted": "An escort must be confirmed before scheduling.",
        "chaperone_required": "A site-provided chaperone must be confirmed before scheduling.",
        "stationed": "Onsite support is stationed.",
        "unknown": "Site access must be confirmed before scheduling.",
        None: "Site access must be confirmed before scheduling.",
    }
    return constraints[access]


def _utc_now(clock: Callable[[], datetime] | None) -> datetime:
    value = clock() if clock else datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value


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


def _routing_profile(ticket: Ticket, owner: str) -> dict[str, str]:
    """Prepare routing, scheduling, and escalation guidance without executing it."""

    contracted_team = _CONTRACTED_TEAMS.get(ticket.contract_id, "approved contracted team")
    platform_route = owner != "field_service_dispatch"
    keywords = ("network", "vpn", "workflow", "fax", "print server", "managed print")
    network_signal = platform_route or any(keyword in ticket.summary.lower() for keyword in keywords)
    if platform_route:
        schedule = "Remote queue; no onsite visit recommended for this platform case."
        contact = "Synthetic platform owner"
        dispatch = "Do not dispatch onsite; route to the dedicated internal team for human review."
    else:
        schedule = "Next available onsite window after access and chaperone confirmation."
        contact = "Synthetic site coordinator"
        dispatch = "Human coordinator decides whether an onsite technician is dispatched."
    escalation = (
        "Eligible for dedicated client-network/platform review when customer-network evidence "
        "or an approved routing keyword is present."
        if network_signal
        else "No dedicated-team escalation identified; keep with the contracted field-service team."
    )
    return {
        "contracted_team": contracted_team,
        "point_of_contact": contact,
        "schedule_recommendation": schedule,
        "escalation_recommendation": escalation,
        "dispatch_recommendation": dispatch,
    }


def _base_steps(ticket: Ticket, owner: str) -> list[str]:
    if owner != "field_service_dispatch":
        return [
            "preserve the original ticket cross-reference",
            "confirm the platform owner accepts the case",
        ]
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
        delivery = (
            "local_courier_candidate" if ticket.part_available_locally else "overnight_part_order"
        )
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
    review_text = (
        "; ".join(review_reasons) if review_reasons else "human approval required before action"
    )
    step_text = "; ".join(required_steps)
    return (
        f"Draft handoff for {ticket.ticket_id}: assign to {owner} at {priority}; "
        f"complete: {step_text}. Draft customer update is required. Review: {review_text}."
    )
