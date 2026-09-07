"""Immutable, synthetic-only records used by FieldBridge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _FrozenModel(BaseModel):
    """Strict base model for data that may cross the model boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RawTicket(_FrozenModel):
    """A bounded thin ticket presented to the investigating agent."""

    ticket_id: str = Field(pattern=r"^FB-", max_length=64)
    contract_id: str = Field(min_length=1, max_length=64)
    reported_at: datetime
    note: str = Field(min_length=1, max_length=1000)
    device_ref: str | None = Field(default=None, max_length=80)
    site_ref: str = Field(min_length=1, max_length=80)
    unknown_fields: tuple[str, ...] = ()

    @field_validator("reported_at")
    @classmethod
    def reported_at_must_have_timezone(cls, value: datetime) -> datetime:
        """Reject ambiguous timestamps at the system boundary."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reported_at must include a timezone")
        return value


class ExtractedFacts(_FrozenModel):
    """Model-interpreted facts; missing evidence remains explicitly unknown."""

    requested_priority: Literal["P1", "P2"] | None = None
    category: (
        Literal["device_print_unavailable", "enterprise_fax", "managed_print_access"] | None
    ) = None
    replacement_needed: bool | None = None
    serial_number: str | None = Field(default=None, max_length=80)
    actual_user_known: bool | None = None
    site_access: Literal["escorted", "chaperone_required", "stationed", "unknown"] | None = None
    part_available_locally: bool | None = None
    unknown_fields: tuple[str, ...] = ()


class EvidenceGap(_FrozenModel):
    """One fact or authority the agent cannot safely resolve itself."""

    field: str
    reason: str
    required_for: str


class ToolTraceEvent(_FrozenModel):
    """Sanitized tool metadata; arguments, results, and reasoning are excluded."""

    tool_name: str
    status: Literal["requested", "ok", "error"]
    duration_ms: int = Field(ge=0)
    correlation_id: str


class DecisionCard(_FrozenModel):
    """Evidence-linked, deterministic decision packet for coordinator review."""

    ticket_id: str
    requested_priority: Literal["P1", "P2"] | None
    allowed_priority: Literal["P1", "P2"]
    sla: str
    sla_deadline: datetime
    sla_timezone: str
    owner: str
    missing_evidence: tuple[EvidenceGap, ...]
    access_constraint: str
    fulfillment_plan: str
    part_delivery: str
    restoration_steps: tuple[str, ...]
    closure_proof: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    review_reasons: tuple[str, ...]
    requires_human_review: bool
    requires_human_approval: bool = True
    execution_state: Literal["PREPARED", "REVIEW_REQUIRED", "DEGRADED_REVIEW_REQUIRED", "FAILED"]
    contracted_team: str = "unknown"
    internal_team: str = "unknown"
    point_of_contact: str = "unknown"
    schedule_recommendation: str = "schedule after human review"
    escalation_recommendation: str = "no dedicated-team escalation identified"
    dispatch_recommendation: str = "human approval required before dispatch"


class AgentInvestigation(_FrozenModel):
    """Schema requested from Strands before deterministic revalidation."""

    extracted_facts: ExtractedFacts
    evidence_gaps: tuple[EvidenceGap, ...]
    decision_card: DecisionCard


class InvestigationResult(_FrozenModel):
    """Final run output with explicit live/degraded provenance."""

    mode: Literal["live", "degraded"]
    model_id: str | None
    correlation_id: str
    extracted_facts: ExtractedFacts
    decision_card: DecisionCard
    tool_trace: tuple[ToolTraceEvent, ...]


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
    reported_at: datetime | None = None


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
    sla_deadline: str = ""
    sla_timezone: str = "UTC"
    contracted_team: str = "unknown"
    internal_team: str = "unknown"
    point_of_contact: str = "unknown"
    schedule_recommendation: str = "schedule after human review"
    escalation_recommendation: str = "no dedicated-team escalation identified"
    dispatch_recommendation: str = "human approval required before dispatch"

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe data for the CLI, API, and Strands tools."""

        return {
            "ticket_id": self.ticket_id,
            "owner": self.owner,
            "normalized_priority": self.normalized_priority,
            "sla": self.sla,
            "sla_deadline": self.sla_deadline,
            "sla_timezone": self.sla_timezone,
            "contracted_team": self.contracted_team,
            "internal_team": self.internal_team,
            "point_of_contact": self.point_of_contact,
            "schedule_recommendation": self.schedule_recommendation,
            "escalation_recommendation": self.escalation_recommendation,
            "dispatch_recommendation": self.dispatch_recommendation,
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
