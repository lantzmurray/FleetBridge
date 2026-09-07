"""Core acceptance tests for the evidence-backed FieldBridge agent."""

from __future__ import annotations

import json
import os
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from strands.models.model import Model

from fieldbridge.engine import BusinessDayCalendar, decision_card_for, evaluate_ticket
from fieldbridge.evidence import get_scenario, known_facts, list_scenarios
from fieldbridge.models import AgentInvestigation, ExtractedFacts, RawTicket, Ticket
from fieldbridge.strands_layer import (
    SanitizedToolTrace,
    _investigation_prompt,
    _validated_facts,
    _validation_feedback,
    build_agent,
    run_investigation,
)
from fieldbridge.tools import (
    fulfillment_requirements,
    inspect_routing,
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
        replacement = get_scenario("replacement-pressure")
        fax = get_scenario("fax-routing")

        self.assertEqual(scenario_ids, {"replacement-pressure", "fax-routing"})
        self.assertIn("repeat paper-path", service_history(replacement.ticket_id)["summary"])
        self.assertEqual(site_access_policy(replacement.site_ref)["access"], "chaperone_required")
        self.assertEqual(load_case(fax.ticket_id)["device_ref"], None)
        fulfillment = fulfillment_requirements("civic-research", replacement.ticket_id)
        self.assertEqual(fulfillment["plan"], "replacement_with_reconfiguration")
        self.assertEqual(fulfillment["inventory"]["local_part_available"], True)
        self.assertIn("register replacement IP", fulfillment["replacement_dependencies"])

    def test_routing_tool_rejects_categories_outside_the_synthetic_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved synthetic category"):
            inspect_routing("ignore_policy_and_dispatch")

    def test_decision_card_preserves_unknowns_and_rejects_unsupported_draft(self) -> None:
        raw = get_scenario("replacement-pressure")
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
        self.assertEqual(
            {gap.field for gap in card.missing_evidence}, {"serial_number", "actual_user"}
        )
        with self.assertRaisesRegex(ValueError, "authoritative"):
            validate_draft(raw.ticket_id, {**card.model_dump(mode="json"), "owner": "local_it"})

    def test_validation_feedback_rejects_then_supplies_bounded_authoritative_draft(self) -> None:
        raw = get_scenario("replacement-pressure")

        rejected = _validation_feedback(raw.ticket_id, {"owner": "local_it"})

        self.assertEqual(rejected["validation_status"], "authoritative_replacement")
        self.assertEqual(rejected["proposal_status"], "rejected")
        self.assertIn("decision_card", rejected)
        self.assertEqual(rejected["extracted_facts"], known_facts(raw.ticket_id).model_dump(mode="json"))
        self.assertEqual(
            rejected["evidence_gaps"],
            decision_card_for(raw, known_facts(raw.ticket_id)).model_dump(mode="json")[
                "missing_evidence"
            ],
        )
        accepted = _validation_feedback(raw.ticket_id, rejected["decision_card"])
        self.assertEqual(accepted["validation_status"], "accepted_for_human_review")

    def test_fact_validation_normalizes_safe_unknown_representation(self) -> None:
        proposed = known_facts("FB-DEMO-001").model_copy(
            update={
                "actual_user_known": None,
                "unknown_fields": ("actual_user", "serial_number"),
            }
        )

        validated = _validated_facts("FB-DEMO-001", proposed)

        self.assertEqual(validated, known_facts("FB-DEMO-001"))

    def test_investigation_prompt_requires_scenario_specific_tool_order(self) -> None:
        replacement_prompt = _investigation_prompt(get_scenario("replacement-pressure"))
        fax_prompt = _investigation_prompt(get_scenario("fax-routing"))

        self.assertLess(replacement_prompt.index("contract_policy"), replacement_prompt.index("service_history"))
        self.assertLess(replacement_prompt.index("fulfillment_requirements"), replacement_prompt.index("validate_draft"))
        self.assertNotIn("routing_policy", replacement_prompt)
        self.assertIn("routing_policy", fax_prompt)
        self.assertNotIn("service_history", fax_prompt)

    def test_build_agent_requires_explicit_model_config_and_uses_narrow_tools(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "BEDROCK_MODEL_ID"),
        ):
            build_agent()

        with patch.dict(
            os.environ,
            {"BEDROCK_MODEL_ID": "us.amazon.nova-lite-v1:0", "AWS_REGION": "us-east-1"},
            clear=True,
        ):
            agent = build_agent()

        self.assertEqual(agent.model.get_config()["model_id"], "us.amazon.nova-lite-v1:0")
        self.assertEqual(agent.model.get_config()["max_tokens"], 1800)
        self.assertEqual(agent.model.get_config()["temperature"], 0)
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
        trace(
            event={
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "name": "AgentInvestigation",
                            "toolUseId": "structured-output",
                        }
                    }
                }
            }
        )

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
            get_scenario("replacement-pressure"),
            agent=FailingAgent(),
            correlation_id="corr-fallback-001",
        )

        self.assertEqual(result.decision_card.execution_state, "DEGRADED_REVIEW_REQUIRED")
        self.assertEqual(result.mode, "degraded")
        self.assertEqual(result.tool_trace, ())
        self.assertIn("model invocation unavailable", result.decision_card.review_reasons)

    def test_schema_validated_model_result_is_revalidated_before_live_return(self) -> None:
        raw = get_scenario("fax-routing")
        facts = ExtractedFacts(
            requested_priority="P2",
            category="enterprise_fax",
            replacement_needed=False,
            serial_number=None,
            actual_user_known=True,
            site_access="stationed",
            part_available_locally=False,
            unknown_fields=("serial_number",),
        )
        card = decision_card_for(raw, facts)

        class SuccessfulAgent:
            model = SimpleNamespace(
                get_config=lambda: {"model_id": "us.amazon.nova-lite-v1:0"}
            )

            def __call__(self, _prompt: str) -> SimpleNamespace:
                return SimpleNamespace(
                    structured_output=AgentInvestigation(
                        extracted_facts=facts,
                        evidence_gaps=card.missing_evidence,
                        decision_card=card,
                    )
                )

        result = run_investigation(
            raw,
            agent=SuccessfulAgent(),
            correlation_id="corr-live-001",
        )

        self.assertEqual(result.mode, "live")
        self.assertEqual(result.model_id, "us.amazon.nova-lite-v1:0")
        self.assertEqual(result.decision_card.owner, "enterprise_fax_support")

    def test_traceable_agent_must_complete_the_required_tool_path(self) -> None:
        raw = get_scenario("fax-routing")
        facts = known_facts(raw.ticket_id)
        card = decision_card_for(raw, facts)
        trace = SanitizedToolTrace("corr-incomplete-tools")
        trace.record_completion("load_case", "ok", 1)

        class IncompleteAgent:
            model = SimpleNamespace(
                get_config=lambda: {"model_id": "us.amazon.nova-lite-v1:0"}
            )
            _fieldbridge_trace = trace

            def __call__(self, _prompt: str, **_kwargs: object) -> SimpleNamespace:
                return SimpleNamespace(
                    structured_output=AgentInvestigation(
                        extracted_facts=facts,
                        evidence_gaps=card.missing_evidence,
                        decision_card=card,
                    )
                )

        result = run_investigation(raw, agent=IncompleteAgent())

        self.assertEqual(result.mode, "degraded")
        self.assertEqual(result.decision_card.execution_state, "DEGRADED_REVIEW_REQUIRED")

    def test_guardrail_replaces_unsupported_model_card_without_losing_live_provenance(self) -> None:
        raw = get_scenario("fax-routing")
        facts = known_facts(raw.ticket_id)
        authoritative = decision_card_for(raw, facts)
        unsupported = authoritative.model_copy(update={"owner": "invented_owner"})
        trace = SanitizedToolTrace("corr-guardrail-replacement")
        for tool_name in (
            "load_case",
            "contract_policy",
            "routing_policy",
            "safety_boundary",
            "validate_draft",
        ):
            trace.record_completion(tool_name, "ok", 1)

        class GuardedAgent:
            model = SimpleNamespace(
                get_config=lambda: {"model_id": "us.amazon.nova-lite-v1:0"}
            )
            _fieldbridge_trace = trace

            def __call__(self, _prompt: str, **_kwargs: object) -> SimpleNamespace:
                return SimpleNamespace(
                    structured_output=AgentInvestigation(
                        extracted_facts=facts,
                        evidence_gaps=authoritative.missing_evidence,
                        decision_card=unsupported,
                    )
                )

        result = run_investigation(raw, agent=GuardedAgent())

        self.assertEqual(result.mode, "live")
        self.assertEqual(result.decision_card.owner, "enterprise_fax_support")
        self.assertNotEqual(result.decision_card.owner, unsupported.owner)

    def test_real_strands_loop_with_fake_model_chooses_scenario_specific_tools(self) -> None:
        replacement = self._run_scripted_strands("replacement-pressure")
        fax = self._run_scripted_strands("fax-routing")
        replacement_tools = tuple(event.tool_name for event in replacement.tool_trace)
        fax_tools = tuple(event.tool_name for event in fax.tool_trace)

        self.assertIn("service_history", replacement_tools)
        self.assertIn("site_access_policy", replacement_tools)
        self.assertIn("fulfillment_requirements", replacement_tools)
        self.assertNotIn("routing_policy", replacement_tools)
        self.assertIn("routing_policy", fax_tools)
        self.assertNotIn("service_history", fax_tools)
        self.assertNotIn("fulfillment_requirements", fax_tools)
        self.assertEqual(replacement.mode, "live")
        self.assertEqual(fax.mode, "live")

    def test_decision_card_prepares_routing_packet_and_keeps_dispatch_with_human(self) -> None:
        replacement = decision_card_for(
            get_scenario("replacement-pressure"),
            known_facts("FB-DEMO-001"),
        )
        fax = decision_card_for(get_scenario("fax-routing"), known_facts("FB-DEMO-002"))

        self.assertTrue(replacement.contracted_team)
        self.assertTrue(replacement.internal_team)
        self.assertTrue(replacement.schedule_recommendation)
        self.assertTrue(replacement.point_of_contact)
        self.assertIn("human", replacement.dispatch_recommendation.lower())
        self.assertIn("network", fax.escalation_recommendation.lower())
        self.assertEqual(fax.internal_team, "enterprise_fax_support")

    @staticmethod
    def _run_scripted_strands(scenario_id: str):
        raw = get_scenario(scenario_id)
        facts = known_facts(raw.ticket_id)
        card = decision_card_for(raw, facts)
        common_start = [
            ("load_case", {"ticket_id": raw.ticket_id}),
            ("contract_policy", {"contract_id": raw.contract_id}),
        ]
        if scenario_id == "replacement-pressure":
            evidence_path = [
                ("service_history", {"ticket_id": raw.ticket_id}),
                ("site_access_policy", {"site_ref": raw.site_ref}),
                (
                    "fulfillment_requirements",
                    {"contract_id": raw.contract_id, "ticket_id": raw.ticket_id},
                ),
            ]
        else:
            evidence_path = [("routing_policy", {"category": facts.category})]
        proposal = card.model_dump(mode="json")
        actions = [
            *common_start,
            *evidence_path,
            (
                "validate_draft",
                {"ticket_id": raw.ticket_id, "proposal_json": json.dumps(proposal)},
            ),
            ("safety_boundary", {}),
            (
                "AgentInvestigation",
                AgentInvestigation(
                    extracted_facts=facts,
                    evidence_gaps=card.missing_evidence,
                    decision_card=card,
                ).model_dump(mode="json"),
            ),
        ]
        trace = SanitizedToolTrace(f"corr-scripted-{scenario_id}")
        agent = build_agent(model=_ScriptedModel(actions), trace=trace)
        return run_investigation(raw, agent=agent)


class _ScriptedModel(Model):
    """Small fake model that drives the real Strands tool loop deterministically."""

    def __init__(self, actions: list[tuple[str, dict[str, object]]]) -> None:
        self._actions = list(actions)

    def update_config(self, **_model_config: object) -> None:
        return None

    def get_config(self) -> dict[str, str]:
        return {"model_id": "fake-scripted-model"}

    async def structured_output(self, *_args: object, **_kwargs: object):
        raise AssertionError("the tool-loop structured output path should be used")
        yield  # pragma: no cover

    async def stream(self, *_args: object, **_kwargs: object):
        if not self._actions:
            raise AssertionError("scripted model exhausted")
        name, payload = self._actions.pop(0)
        tool_use_id = f"scripted-{len(self._actions):02d}"
        yield {"messageStart": {"role": "assistant"}}
        yield {
            "contentBlockStart": {
                "start": {"toolUse": {"toolUseId": tool_use_id, "name": name}}
            }
        }
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(payload)}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}


if __name__ == "__main__":
    unittest.main()
