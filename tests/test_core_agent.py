"""Core acceptance tests for the evidence-backed FieldBridge agent."""

from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from pydantic import ValidationError

from fieldbridge.engine import BusinessDayCalendar, decision_card_for, evaluate_ticket
from fieldbridge.evidence import get_scenario, list_scenarios
from fieldbridge.models import ExtractedFacts, RawTicket, Ticket
from fieldbridge.strands_layer import SanitizedToolTrace, build_agent, run_investigation
from fieldbridge.tools import (
    fulfillment_requirements,
    load_case,
    service_history,
    site_access_policy,
    validate_draft,
)


class FieldBridgeCoreAgentTests(unittest.TestCase):
    def test_raw_ticket_is_bounded_immutable_and_preserves_unknowns(self) -> None:
        ticket = RawTicket(
            ticket_id="FB-DEMO-001",
            contract_id="civic-research",
            reported_at=datetime(2026, 9, 4, 19, 30, tzinfo=UTC),
            note="Urgent—replace the printer. Send someone today.",
            device_ref="DEVICE-DEMO-001",
            site_ref="SITE-CIVIC-01",
            unknown_fields=("actual_user", "serial_number"),
        )

        self.assertEqual(ticket.unknown_fields, ("actual_user", "serial_number"))
        with self.assertRaises(ValidationError):
            ticket.note = "changed"  # type: ignore[misc]
        with self.assertRaises(ValidationError):
            RawTicket(
                ticket_id="FB-DEMO-001",
                contract_id="civic-research",
                reported_at=datetime(2026, 9, 4, 19, 30, tzinfo=UTC),
                note="x" * 1001,
                device_ref=None,
                site_ref="SITE-CIVIC-01",
                unknown_fields=(),
            )

    def test_next_business_day_deadline_uses_contract_timezone_and_calendar(self) -> None:
        ticket = Ticket(
            ticket_id="FB-500",
            contract_id="civic-research",
            priority="P2",
            category="device_print_unavailable",
            summary="Synthetic paper-path failure.",
            serial_number="SYN-500",
            replacement_needed=True,
            part_available_locally=False,
            site_access="chaperone_required",
            reported_at=datetime(2026, 9, 4, 19, 30, tzinfo=UTC),  # Friday 3:30 PM ET
        )

        result = evaluate_ticket(ticket, business_calendar=BusinessDayCalendar())

        self.assertEqual(result.sla_deadline, "2026-09-07T17:00:00-04:00")
        self.assertEqual(result.sla_timezone, "America/New_York")

    def test_device_route_without_serial_is_forced_to_human_review(self) -> None:
        ticket = Ticket(
            ticket_id="FB-501",
            contract_id="northstar-health",
            priority="P1",
            category="device_print_unavailable",
            summary="Synthetic device is unavailable.",
            serial_number=None,
            replacement_needed=True,
            part_available_locally=True,
            site_access="escorted",
            reported_at=datetime(2026, 9, 4, 14, 0, tzinfo=UTC),
        )

        result = evaluate_ticket(ticket)

        self.assertTrue(result.requires_human_review)
        self.assertIn("device serial evidence is missing", result.review_reasons)
        self.assertIn("recover the synthetic device serial", result.required_steps)

    def test_seeded_scenarios_and_tools_expose_distinct_evidence_paths(self) -> None:
        scenario_ids = {scenario["scenario_id"] for scenario in list_scenarios()}
        replacement = get_scenario("replacement-gap")
        fax = get_scenario("fax-routing")

        self.assertEqual(scenario_ids, {"replacement-gap", "fax-routing"})
        self.assertIn("repeat paper-path", service_history(replacement.ticket_id)["summary"])
        self.assertEqual(site_access_policy(replacement.site_ref)["access"], "chaperone_required")
        self.assertEqual(load_case(fax.ticket_id)["device_ref"], None)
        self.assertEqual(
            fulfillment_requirements("civic-research", replacement.ticket_id)["plan"],
            "replacement_with_reconfiguration",
        )

    def test_decision_card_preserves_unknowns_and_rejects_unsupported_draft(self) -> None:
        raw = get_scenario("replacement-gap")
        facts = ExtractedFacts(
            requested_priority="P1",
            category="device_print_unavailable",
            replacement_needed=True,
            serial_number=None,
            actual_user_known=False,
            site_access="chaperone_required",
            part_available_locally=True,
            unknown_fields=("serial_number", "actual_user"),
        )

        card = decision_card_for(raw, facts)

        self.assertEqual(card.allowed_priority, "P2")
        self.assertEqual(card.requested_priority, "P1")
        self.assertEqual({gap.field for gap in card.missing_evidence}, {"serial_number", "actual_user"})
        with self.assertRaisesRegex(ValueError, "authoritative"):
            validate_draft(raw.ticket_id, {**card.model_dump(mode="json"), "owner": "local_it"})

    def test_build_agent_requires_explicit_model_config_and_uses_narrow_tools(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            RuntimeError, "BEDROCK_MODEL_ID"
        ):
            build_agent()

        with patch.dict(
            os.environ,
            {"BEDROCK_MODEL_ID": "us.amazon.nova-lite-v1:0", "AWS_REGION": "us-east-1"},
            clear=True,
        ):
            agent = build_agent()

        self.assertEqual(agent.model.get_config()["model_id"], "us.amazon.nova-lite-v1:0")
        tool_names = {tool.tool_name for tool in agent.tool_registry.registry.values()}
        self.assertEqual(
            tool_names,
            {
                "load_case",
                "contract_policy",
                "service_history",
                "site_access_policy",
                "routing_policy",
                "fulfillment_requirements",
                "validate_draft",
                "safety_boundary",
            },
        )

    def test_sanitized_trace_captures_only_tool_metadata(self) -> None:
        trace = SanitizedToolTrace(correlation_id="corr-safe-001")

        trace(
            event={
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "name": "contract_policy",
                            "toolUseId": "tool-1",
                            "input": {"secret": "must not appear"},
                        }
                    }
                },
                "reasoningContent": "never retain chain of thought",
            }
        )
        trace.record_completion("contract_policy", "ok", 12)

        self.assertEqual(
            trace.as_dicts(),
            [
                {
                    "tool_name": "contract_policy",
                    "status": "ok",
                    "duration_ms": 12,
                    "correlation_id": "corr-safe-001",
                }
            ],
        )

    def test_model_failure_returns_labeled_deterministic_fallback_without_fake_trace(self) -> None:
        class FailingAgent:
            def __call__(self, _prompt: str):
                raise TimeoutError("Bedrock did not answer")

        result = run_investigation(
            get_scenario("replacement-gap"),
            agent=FailingAgent(),
            correlation_id="corr-fallback-001",
        )

        self.assertEqual(result.decision_card.execution_state, "DEGRADED_REVIEW_REQUIRED")
        self.assertEqual(result.mode, "degraded")
        self.assertEqual(result.tool_trace, ())
        self.assertIn("model invocation unavailable", result.decision_card.review_reasons)


if __name__ == "__main__":
    unittest.main()
