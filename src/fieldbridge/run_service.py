"""Application service joining evidence, Strands investigation, and workflow state."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from .engine import decision_card_for
from .evidence import get_scenario, known_facts, list_scenarios
from .models import DecisionCard, InvestigationResult, RawTicket
from .strands_layer import run_investigation
from .workflow import (
    AnalysisOutcome,
    ReviewDecision,
    ReviewReason,
    RunRecord,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowService,
    WorkflowState,
    WorkflowValidationError,
    build_demo_workflow_service,
)


class RunNotFoundError(LookupError):
    """Raised when a public synthetic run does not exist."""


class ScenarioNotFoundError(LookupError):
    """Raised when a scenario is outside the approved public set."""


class RunConflictError(RuntimeError):
    """Raised when a review would violate the state machine."""


class RunValidationError(ValueError):
    """Raised when a bounded public run value is malformed."""


_SCENARIO_COPY = {
    "replacement-pressure": {
        "title": "The replacement trap",
        "eyebrow": "Replacement request · six hidden dependencies",
        "contract": "Civic Research · Field coverage",
        "requester": "Site operations coordinator",
        "account": "Civic Research",
        "channel": "Portal",
        "received_at": "Today · 3:30 PM ET",
        "sla_preview": "Due today · 5:00 PM",
        "serial": "Unknown",
        "application": "Managed print",
        "contact": "Synthetic site coordinator",
        "client": "Civic Research",
        "due": "Due today · 5:00 PM",
        "assigned_team": "Field service dispatch",
        "queue_status": "OPEN",
    },
    "fax-routing": {
        "title": "The routing trap",
        "eyebrow": "Platform issue · no serial required",
        "contract": "Metro Financial · Platform coverage",
        "requester": "Business systems analyst",
        "account": "Metro Financial",
        "channel": "Email",
        "received_at": "Today · 11:00 AM ET",
        "sla_preview": "Due today · 5:00 PM",
        "serial": "N/A",
        "application": "Enterprise fax",
        "contact": "Synthetic platform owner",
        "client": "Metro Financial",
        "due": "Due today · 5:00 PM",
        "assigned_team": "Enterprise fax support",
        "queue_status": "PREPARED",
    },
}

_REVIEW_DECISIONS = {
    "approve": ReviewDecision.APPROVE_DRAFT,
    "request_changes": ReviewDecision.REQUEST_CHANGES,
    "reject": ReviewDecision.REJECT,
}

_REVIEW_REASONS = {
    "evidence_verified": ReviewReason.READY_FOR_HANDOFF,
    "insufficient_evidence": ReviewReason.MISSING_EVIDENCE,
    "policy_exception": ReviewReason.POLICY_EXCEPTION,
    "routing_correction": ReviewReason.INCORRECT_ROUTING,
}

_EVENT_LABELS = {
    "RUN_CREATED": "Synthetic run created",
    "ANALYSIS_STARTED": "Bounded investigation started",
    "ANALYSIS_COMPLETED": "Decision validated against authoritative policy",
    "EVIDENCE_CORRECTED": "Approved synthetic evidence added",
    "REVIEW_RECORDED": "Human review recorded",
}

_SCENARIO_BY_TICKET = {
    "FB-DEMO-001": "replacement-pressure",
    "FB-DEMO-002": "fax-routing",
}

Investigator = Callable[[RawTicket, str], InvestigationResult]


class AgentCoreInvestigator:
    """Invoke the private AgentCore worker through its IAM-authenticated runtime API."""

    def __init__(
        self,
        *,
        runtime_arn: str,
        client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        if not runtime_arn or runtime_arn == "UNKNOWN":
            raise ValueError("a verified AgentCore runtime ARN is required")
        if client is None:
            import boto3

            client = boto3.client(
                "bedrock-agentcore",
                region_name=region_name or os.getenv("AWS_REGION", "us-east-1"),
            )
        self._runtime_arn = runtime_arn
        self._client = client

    def __call__(self, raw_ticket: RawTicket, correlation_id: str) -> InvestigationResult:
        scenario_id = _SCENARIO_BY_TICKET.get(raw_ticket.ticket_id)
        if scenario_id is None:
            raise ValueError("ticket is not an approved AgentCore scenario")
        response = self._client.invoke_agent_runtime(
            agentRuntimeArn=self._runtime_arn,
            runtimeSessionId=hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:40],
            qualifier="DEFAULT",
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(
                {"scenario_id": scenario_id, "correlation_id": correlation_id}
            ).encode("utf-8"),
        )
        if int(response.get("statusCode", 500)) != 200:
            raise RuntimeError("AgentCore investigation failed")
        body = response.get("response")
        read = getattr(body, "read", None)
        if not callable(read):
            raise TypeError("AgentCore returned an invalid response")
        return InvestigationResult.model_validate_json(read())


class LocalRunService:
    """Local coordinator workflow using the same core as the live agent path."""

    def __init__(
        self,
        workflow: WorkflowService | None = None,
        investigator: Investigator | None = None,
        *,
        rehearsal: bool = False,
    ) -> None:
        self._workflow = workflow or build_demo_workflow_service()
        self._investigator = investigator or _default_investigator
        self._rehearsal = rehearsal

    def list_scenarios(self) -> list[dict[str, object]]:
        """Return presentation metadata for the fixed synthetic catalog."""

        catalog: list[dict[str, object]] = []
        for item in list_scenarios():
            scenario_id = str(item["scenario_id"])
            copy = _SCENARIO_COPY[scenario_id]
            catalog.append(
                {
                    "id": scenario_id,
                    "ticket_id": item["ticket_id"],
                    "title": copy["title"],
                    "eyebrow": copy["eyebrow"],
                    "summary": item["note"],
                    "contract": copy["contract"],
                    "requester": copy["requester"],
                    "account": copy["account"],
                    "channel": copy["channel"],
                    "received_at": copy["received_at"],
                    "sla_preview": copy["sla_preview"],
                    "serial": copy["serial"],
                    "application": copy["application"],
                    "contact": copy["contact"],
                    "client": copy["client"],
                    "due": copy["due"],
                    "assigned_team": copy["assigned_team"],
                    "queue_status": copy["queue_status"],
                    "synthetic": True,
                }
            )
        return catalog

    def reset(self) -> None:
        try:
            self._workflow.reset_demo()
        except WorkflowConflictError as error:
            raise RunConflictError from error

    def create_run(self, scenario_id: str, idempotency_key: str) -> dict[str, object]:
        try:
            raw_ticket = get_scenario(scenario_id)
        except ValueError as error:
            raise ScenarioNotFoundError from error

        try:
            run = self._workflow.create_run(scenario_id, idempotency_key)
        except WorkflowValidationError as error:
            raise RunValidationError from error
        except WorkflowConflictError as error:
            raise RunConflictError from error
        if run.state is not WorkflowState.CREATED:
            return self._serialize_run(run)

        self._workflow.start_analysis(run.run_id)
        correlation_id = f"corr-{run.run_id.removeprefix('run_')[:24]}"
        try:
            investigation = self._investigator(raw_ticket, correlation_id)
        except Exception:  # noqa: BLE001 -- external runtime errors must fail closed
            investigation = _degraded_investigation(raw_ticket, correlation_id)
        card = investigation.decision_card
        if investigation.mode == "degraded":
            outcome = AnalysisOutcome.DEGRADED_REVIEW_REQUIRED
        elif card.requires_human_review:
            outcome = AnalysisOutcome.REVIEW_REQUIRED
        else:
            outcome = AnalysisOutcome.PREPARED
        completed = self._workflow.complete_analysis(
            run.run_id,
            outcome,
            result={
                "mode": "REHEARSAL" if self._rehearsal else investigation.mode.upper(),
                "mode_label": (
                    "Local scripted investigator · synthetic fixtures"
                    if self._rehearsal
                    else (
                        "Live Strands · Amazon Bedrock"
                        if investigation.mode == "live"
                        else "Deterministic fallback · review required"
                    )
                ),
                "model_id": investigation.model_id or "not-configured",
                "deployment_revision": os.getenv(
                    "DEPLOYMENT_REVISION", os.getenv("APP_VERSION", "local-unverified")
                ),
                "correlation_id": investigation.correlation_id,
                "source_note": raw_ticket.note,
                "decision": _serialize_decision(card),
                "tool_trace": [event.model_dump(mode="json") for event in investigation.tool_trace],
            },
            correlation_id=investigation.correlation_id,
        )
        return self._serialize_run(completed)

    def get_run(self, run_id: str) -> dict[str, object]:
        try:
            return self._serialize_run(self._workflow.get_run(run_id))
        except WorkflowNotFoundError as error:
            raise RunNotFoundError from error

    def get_events(self, run_id: str) -> list[dict[str, object]]:
        try:
            run = self._workflow.get_run(run_id)
            workflow_events = self._workflow.get_events(run_id)
        except WorkflowNotFoundError as error:
            raise RunNotFoundError from error

        events: list[dict[str, object]] = []
        for event in workflow_events:
            events.append(
                {
                    "event_id": event.event_id,
                    "type": "review" if event.event_type == "REVIEW_RECORDED" else "workflow",
                    "label": _review_label(run) if event.event_type == "REVIEW_RECORDED" else _EVENT_LABELS[event.event_type],
                    "status": "recorded",
                    "occurred_at": event.as_dict()["occurred_at"],
                    "duration_ms": 0,
                }
            )

        result = run.as_dict()["result"]
        if isinstance(result, dict):
            occurred_at = run.as_dict()["updated_at"]
            for index, trace in enumerate(result.get("tool_trace", [])):
                if not isinstance(trace, dict):
                    continue
                events.insert(
                    min(2 + index, len(events)),
                    {
                        "event_id": f"tool-{run.run_id}-{index}",
                        "type": "tool",
                        "label": str(trace.get("tool_name", "bounded tool")),
                        "status": str(trace.get("status", "recorded")),
                        "occurred_at": occurred_at,
                        "duration_ms": int(trace.get("duration_ms", 0)),
                    },
                )
        return events

    def review_run(
        self, run_id: str, decision: str, reason_code: str
    ) -> dict[str, object]:
        try:
            reviewed = self._workflow.review_run(
                run_id,
                _REVIEW_DECISIONS[decision],
                _REVIEW_REASONS[reason_code],
            )
        except WorkflowNotFoundError as error:
            raise RunNotFoundError from error
        except (WorkflowConflictError, KeyError) as error:
            raise RunConflictError from error
        return self._serialize_run(reviewed)

    def apply_correction(self, run_id: str, correction_id: str) -> dict[str, object]:
        """Apply one fixed synthetic evidence packet to a reviewable live draft."""

        if correction_id != "serial_and_user_confirmed":
            raise ValueError("correction is not in the approved synthetic catalog")
        try:
            run = self._workflow.get_run(run_id)
        except WorkflowNotFoundError as error:
            raise RunNotFoundError from error
        if run.scenario_id != "replacement-pressure":
            raise ValueError("correction does not apply to this synthetic scenario")
        facts = known_facts("FB-DEMO-001").model_copy(
            update={
                "serial_number": "SYN-DEMO-RECOVERED",
                "actual_user_known": True,
                "unknown_fields": (),
            }
        )
        result = run.as_dict()["result"]
        if not isinstance(result, dict):
            raise RunConflictError
        result["decision"] = _serialize_decision(
            decision_card_for(get_scenario(run.scenario_id), facts)
        )
        try:
            corrected = self._workflow.record_correction(
                run_id,
                correction_id=correction_id,
                result=result,
            )
        except WorkflowConflictError as error:
            raise RunConflictError from error
        return self._serialize_run(corrected)

    @staticmethod
    def _serialize_run(run: RunRecord) -> dict[str, object]:
        payload = run.as_dict()
        result = payload.pop("result")
        if not isinstance(result, Mapping):
            result = {}
        return {**payload, **dict(result)}


def _serialize_decision(card: DecisionCard) -> dict[str, object]:
    return {
        "requested_priority": card.requested_priority or "Unknown",
        "allowed_priority": card.allowed_priority,
        "deadline": card.sla_deadline.isoformat(),
        "sla": card.sla,
        "owner": card.owner,
        "contracted_team": card.contracted_team,
        "internal_team": card.internal_team,
        "point_of_contact": card.point_of_contact,
        "schedule_recommendation": card.schedule_recommendation,
        "escalation_recommendation": card.escalation_recommendation,
        "dispatch_recommendation": card.dispatch_recommendation,
        "missing_evidence": [
            f"{gap.field.replace('_', ' ')} — {gap.reason}" for gap in card.missing_evidence
        ],
        "access_constraint": card.access_constraint,
        "fulfillment_plan": card.fulfillment_plan,
        "restoration_steps": list(card.restoration_steps),
        "closure_proof": list(card.closure_proof),
        "blocked_actions": list(card.blocked_actions),
        "review_reasons": list(card.review_reasons),
        "execution_state": card.execution_state,
    }


def _review_label(run: RunRecord) -> str:
    decision = run.review_decision
    reason = run.review_reason
    decision_label = {
        ReviewDecision.APPROVE_DRAFT: "Draft approved",
        ReviewDecision.REQUEST_CHANGES: "Changes requested",
        ReviewDecision.REJECT: "Draft rejected",
        None: "Review recorded",
    }[decision]
    reason_label = {
        ReviewReason.READY_FOR_HANDOFF: "evidence verified",
        ReviewReason.MISSING_EVIDENCE: "insufficient evidence",
        ReviewReason.POLICY_EXCEPTION: "policy exception",
        ReviewReason.INCORRECT_ROUTING: "routing correction",
        ReviewReason.NEEDS_CLARIFICATION: "needs clarification",
        ReviewReason.UNSAFE_OR_UNSUPPORTED: "unsafe or unsupported",
        None: "bounded reason",
    }[reason]
    return f"{decision_label} · {reason_label}"


class _UnavailableAgent:
    def __call__(self, _prompt: str) -> None:
        raise RuntimeError("live model invocation unavailable")


def _degraded_investigation(
    raw_ticket: RawTicket, correlation_id: str
) -> InvestigationResult:
    return run_investigation(
        raw_ticket,
        agent=_UnavailableAgent(),
        correlation_id=correlation_id,
    )


def _default_investigator(
    raw_ticket: RawTicket, correlation_id: str
) -> InvestigationResult:
    runtime_arn = os.getenv("AGENTCORE_RUNTIME_ARN")
    if runtime_arn and runtime_arn != "UNKNOWN":
        return AgentCoreInvestigator(runtime_arn=runtime_arn)(raw_ticket, correlation_id)
    return run_investigation(raw_ticket, correlation_id=correlation_id)
