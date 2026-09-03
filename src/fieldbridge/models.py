"""Immutable, synthetic-only records used by FieldBridge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ticket:
    """A normalized synthetic service ticket.

    The model intentionally contains no real customer identifier, contact detail,
    address, credential, or production system reference.
    """

    ticket_id: str
    contract_id: str
    priority: str
    category: str
    summary: str
    serial_number: str | None
    replacement_needed: bool
    part_available_locally: bool
    site_access: str
    actual_user_known: bool = True


@dataclass(frozen=True)
class HandoffDecision:
    """A reviewable recommendation. FieldBridge never executes a real action."""

    ticket_id: str
    owner: str
    normalized_priority: str
    sla: str
    recommended_fulfillment: str
    part_delivery: str
    serial_number_required: bool
    required_steps: tuple[str, ...]
    closure_requirements: tuple[str, ...]
    routing_notes: str
    review_reasons: tuple[str, ...]
    requires_human_review: bool
    requires_human_approval: bool
    execution_state: str
    draft_handoff: str

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe data for the CLI, API, and Strands tools."""

        return {
            "ticket_id": self.ticket_id,
            "owner": self.owner,
            "normalized_priority": self.normalized_priority,
            "sla": self.sla,
            "recommended_fulfillment": self.recommended_fulfillment,
            "part_delivery": self.part_delivery,
            "serial_number_required": self.serial_number_required,
            "required_steps": list(self.required_steps),
            "closure_requirements": list(self.closure_requirements),
            "routing_notes": self.routing_notes,
            "review_reasons": list(self.review_reasons),
            "requires_human_review": self.requires_human_review,
            "requires_human_approval": self.requires_human_approval,
            "execution_state": self.execution_state,
            "draft_handoff": self.draft_handoff,
        }
