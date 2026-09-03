"""Behavioral acceptance tests for FieldBridge's public-safe policy engine.

User journeys:
* A coordinator needs contract-specific guidance without relying on pressure from
  a loud requester.
* A technician needs a complete, safe handoff instead of an invented closure.
* A platform issue must reach the right internal owner even when no device serial
  number exists.
"""

from __future__ import annotations

import unittest

from fieldbridge.engine import evaluate_ticket
from fieldbridge.models import Ticket


class FieldBridgePolicyTests(unittest.TestCase):
    def test_health_network_p1_recommends_local_hot_swap_with_four_hour_sla(self) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-100",
                contract_id="northstar-health",
                priority="P1",
                category="device_print_unavailable",
                summary="Main-floor device cannot print.",
                serial_number="SYN-100",
                replacement_needed=True,
                part_available_locally=True,
                site_access="escorted",
            )
        )

        self.assertEqual(result.sla, "resolve within 4 hours")
        self.assertEqual(result.recommended_fulfillment, "local_hot_swap")
        self.assertEqual(result.part_delivery, "local_courier_candidate")
        self.assertIn("printing is restored", result.closure_requirements)
        self.assertTrue(result.requires_human_approval)

    def test_federal_contract_replacement_requires_reconfiguration_and_cannot_close_as_hot_swap(
        self,
    ) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-101",
                contract_id="civic-research",
                priority="P2",
                category="device_print_unavailable",
                summary="Replacement device is required after repeated jams.",
                serial_number="SYN-101",
                replacement_needed=True,
                part_available_locally=True,
                site_access="chaperone_required",
            )
        )

        self.assertEqual(result.sla, "end of next business day")
        self.assertEqual(result.recommended_fulfillment, "replacement_with_reconfiguration")
        self.assertIn("register the replacement IP", result.required_steps)
        self.assertIn("verify the managed print workflow", result.closure_requirements)
        self.assertNotIn("local_hot_swap", result.recommended_fulfillment)

    def test_platform_fax_issue_routes_without_a_printer_serial_number(self) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-102",
                contract_id="metro-financial",
                priority="P2",
                category="enterprise_fax",
                summary="Inbound fax delivery failed for a business workflow.",
                serial_number=None,
                replacement_needed=False,
                part_available_locally=False,
                site_access="stationed",
            )
        )

        self.assertEqual(result.owner, "enterprise_fax_support")
        self.assertFalse(result.serial_number_required)
        self.assertIn("do not redirect this platform issue to local IT", result.routing_notes)

    def test_managed_print_issue_routes_to_platform_support_not_local_it(self) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-103",
                contract_id="metro-financial",
                priority="P2",
                category="managed_print_access",
                summary="Users cannot authenticate to the managed print service.",
                serial_number="SYN-103",
                replacement_needed=False,
                part_available_locally=False,
                site_access="stationed",
            )
        )

        self.assertEqual(result.owner, "managed_print_platform_support")
        self.assertIn("internal platform team", result.routing_notes)
        self.assertNotIn("local IT password reset", result.routing_notes)

    def test_loud_requester_does_not_override_the_contract_priority_policy(self) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-104",
                contract_id="metro-financial",
                priority="P1",
                category="device_print_unavailable",
                summary="Executive department requests immediate attention.",
                serial_number="SYN-104",
                replacement_needed=False,
                part_available_locally=False,
                site_access="unknown",
            )
        )

        self.assertEqual(result.normalized_priority, "P2")
        self.assertTrue(result.requires_human_review)
        self.assertIn("contract does not offer P1", result.review_reasons)
        self.assertIn("site access must be confirmed", result.review_reasons)

    def test_missing_actual_user_information_creates_a_contact_recovery_task(self) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-105",
                contract_id="civic-research",
                priority="P2",
                category="device_print_unavailable",
                summary="Queue remains stalled after an attempted restart.",
                serial_number="SYN-105",
                replacement_needed=False,
                part_available_locally=False,
                site_access="chaperone_required",
                actual_user_known=False,
            )
        )

        self.assertIn("recover an actual-user contact", result.required_steps)
        self.assertIn("draft a customer update", result.required_steps)
        self.assertTrue(result.requires_human_review)

    def test_handoff_is_a_draft_and_never_executes_dispatch_or_customer_contact(self) -> None:
        result = evaluate_ticket(
            Ticket(
                ticket_id="FB-106",
                contract_id="northstar-health",
                priority="P2",
                category="device_print_unavailable",
                summary="Paper-path fault requires a next-day visit.",
                serial_number="SYN-106",
                replacement_needed=False,
                part_available_locally=False,
                site_access="escorted",
            )
        )

        self.assertEqual(result.execution_state, "draft_only")
        self.assertTrue(result.requires_human_approval)
        self.assertIn("customer update", result.draft_handoff)


if __name__ == "__main__":
    unittest.main()
