"""Unit and integration tests for the immutable demo workflow ledger."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

from fieldbridge.repository import InMemoryRunRepository
from fieldbridge.workflow import (
    AnalysisOutcome,
    InMemoryQuotaService,
    ReviewDecision,
    ReviewReason,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowService,
    WorkflowState,
    WorkflowValidationError,
    build_demo_workflow_service,
)


class MutableClock:
    """Small deterministic clock for TTL and daily-quota tests."""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class WorkflowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock(datetime(2026, 9, 4, 14, 0, tzinfo=UTC))
        self.repository = InMemoryRunRepository(clock=self.clock)
        self.service = WorkflowService(repository=self.repository, clock=self.clock)

    def test_create_run_is_immutable_audited_and_has_24_hour_ttl(self) -> None:
        run = self.service.create_run("replacement-gap", "idem-001")

        self.assertEqual(run.state, WorkflowState.CREATED)
        self.assertEqual(run.expires_at, self.clock.current + timedelta(hours=24))
        self.assertEqual(run.ttl_epoch_seconds, int(run.expires_at.timestamp()))
        self.assertEqual(run.version, 0)
        with self.assertRaises(FrozenInstanceError):
            run.state = WorkflowState.ANALYZING  # type: ignore[misc]

        events = self.service.get_events(run.run_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "RUN_CREATED")
        self.assertIsNone(events[0].from_state)
        self.assertEqual(events[0].to_state, WorkflowState.CREATED)
        self.assertEqual(events[0].ttl_epoch_seconds, run.ttl_epoch_seconds)

    def test_same_idempotency_key_returns_original_run_without_duplicate_event(self) -> None:
        original = self.service.create_run("replacement-gap", "idem-002")
        replay = self.service.create_run("replacement-gap", "idem-002")

        self.assertEqual(replay, original)
        self.assertEqual(len(self.service.get_events(original.run_id)), 1)

    def test_idempotency_key_cannot_be_reused_for_a_different_scenario(self) -> None:
        self.service.create_run("replacement-gap", "idem-003")

        with self.assertRaisesRegex(WorkflowConflictError, "idempotency"):
            self.service.create_run("fax-routing", "idem-003")

    def test_full_review_lifecycle_is_serializable_and_append_only(self) -> None:
        created = self.service.create_run("replacement-gap", "idem-004")
        analyzing = self.service.start_analysis(created.run_id)
        decision = {"owner": "field_service_dispatch", "missing_evidence": ["serial"]}
        prepared = self.service.complete_analysis(
            created.run_id,
            AnalysisOutcome.REVIEW_REQUIRED,
            result=decision,
            correlation_id="trace-004",
        )
        decision["owner"] = "mutated-outside"
        reviewed = self.service.review_run(
            created.run_id,
            ReviewDecision.APPROVE_DRAFT,
            ReviewReason.READY_FOR_HANDOFF,
        )

        self.assertEqual(analyzing.state, WorkflowState.ANALYZING)
        self.assertEqual(prepared.state, WorkflowState.REVIEW_REQUIRED)
        self.assertEqual(reviewed.state, WorkflowState.APPROVED_DRAFT)
        self.assertEqual(reviewed.result["owner"], "field_service_dispatch")
        self.assertEqual(reviewed.review_reason, ReviewReason.READY_FOR_HANDOFF)
        self.assertEqual(reviewed.as_dict()["state"], "APPROVED_DRAFT")
        self.assertIsInstance(reviewed.as_dict()["expires_at"], str)

        events = self.service.get_events(created.run_id)
        self.assertEqual(
            tuple(event.event_type for event in events),
            ("RUN_CREATED", "ANALYSIS_STARTED", "ANALYSIS_COMPLETED", "REVIEW_RECORDED"),
        )
        serialized = [event.as_dict() for event in events]
        self.assertEqual(serialized[2]["correlation_id"], "trace-004")
        self.assertEqual(serialized[3]["reason_code"], "READY_FOR_HANDOFF")
        self.assertEqual(self.service.get_events(created.run_id), events)

    def test_bounded_evidence_correction_is_an_append_only_same_state_transition(self) -> None:
        run = self.service.create_run("replacement-gap", "idem-correction")
        self.service.start_analysis(run.run_id)
        prepared = self.service.complete_analysis(
            run.run_id,
            AnalysisOutcome.REVIEW_REQUIRED,
            result={"missing_evidence": ["serial_number", "actual_user"]},
        )

        corrected = self.service.record_correction(
            run.run_id,
            correction_id="serial_and_user_confirmed",
            result={"missing_evidence": []},
        )

        self.assertEqual(corrected.state, WorkflowState.REVIEW_REQUIRED)
        self.assertEqual(corrected.version, prepared.version + 1)
        self.assertEqual(corrected.result["missing_evidence"], ())
        self.assertEqual(self.service.get_events(run.run_id)[-1].event_type, "EVIDENCE_CORRECTED")

    def test_each_analysis_outcome_maps_to_its_authoritative_state(self) -> None:
        expected = {
            AnalysisOutcome.PREPARED: WorkflowState.PREPARED,
            AnalysisOutcome.REVIEW_REQUIRED: WorkflowState.REVIEW_REQUIRED,
            AnalysisOutcome.DEGRADED_REVIEW_REQUIRED: WorkflowState.DEGRADED_REVIEW_REQUIRED,
            AnalysisOutcome.FAILED: WorkflowState.FAILED,
        }

        for index, (outcome, state) in enumerate(expected.items()):
            with self.subTest(outcome=outcome):
                run = self.service.create_run(f"scenario-{index}", f"outcome-{index}")
                self.service.start_analysis(run.run_id)
                completed = self.service.complete_analysis(run.run_id, outcome)
                self.assertEqual(completed.state, state)

    def test_invalid_or_repeated_transition_raises_conflict(self) -> None:
        run = self.service.create_run("replacement-gap", "idem-005")

        with self.assertRaises(WorkflowConflictError):
            self.service.complete_analysis(run.run_id, AnalysisOutcome.PREPARED)

        self.service.start_analysis(run.run_id)
        self.service.complete_analysis(run.run_id, AnalysisOutcome.PREPARED)
        self.service.review_run(
            run.run_id,
            ReviewDecision.REJECT,
            ReviewReason.UNSAFE_OR_UNSUPPORTED,
        )

        with self.assertRaises(WorkflowConflictError):
            self.service.review_run(
                run.run_id,
                ReviewDecision.REQUEST_CHANGES,
                ReviewReason.MISSING_EVIDENCE,
            )

    def test_degraded_and_failed_runs_are_not_reviewable(self) -> None:
        for index, outcome in enumerate(
            (AnalysisOutcome.DEGRADED_REVIEW_REQUIRED, AnalysisOutcome.FAILED)
        ):
            with self.subTest(outcome=outcome):
                run = self.service.create_run(f"terminal-{index}", f"terminal-{index}")
                self.service.start_analysis(run.run_id)
                self.service.complete_analysis(run.run_id, outcome)
                with self.assertRaises(WorkflowConflictError):
                    self.service.review_run(
                        run.run_id,
                        ReviewDecision.REQUEST_CHANGES,
                        ReviewReason.NEEDS_CLARIFICATION,
                    )

    def test_review_requires_allowlisted_decision_and_reason(self) -> None:
        run = self.service.create_run("replacement-gap", "idem-006")
        self.service.start_analysis(run.run_id)
        self.service.complete_analysis(run.run_id, AnalysisOutcome.REVIEW_REQUIRED)

        with self.assertRaises(WorkflowValidationError):
            self.service.review_run(run.run_id, "ship_it", ReviewReason.READY_FOR_HANDOFF)
        with self.assertRaises(WorkflowValidationError):
            self.service.review_run(run.run_id, ReviewDecision.REJECT, "free form reason")

    def test_unknown_or_expired_runs_are_not_returned(self) -> None:
        with self.assertRaises(WorkflowNotFoundError):
            self.service.get_run("unknown")

        run = self.service.create_run("replacement-gap", "idem-expiring")
        self.clock.current += timedelta(hours=24, seconds=1)

        with self.assertRaises(WorkflowNotFoundError):
            self.service.get_run(run.run_id)
        self.assertEqual(self.service.get_events(run.run_id), ())

    def test_demo_reset_removes_runs_events_and_idempotency_records(self) -> None:
        old = self.service.create_run("replacement-gap", "idem-reset")
        self.service.reset_demo()
        replacement = self.service.create_run("replacement-gap", "idem-reset")

        self.assertNotEqual(old.run_id, replacement.run_id)
        self.assertEqual(self.service.get_events(old.run_id), ())

    def test_default_demo_service_has_no_aws_dependency(self) -> None:
        service = build_demo_workflow_service(clock=self.clock)

        run = service.create_run("fax-routing", "default-demo")

        self.assertEqual(run.state, WorkflowState.CREATED)


class InMemoryRepositoryTests(unittest.TestCase):
    def test_optimistic_version_conflict_keeps_record_and_events_unchanged(self) -> None:
        clock = MutableClock(datetime(2026, 9, 4, 14, 0, tzinfo=UTC))
        repository = InMemoryRunRepository(clock=clock)
        service = WorkflowService(repository=repository, clock=clock)
        created = service.create_run("replacement-gap", "optimistic")
        analyzing = service.start_analysis(created.run_id)

        with self.assertRaises(WorkflowConflictError):
            repository.save_transition(
                run=analyzing,
                event=service.get_events(created.run_id)[-1],
                expected_version=0,
            )

        self.assertEqual(repository.get_run(created.run_id), analyzing)
        self.assertEqual(len(repository.list_events(created.run_id)), 2)


class InMemoryQuotaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock(datetime(2026, 9, 4, 23, 59, tzinfo=UTC))
        self.quota = InMemoryQuotaService(
            hmac_secret=b"synthetic-test-secret",
            per_client_daily_limit=2,
            global_daily_limit=3,
            clock=self.clock,
        )

    def test_quota_stores_only_hmac_client_identifiers(self) -> None:
        source = "192.0.2.10"

        decision = self.quota.check_and_consume(source)
        snapshot = self.quota.snapshot()

        self.assertTrue(decision.allowed)
        self.assertNotEqual(decision.client_id, source)
        self.assertEqual(len(decision.client_id), 64)
        self.assertNotIn(source, repr(snapshot))
        self.assertEqual(tuple(snapshot["client_counts"].values()), (1,))
        self.assertIsInstance(decision.as_dict()["resets_at"], str)

    def test_client_and_global_limits_are_enforced_without_incrementing_denials(self) -> None:
        self.assertTrue(self.quota.check_and_consume("198.51.100.1").allowed)
        self.assertTrue(self.quota.check_and_consume("198.51.100.1").allowed)
        client_denial = self.quota.check_and_consume("198.51.100.1")
        self.assertFalse(client_denial.allowed)
        self.assertEqual(client_denial.reason, "client_daily_limit")

        self.assertTrue(self.quota.check_and_consume("198.51.100.2").allowed)
        global_denial = self.quota.check_and_consume("198.51.100.3")
        self.assertFalse(global_denial.allowed)
        self.assertEqual(global_denial.reason, "global_daily_limit")
        self.assertEqual(self.quota.snapshot()["global_count"], 3)

    def test_daily_quota_resets_at_utc_midnight(self) -> None:
        first = self.quota.check_and_consume("203.0.113.9")
        self.clock.current += timedelta(minutes=2)
        second = self.quota.check_and_consume("203.0.113.9")

        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertEqual(second.remaining_client, 1)
        self.assertEqual(self.quota.snapshot()["global_count"], 1)

    def test_quota_configuration_and_source_are_validated(self) -> None:
        with self.assertRaises(WorkflowValidationError):
            InMemoryQuotaService(hmac_secret=b"", clock=self.clock)
        with self.assertRaises(WorkflowValidationError):
            self.quota.check_and_consume("")


if __name__ == "__main__":
    unittest.main()
