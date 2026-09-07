"""Replaceable persistence adapters for FieldBridge workflow records."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from .workflow import (
    AuditEvent,
    RunRecord,
    WorkflowConflictError,
    WorkflowValidationError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryRunRepository:
    """Thread-safe local ledger with atomic transitions and TTL behavior.

    Stored run and event values are frozen dataclasses. Internal dictionaries
    provide indexes only; callers receive immutable records and event tuples.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _utc_now
        self._lock = threading.RLock()
        self._runs: dict[str, RunRecord] = {}
        self._events: dict[str, list[AuditEvent]] = {}
        self._event_ids: set[str] = set()
        self._idempotency: dict[str, tuple[str, str]] = {}

    def create_run(
        self,
        *,
        run: RunRecord,
        event: AuditEvent,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> tuple[RunRecord, bool]:
        """Atomically create the first run snapshot and audit event."""

        with self._lock:
            self._purge_expired()
            replay = self._idempotency.get(idempotency_key)
            if replay is not None:
                fingerprint, run_id = replay
                if fingerprint != request_fingerprint:
                    raise WorkflowConflictError(
                        "idempotency key was already used for a different request"
                    )
                existing = self._runs.get(run_id)
                if existing is not None:
                    return existing, False
            self._validate_creation(run, event)
            self._runs[run.run_id] = run
            self._events[run.run_id] = [event]
            self._event_ids.add(event.event_id)
            self._idempotency[idempotency_key] = (request_fingerprint, run.run_id)
            return run, True

    def get_run(self, run_id: str) -> RunRecord | None:
        """Return the current immutable snapshot while its TTL is live."""

        with self._lock:
            self._purge_expired()
            return self._runs.get(run_id)

    def save_transition(
        self, *, run: RunRecord, event: AuditEvent, expected_version: int
    ) -> RunRecord:
        """Atomically compare-and-swap the run and append its event."""

        with self._lock:
            self._purge_expired()
            existing = self._runs.get(run.run_id)
            if existing is None:
                raise WorkflowConflictError("workflow run no longer exists")
            if existing.version != expected_version:
                raise WorkflowConflictError("workflow run version conflict")
            self._validate_transition(existing, run, event)
            self._runs[run.run_id] = run
            self._events[run.run_id].append(event)
            self._event_ids.add(event.event_id)
            return run

    def list_events(self, run_id: str) -> tuple[AuditEvent, ...]:
        """Return an immutable append-order event snapshot."""

        with self._lock:
            self._purge_expired()
            return tuple(self._events.get(run_id, ()))

    def reset(self) -> None:
        """Remove all local synthetic demo data, including idempotency indexes."""

        with self._lock:
            self._runs.clear()
            self._events.clear()
            self._event_ids.clear()
            self._idempotency.clear()

    def _validate_creation(self, run: RunRecord, event: AuditEvent) -> None:
        if run.run_id in self._runs:
            raise WorkflowConflictError("workflow run already exists")
        if event.event_id in self._event_ids:
            raise WorkflowConflictError("audit event already exists")
        if run.version != 0 or event.version != 0:
            raise WorkflowValidationError("created run must begin at version zero")
        if event.run_id != run.run_id or event.to_state != run.state:
            raise WorkflowValidationError("created audit event does not match run")
        if event.from_state is not None:
            raise WorkflowValidationError("created audit event cannot have a prior state")
        if event.expires_at != run.expires_at:
            raise WorkflowValidationError("audit TTL must match run TTL")

    def _validate_transition(
        self, existing: RunRecord, run: RunRecord, event: AuditEvent
    ) -> None:
        if run.version != existing.version + 1:
            raise WorkflowConflictError("workflow transition version is not sequential")
        if event.event_id in self._event_ids:
            raise WorkflowConflictError("audit event already exists")
        if event.run_id != run.run_id:
            raise WorkflowValidationError("audit event does not match run")
        if event.version != run.version:
            raise WorkflowValidationError("audit event version does not match run")
        if event.from_state != existing.state or event.to_state != run.state:
            raise WorkflowValidationError("audit event states do not match transition")
        if run.created_at != existing.created_at or run.expires_at != existing.expires_at:
            raise WorkflowValidationError("transition cannot change creation or TTL metadata")
        if event.expires_at != run.expires_at:
            raise WorkflowValidationError("audit TTL must match run TTL")

    def _purge_expired(self) -> None:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise WorkflowValidationError("clock must return a timezone-aware datetime")
        expired_ids = [
            run_id for run_id, run in self._runs.items() if run.expires_at <= now
        ]
        if not expired_ids:
            return
        expired_set = set(expired_ids)
        for run_id in expired_ids:
            self._runs.pop(run_id, None)
            removed_events = self._events.pop(run_id, ())
            self._event_ids.difference_update(event.event_id for event in removed_events)
        stale_keys = [
            key for key, (_fingerprint, run_id) in self._idempotency.items() if run_id in expired_set
        ]
        for key in stale_keys:
            self._idempotency.pop(key, None)
