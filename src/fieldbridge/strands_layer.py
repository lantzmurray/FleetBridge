"""Strands investigation layer around FieldBridge's deterministic safety floor."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from time import monotonic
from typing import Any
from uuid import uuid4

from .engine import decision_card_for
from .evidence import get_case, known_facts
from .models import (
    AgentInvestigation,
    ExtractedFacts,
    InvestigationResult,
    RawTicket,
    ToolTraceEvent,
)
from .tools import (
    fulfillment_requirements as inspect_fulfillment,
)
from .tools import (
    inspect_contract,
    inspect_routing,
)
from .tools import (
    load_case as inspect_case,
)
from .tools import (
    safety_boundary as inspect_safety_boundary,
)
from .tools import (
    service_history as inspect_service_history,
)
from .tools import (
    site_access_policy as inspect_site_access,
)
from .tools import (
    validate_draft as validate_agent_draft,
)

DEFAULT_MODEL_ID = "us.amazon.nova-lite-v1:0"
TRACEABLE_TOOL_NAMES = frozenset(
    {
        "load_case",
        "contract_policy",
        "service_history",
        "site_access_policy",
        "routing_policy",
        "fulfillment_requirements",
        "validate_draft",
        "safety_boundary",
    }
)
SYSTEM_PROMPT = """You are FieldBridge, a public-safe field-service handoff agent.
Investigate only the supplied approved synthetic case. Always use load_case,
contract_policy, safety_boundary, and validate_draft. For a device replacement,
also use service_history, site_access_policy, and fulfillment_requirements. For a
fax platform issue, use routing_policy instead. Treat deterministic tool output
as authoritative. Never invent identifiers, contacts, access rules, inventory,
SLAs, or completion evidence. Preserve every unstated fact as unknown. Call
safety_boundary before validate_draft. If validate_draft reports an
authoritative_replacement, copy its decision_card, extracted_facts, and
evidence_gaps exactly into final output and do not retry the validation tool.
The deterministic replacement is the accepted human-review draft.
Never dispatch, order parts, contact a customer, modify a ticket, close a ticket,
or claim that any real action occurred.
"""


class SanitizedToolTrace:
    """Collect tool name/status/timing while discarding inputs, outputs, and reasoning."""

    def __init__(self, correlation_id: str) -> None:
        self.correlation_id = correlation_id
        self._events: list[ToolTraceEvent] = []

    def __call__(self, **kwargs: Any) -> None:
        """Consume only safe tool-start metadata from a Strands callback event."""

        event = kwargs.get("event")
        if not isinstance(event, dict):
            return
        tool_use = event.get("contentBlockStart", {}).get("start", {}).get("toolUse")
        if not isinstance(tool_use, dict):
            return
        tool_name = tool_use.get("name")
        if isinstance(tool_name, str) and tool_name in TRACEABLE_TOOL_NAMES:
            self._events.append(
                ToolTraceEvent(
                    tool_name=tool_name,
                    status="requested",
                    duration_ms=0,
                    correlation_id=self.correlation_id,
                )
            )

    def record_completion(self, tool_name: str, status: str, duration_ms: int) -> None:
        """Replace the latest matching request with its sanitized completion."""

        if tool_name not in TRACEABLE_TOOL_NAMES:
            return
        completed = ToolTraceEvent(
            tool_name=tool_name,
            status=status,
            duration_ms=max(0, duration_ms),
            correlation_id=self.correlation_id,
        )
        for index in range(len(self._events) - 1, -1, -1):
            event = self._events[index]
            if event.tool_name == tool_name and event.status == "requested":
                self._events[index] = completed
                return
        self._events.append(completed)

    def events(self) -> tuple[ToolTraceEvent, ...]:
        return tuple(self._events)

    def as_dicts(self) -> list[dict[str, object]]:
        return [event.model_dump(mode="json") for event in self._events]


def build_agent(
    *,
    model: Any | None = None,
    trace: SanitizedToolTrace | None = None,
) -> Any:
    """Build the bounded Strands agent with an explicit Bedrock model configuration."""

    try:
        from strands import Agent, tool
        from strands.models import BedrockModel
    except ImportError as error:
        raise RuntimeError(
            "Install the project dependencies to enable the Strands demo."
        ) from error

    if model is None:
        model_id = os.getenv("BEDROCK_MODEL_ID")
        if not model_id:
            raise RuntimeError(
                f"BEDROCK_MODEL_ID is required for live mode (recommended: {DEFAULT_MODEL_ID})."
            )
        model = BedrockModel(
            model_id=model_id,
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            max_tokens=1800,
            temperature=0,
        )

    safe_trace = trace or SanitizedToolTrace(correlation_id=f"corr-{uuid4().hex}")

    def timed(tool_name: str, operation: Callable[[], dict[str, object]]) -> str:
        started = monotonic()
        try:
            value = operation()
        except Exception:
            safe_trace.record_completion(tool_name, "error", _elapsed_ms(started))
            raise
        safe_trace.record_completion(tool_name, "ok", _elapsed_ms(started))
        return json.dumps(value, sort_keys=True)

    @tool
    def load_case(ticket_id: str) -> str:
        """Load one approved bounded synthetic case by ticket ID."""

        return timed("load_case", lambda: inspect_case(ticket_id))

    @tool
    def contract_policy(contract_id: str) -> str:
        """Inspect one approved synthetic contract profile."""

        return timed("contract_policy", lambda: inspect_contract(contract_id))

    @tool
    def service_history(ticket_id: str) -> str:
        """Inspect bounded synthetic service history for one case."""

        return timed("service_history", lambda: inspect_service_history(ticket_id))

    @tool
    def site_access_policy(site_ref: str) -> str:
        """Inspect the approved synthetic site-access policy."""

        return timed("site_access_policy", lambda: inspect_site_access(site_ref))

    @tool
    def routing_policy(category: str) -> str:
        """Inspect the deterministic internal owner for a supported category."""

        return timed("routing_policy", lambda: inspect_routing(category))

    @tool
    def fulfillment_requirements(contract_id: str, ticket_id: str) -> str:
        """Inspect deterministic fulfillment, restoration, and closure requirements."""

        return timed(
            "fulfillment_requirements",
            lambda: inspect_fulfillment(contract_id, ticket_id),
        )

    @tool
    def validate_draft(ticket_id: str, proposal_json: str) -> str:
        """Validate a proposed decision card against authoritative policy."""

        def operation() -> dict[str, object]:
            try:
                proposal = json.loads(proposal_json)
            except json.JSONDecodeError as error:
                raise ValueError("proposal_json must be valid JSON") from error
            return _validation_feedback(ticket_id, proposal)

        return timed("validate_draft", operation)

    @tool
    def safety_boundary() -> str:
        """Read FieldBridge's non-negotiable no-action boundary."""

        return timed("safety_boundary", inspect_safety_boundary)

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            load_case,
            contract_policy,
            service_history,
            site_access_policy,
            routing_policy,
            fulfillment_requirements,
            validate_draft,
            safety_boundary,
        ],
        structured_output_model=AgentInvestigation,
        callback_handler=safe_trace,
        trace_attributes={"fieldbridge.correlation_id": safe_trace.correlation_id},
    )
    agent._fieldbridge_trace = safe_trace
    return agent


def run_investigation(
    raw_ticket: RawTicket,
    *,
    agent: Any | None = None,
    correlation_id: str | None = None,
) -> InvestigationResult:
    """Run Strands and revalidate its structured proposal, or return a labeled fallback."""

    approved = get_case(raw_ticket.ticket_id)
    if approved != raw_ticket:
        raise ValueError("raw_ticket must match an approved immutable synthetic scenario")
    correlation = correlation_id or f"corr-{uuid4().hex}"
    trace = SanitizedToolTrace(correlation)
    active_agent = agent
    try:
        if active_agent is None:
            active_agent = build_agent(trace=trace)
        else:
            supplied_trace = getattr(active_agent, "_fieldbridge_trace", None)
            if isinstance(supplied_trace, SanitizedToolTrace):
                trace = supplied_trace
                correlation = supplied_trace.correlation_id
        prompt = _investigation_prompt(raw_ticket)
        if hasattr(active_agent, "_fieldbridge_trace"):
            result = active_agent(
                prompt,
                limits={"turns": 12, "output_tokens": 5000, "total_tokens": 30000},
            )
        else:
            result = active_agent(prompt)
        structured = getattr(result, "structured_output", None)
        if not isinstance(structured, AgentInvestigation):
            raise TypeError("model did not return the required AgentInvestigation schema")
        facts = _validated_facts(raw_ticket.ticket_id, structured.extracted_facts)
        authoritative_card = decision_card_for(raw_ticket, facts)
        # The model proposal is advisory. The validated deterministic card is the
        # only decision packet returned to a coordinator.
        validate_agent_draft(
            raw_ticket.ticket_id,
            authoritative_card.model_dump(mode="json"),
        )
        _require_completed_tool_path(raw_ticket.ticket_id, active_agent, trace)
        return InvestigationResult(
            mode="live",
            model_id=_model_id(active_agent),
            correlation_id=correlation,
            extracted_facts=facts,
            decision_card=authoritative_card,
            tool_trace=trace.events(),
        )
    except Exception:  # noqa: BLE001 -- every live-provider failure must degrade safely
        facts = known_facts(raw_ticket.ticket_id)
        fallback = decision_card_for(
            raw_ticket,
            facts,
            execution_state="DEGRADED_REVIEW_REQUIRED",
            additional_review_reasons=("model invocation unavailable",),
        )
        return InvestigationResult(
            mode="degraded",
            model_id=_model_id(active_agent),
            correlation_id=correlation,
            extracted_facts=facts,
            decision_card=fallback,
            tool_trace=trace.events(),
        )


def _validated_facts(ticket_id: str, proposed: ExtractedFacts) -> ExtractedFacts:
    authoritative = known_facts(ticket_id)
    proposed_user_known = proposed.actual_user_known
    if (
        proposed_user_known is None
        and authoritative.actual_user_known is False
        and "actual_user" in proposed.unknown_fields
    ):
        proposed_user_known = False
    normalized_proposed = proposed.model_copy(
        update={
            "actual_user_known": proposed_user_known,
            "unknown_fields": tuple(sorted(proposed.unknown_fields)),
        }
    )
    normalized_authoritative = authoritative.model_copy(
        update={"unknown_fields": tuple(sorted(authoritative.unknown_fields))}
    )
    if normalized_proposed != normalized_authoritative:
        raise ValueError("model facts conflict with approved synthetic evidence")
    return authoritative


def _validation_feedback(ticket_id: str, proposal: Any) -> dict[str, object]:
    """Give the model bounded synthetic correction data without weakening policy."""

    facts = known_facts(ticket_id)
    card = decision_card_for(get_case(ticket_id), facts)
    bundle: dict[str, object] = {
        "decision_card": card.model_dump(mode="json"),
        "extracted_facts": facts.model_dump(mode="json"),
        "evidence_gaps": card.model_dump(mode="json")["missing_evidence"],
    }
    try:
        validate_agent_draft(ticket_id, proposal)
        return {
            "validation_status": "accepted_for_human_review",
            "proposal_status": "accepted",
            **bundle,
        }
    except (TypeError, ValueError) as error:
        return {
            "validation_status": "authoritative_replacement",
            "proposal_status": "rejected",
            "reason_code": "authoritative_policy_conflict",
            "reason": str(error),
            **bundle,
        }


def _require_completed_tool_path(
    ticket_id: str,
    agent: Any,
    trace: SanitizedToolTrace,
) -> None:
    """Reject a traceable live result that skipped required evidence or validation."""

    if not hasattr(agent, "_fieldbridge_trace"):
        return
    common = {"load_case", "contract_policy", "validate_draft", "safety_boundary"}
    scenario_specific = {
        "FB-DEMO-001": {
            "service_history",
            "site_access_policy",
            "fulfillment_requirements",
        },
        "FB-DEMO-002": {"routing_policy"},
    }
    required = common | scenario_specific.get(ticket_id, set())
    completed = {event.tool_name for event in trace.events() if event.status == "ok"}
    missing = sorted(required - completed)
    if missing:
        raise ValueError("agent skipped required tool path: " + ", ".join(missing))


def _investigation_prompt(raw_ticket: RawTicket) -> str:
    if raw_ticket.ticket_id == "FB-DEMO-001":
        tool_plan = (
            "1 load_case; 2 contract_policy; 3 service_history; "
            "4 site_access_policy; 5 fulfillment_requirements; "
            "6 safety_boundary; 7 validate_draft exactly once"
        )
    elif raw_ticket.ticket_id == "FB-DEMO-002":
        tool_plan = (
            "1 load_case; 2 contract_policy; 3 routing_policy; "
            "4 safety_boundary; 5 validate_draft exactly once"
        )
    else:  # pragma: no cover - approved cases are checked before prompt construction
        raise ValueError("ticket is outside the approved investigation catalog")
    return (
        "Execute this scenario tool plan in the numbered order and do not skip or reorder "
        f"steps: {tool_plan}. Do not call validate_draft before the preceding evidence tools. "
        "If validation returns authoritative_replacement, copy its decision_card, "
        "extracted_facts, and evidence_gaps into the final AgentInvestigation and do not call "
        "validate_draft again. Do not infer any fact that "
        "an evidence tool does not support.\n"
        + raw_ticket.model_dump_json()
    )


def _model_id(agent: Any | None) -> str | None:
    model = getattr(agent, "model", None)
    get_config = getattr(model, "get_config", None)
    if callable(get_config):
        config = get_config()
        value = config.get("model_id")
        return value if isinstance(value, str) else None
    return os.getenv("BEDROCK_MODEL_ID")


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))
