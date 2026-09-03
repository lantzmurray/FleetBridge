"""Integration tests for FieldBridge's local synthetic-only HTTP boundary."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from fieldbridge.api import app


class FieldBridgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.payload = {
            "ticket_id": "FB-301",
            "contract_id": "northstar-health",
            "priority": "P2",
            "category": "device_print_unavailable",
            "summary": "Synthetic service visit needs a handoff.",
            "serial_number": "SYN-301",
            "replacement_needed": False,
            "part_available_locally": False,
            "site_access": "escorted",
            "actual_user_known": True,
        }

    def test_health_and_boundary_disclose_synthetic_draft_only_mode(self) -> None:
        health = self.client.get("/health")
        boundary = self.client.get("/api/v1/boundary")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["mode"], "synthetic_draft_only")
        self.assertIn("dispatch", boundary.json()["blocked_operations"])

    def test_handoff_endpoint_returns_a_draft_without_executing_actions(self) -> None:
        response = self.client.post("/api/v1/handoffs", json=self.payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["execution_state"], "draft_only")
        self.assertTrue(response.json()["requires_human_approval"])

    def test_handoff_endpoint_rejects_unapproved_data_without_echoing_it(self) -> None:
        response = self.client.post(
            "/api/v1/handoffs",
            json={**self.payload, "email": "person@example.com"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "request does not meet FieldBridge policy")
        self.assertNotIn("person@example.com", response.text)

    def test_handoff_endpoint_rejects_malformed_json(self) -> None:
        response = self.client.post(
            "/api/v1/handoffs",
            content="{not-json}",
            headers={"content-type": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid JSON request body")


if __name__ == "__main__":
    unittest.main()
