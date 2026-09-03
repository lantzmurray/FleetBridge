"""Input-boundary tests for the FieldBridge API and Strands tools."""

from __future__ import annotations

import unittest

from fieldbridge.input_validation import ticket_from_payload


class TicketInputBoundaryTests(unittest.TestCase):
    def test_accepts_a_complete_synthetic_ticket_and_preserves_draft_only_boundary(self) -> None:
        ticket = ticket_from_payload(
            {
                "ticket_id": "FB-201",
                "contract_id": "northstar-health",
                "priority": "P2",
                "category": "device_print_unavailable",
                "summary": "Synthetic queue issue requires a visit.",
                "serial_number": "SYN-201",
                "replacement_needed": False,
                "part_available_locally": False,
                "site_access": "escorted",
                "actual_user_known": True,
            }
        )

        self.assertEqual(ticket.ticket_id, "FB-201")
        self.assertEqual(ticket.contract_id, "northstar-health")

    def test_rejects_unapproved_fields_that_could_hold_real_contact_data(self) -> None:
        with self.assertRaisesRegex(ValueError, "unapproved fields"):
            ticket_from_payload(
                {
                    "ticket_id": "FB-202",
                    "contract_id": "northstar-health",
                    "priority": "P2",
                    "category": "device_print_unavailable",
                    "summary": "Synthetic record.",
                    "serial_number": "SYN-202",
                    "replacement_needed": False,
                    "part_available_locally": False,
                    "site_access": "escorted",
                    "email": "person@example.com",
                }
            )

    def test_rejects_unknown_contracts_and_invalid_access_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "contract_id"):
            ticket_from_payload(
                {
                    "ticket_id": "FB-203",
                    "contract_id": "real-customer",
                    "priority": "P2",
                    "category": "device_print_unavailable",
                    "summary": "Synthetic record.",
                    "serial_number": "SYN-203",
                    "replacement_needed": False,
                    "part_available_locally": False,
                    "site_access": "escorted",
                }
            )

        with self.assertRaisesRegex(ValueError, "site_access"):
            ticket_from_payload(
                {
                    "ticket_id": "FB-204",
                    "contract_id": "northstar-health",
                    "priority": "P2",
                    "category": "device_print_unavailable",
                    "summary": "Synthetic record.",
                    "serial_number": "SYN-204",
                    "replacement_needed": False,
                    "part_available_locally": False,
                    "site_access": "badge_shared",
                }
            )

    def test_rejects_secret_like_or_overlong_summaries(self) -> None:
        payload = {
            "ticket_id": "FB-205",
            "contract_id": "northstar-health",
            "priority": "P2",
            "category": "device_print_unavailable",
            "summary": "password=not-for-public-projects",
            "serial_number": "SYN-205",
            "replacement_needed": False,
            "part_available_locally": False,
            "site_access": "escorted",
        }
        with self.assertRaisesRegex(ValueError, "secret-like"):
            ticket_from_payload(payload)

        with self.assertRaisesRegex(ValueError, "summary"):
            ticket_from_payload({**payload, "summary": "x" * 1001})


if __name__ == "__main__":
    unittest.main()
