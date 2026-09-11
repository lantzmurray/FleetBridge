"""Integration tests for FieldBridge's public, synthetic-only HTTP surface."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from fieldbridge.api import app, set_quota_service, set_run_service
from fieldbridge.engine import decision_card_for
from fieldbridge.evidence import known_facts
from fieldbridge.models import InvestigationResult, RawTicket
from fieldbridge.run_service import LocalRunService
from fieldbridge.workflow import InMemoryQuotaService


def _live_investigator(raw: RawTicket, correlation_id: str) -> InvestigationResult:
    return InvestigationResult(
        mode="live",
        model_id="us.amazon.nova-lite-v1:0",
        correlation_id=correlation_id,
        extracted_facts=known_facts(raw.ticket_id),
        decision_card=decision_card_for(raw, known_facts(raw.ticket_id)),
        tool_trace=(),
    )


class FieldBridgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        set_run_service(LocalRunService())
        set_quota_service(
            InMemoryQuotaService(
                hmac_secret=b"api-test-only",
                per_client_daily_limit=100,
                global_daily_limit=100,
            )
        )
        self.client = TestClient(app)
        self.client.post("/api/v1/demo/reset")

    def test_homepage_is_the_accessible_judge_facing_product(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("FieldBridge Service Desk", response.text)
        self.assertIn("prepare, never execute", response.text)
        self.assertIn("Run triage", response.text)
        self.assertIn("AI triage", response.text)
        self.assertIn('aria-live="polite"', response.text)
        self.assertIn('href="static/app.css?v=0.6.0"', response.text)
        self.assertIn('src="static/app.js?v=0.6.0"', response.text)

    def test_security_headers_are_set_on_html_and_api_responses(self) -> None:
        for response in (self.client.get("/"), self.client.get("/health")):
            with self.subTest(path=response.request.url.path):
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(response.headers["x-frame-options"], "DENY")
                self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                self.assertIn("default-src 'self'", response.headers["content-security-policy"])
                self.assertNotIn("'unsafe-inline'", response.headers["content-security-policy"])

    def test_health_and_boundary_disclose_synthetic_draft_only_mode(self) -> None:
        health = self.client.get("/health")
        boundary = self.client.get("/api/v1/boundary")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["mode"], "synthetic_draft_only")
        self.assertIn("dispatch", boundary.json()["blocked_operations"])

    def test_scenarios_are_bounded_and_contain_no_free_form_prompt(self) -> None:
        response = self.client.get("/api/v1/scenarios")

        self.assertEqual(response.status_code, 200)
        scenarios = response.json()["scenarios"]
        self.assertGreaterEqual(len(scenarios), 2)
        self.assertEqual(scenarios[0]["id"], "replacement-pressure")
        self.assertTrue(all(item["synthetic"] for item in scenarios))
        self.assertNotIn("prompt", response.text.lower())

    def test_run_is_idempotent_and_exposes_reviewable_decision(self) -> None:
        headers = {"Idempotency-Key": "api-test-key-001"}

        first = self.client.post(
            "/api/v1/runs", json={"scenario_id": "replacement-pressure"}, headers=headers
        )
        second = self.client.post(
            "/api/v1/runs", json={"scenario_id": "replacement-pressure"}, headers=headers
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["run_id"], second.json()["run_id"])
        self.assertEqual(first.json()["state"], "DEGRADED_REVIEW_REQUIRED")
        self.assertEqual(first.json()["mode"], "DEGRADED")
        self.assertEqual(first.json()["decision"]["allowed_priority"], "P2")
        self.assertIn("actual user", " ".join(first.json()["decision"]["missing_evidence"]))
        self.assertIn("serial", " ".join(first.json()["decision"]["missing_evidence"]))
        self.assertIn("chaperone", first.json()["decision"]["access_constraint"])
        self.assertTrue(first.json()["decision"]["blocked_actions"])

    def test_run_input_is_strictly_bounded_to_scenario_id(self) -> None:
        missing_key = self.client.post(
            "/api/v1/runs", json={"scenario_id": "replacement-pressure"}
        )
        arbitrary_ticket = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "replacement-pressure", "prompt": "real customer details"},
            headers={"Idempotency-Key": "api-test-key-002"},
        )
        unknown = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "unknown"},
            headers={"Idempotency-Key": "api-test-key-003"},
        )

        self.assertEqual(missing_key.status_code, 400)
        self.assertEqual(arbitrary_ticket.status_code, 400)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json()["detail"], "scenario not found")

    def test_idempotency_validation_and_reuse_conflicts_are_generic(self) -> None:
        invalid = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "invalid key with spaces"},
        )
        first = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "api-reuse-001"},
        )
        conflict = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "replacement-pressure"},
            headers={"Idempotency-Key": "api-reuse-001"},
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["detail"], "invalid run request")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"], "idempotency conflict")

    def test_oversized_post_body_is_rejected_before_validation_or_agent_work(self) -> None:
        response = self.client.post(
            "/api/v1/runs",
            content='{"scenario_id":"replacement-pressure","padding":"' + ("x" * 5000) + '"}',
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "api-oversize-001",
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "request body too large")

    def test_run_quota_returns_generic_429_and_retains_only_hmac_source_id(self) -> None:
        quota = InMemoryQuotaService(
            hmac_secret=b"quota-test-only",
            per_client_daily_limit=1,
            global_daily_limit=2,
        )
        set_quota_service(quota)

        first = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "api-quota-001"},
        )
        denied = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "api-quota-002"},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.json()["detail"], "public demo run quota exceeded")
        self.assertNotIn("testclient", repr(quota.snapshot()))

    def test_forwarded_callers_get_separate_quota_buckets(self) -> None:
        quota = InMemoryQuotaService(
            hmac_secret=b"quota-forwarded-test",
            per_client_daily_limit=1,
            global_daily_limit=5,
        )
        set_quota_service(quota)

        first_judge = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "fwd-quota-001", "X-Forwarded-For": "203.0.113.9"},
        )
        second_judge = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "fwd-quota-002", "X-Forwarded-For": "203.0.113.10"},
        )
        first_judge_repeat = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "fwd-quota-003", "X-Forwarded-For": "203.0.113.9"},
        )

        self.assertEqual(first_judge.status_code, 201)
        self.assertEqual(second_judge.status_code, 201)
        self.assertEqual(first_judge_repeat.status_code, 429)
        self.assertNotIn("203.0.113", repr(quota.snapshot()))

    def test_run_and_sanitized_events_can_be_retrieved(self) -> None:
        created = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "api-test-key-004"},
        ).json()

        run = self.client.get(f"/api/v1/runs/{created['run_id']}")
        events = self.client.get(f"/api/v1/runs/{created['run_id']}/events")

        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["decision"]["owner"], "enterprise_fax_support")
        self.assertEqual(events.status_code, 200)
        self.assertGreaterEqual(len(events.json()["events"]), 3)
        self.assertEqual(
            set(events.json()["events"][0]),
            {"event_id", "type", "label", "status", "occurred_at", "duration_ms"},
        )
        self.assertNotIn("reasoning", events.text.lower())

    def test_review_decisions_are_allowlisted_and_append_audit_event(self) -> None:
        set_run_service(LocalRunService(investigator=_live_investigator))
        created = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "replacement-pressure"},
            headers={"Idempotency-Key": "api-test-key-005"},
        ).json()
        run_id = created["run_id"]

        reviewed = self.client.post(
            f"/api/v1/runs/{run_id}/reviews",
            json={"decision": "approve", "reason_code": "evidence_verified"},
        )
        events = self.client.get(f"/api/v1/runs/{run_id}/events").json()["events"]

        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.json()["state"], "APPROVED_DRAFT")
        self.assertEqual(events[-1]["type"], "review")
        self.assertEqual(events[-1]["label"], "Draft approved · evidence verified")

        invalid = self.client.post(
            f"/api/v1/runs/{run_id}/reviews",
            json={"decision": "dispatch", "reason_code": "because_i_said_so"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_degraded_run_cannot_be_approved_as_if_the_agent_completed(self) -> None:
        created = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "replacement-pressure"},
            headers={"Idempotency-Key": "api-test-key-degraded"},
        ).json()

        reviewed = self.client.post(
            f"/api/v1/runs/{created['run_id']}/reviews",
            json={"decision": "approve", "reason_code": "evidence_verified"},
        )

        self.assertEqual(created["state"], "DEGRADED_REVIEW_REQUIRED")
        self.assertEqual(reviewed.status_code, 409)

    def test_bounded_synthetic_correction_updates_the_live_draft_and_audit(self) -> None:
        set_run_service(LocalRunService(investigator=_live_investigator))
        created = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "replacement-pressure"},
            headers={"Idempotency-Key": "api-correction-001"},  # gitleaks:allow
        ).json()

        corrected = self.client.post(
            f"/api/v1/runs/{created['run_id']}/corrections",
            json={"correction_id": "serial_and_user_confirmed"},
        )
        events = self.client.get(f"/api/v1/runs/{created['run_id']}/events").json()["events"]

        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.json()["decision"]["missing_evidence"], [])
        self.assertEqual(events[-1]["label"], "Approved synthetic evidence added")

        rejected = self.client.post(
            f"/api/v1/runs/{created['run_id']}/corrections",
            json={"correction_id": "invent_customer_contact"},
        )
        self.assertEqual(rejected.status_code, 400)

    def test_invalid_review_transition_has_a_generic_conflict_response(self) -> None:
        set_run_service(LocalRunService(investigator=_live_investigator))
        created = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "api-test-key-006"},
        ).json()
        run_id = created["run_id"]
        body = {"decision": "reject", "reason_code": "insufficient_evidence"}

        first = self.client.post(f"/api/v1/runs/{run_id}/reviews", json=body)
        second = self.client.post(f"/api/v1/runs/{run_id}/reviews", json=body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], "run is not reviewable")

    def test_demo_reset_clears_prior_runs(self) -> None:
        created = self.client.post(
            "/api/v1/runs",
            json={"scenario_id": "fax-routing"},
            headers={"Idempotency-Key": "api-test-key-007"},
        ).json()

        reset = self.client.post("/api/v1/demo/reset")
        missing = self.client.get(f"/api/v1/runs/{created['run_id']}")

        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json(), {"status": "reset", "synthetic_only": True})
        self.assertEqual(missing.status_code, 404)

    def test_arbitrary_ticket_handoff_endpoint_is_not_public(self) -> None:
        response = self.client.post(
            "/api/v1/handoffs",
            json={"ticket_id": "FB-301", "summary": "arbitrary ticket"},
        )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
