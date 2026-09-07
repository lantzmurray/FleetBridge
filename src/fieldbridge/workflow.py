"""Immutable workflow records and services for the synthetic FieldBridge demo.

The domain service depends on small protocols instead of a concrete cloud SDK.
The in-memory implementations support local demonstration; the AWS adapters
implement the same protocols without changing callers.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

Clock = Callable[[], datetime]


class WorkflowState(str, Enum):
    """Authoritative states exposed by the coordinator workflow."""

    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    PREPARED = "PREPARED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DEGRADED_REVIEW_REQUIRED = "DEGRADED_REVIEW_REQUIRED"
    FAILED = "FAILED"
    APPROVED_DRAFT = "APPROVED_DRAFT"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


class AnalysisOutcome(str, Enum):
    """Allowlisted outcomes for an analysis run."""

    PREPARED = "PREPARED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DEGRADED_REVIEW_REQUIRED = "DEGRADED_REVIEW_REQUIRED"
    FAILED = "FAILED"


class ReviewDecision(str, Enum):
    """Bounded decisions a coordinator may record for a synthetic draft."""

    APPROVE_DRAFT = "approve_draft"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"


class ReviewReason(str, Enum):
    """Allowlisted reason codes; free-form public review text is not accepted."""

    READY_FOR_HANDOFF = "READY_FOR_HANDOFF"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    POLICY_EXCEPTION = "POLICY_EXCEPTION"
    INCORRECT_ROUTING = "INCORRECT_ROUTING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSAFE_OR_UNSUPPORTED = "UNSAFE_OR_UNSUPPORTED"


class WorkflowError(Exception):
    """Base class for errors safe to map at the API boundary."""


class WorkflowValidationError(WorkflowError, ValueError):
    """A bounded workflow value did not meet the public contract."""


class WorkflowNotFoundError(WorkflowError, LookupError):
    """A run does not exist or its TTL has elapsed."""


class WorkflowConflictError(WorkflowError):
    """A transition, version, or idempotency request conflicts with state."""


@dataclass(frozen=True)
class RunRecord:
    """Immutable snapshot of one workflow run."""

    run_id: str
    scenario_id: str
    state: WorkflowState
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    version: int = 0
    result: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    review_decision: ReviewDecision | None = None
    review_reason: ReviewReason | None = None

    @property
    def ttl_epoch_seconds(self) -> int:
        """Return DynamoDB-compatible TTL metadata."""

        return int(self.expires_at.timestamp())

    def as_dict(self) -> dict[str, object]:
        """Return a detached, JSON-safe representation."""

        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "state": self.state.value,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
            "expires_at": _format_datetime(self.expires_at),
            "ttl_epoch_seconds": self.ttl_epoch_seconds,
            "version": self.version,
            "result": _thaw_json(self.result),
            "review_decision": (
                self.review_decision.value if self.review_decision is not None else None
            ),
            "review_reason": self.review_reason.value if self.review_reason is not None else None,
        }


@dataclass(frozen=True)
class AuditEvent:
    """Append-only evidence for a single state change."""

    event_id: str
    run_id: str
    event_type: str
    from_state: WorkflowState | None
    to_state: WorkflowState
    occurred_at: datetime
    expires_at: datetime
    version: int
    reason_code: ReviewReason | None = None
    correlation_id: str | None = None

    @property
    def ttl_epoch_seconds(self) -> int:
        """Return DynamoDB-compatible TTL metadata."""

        return int(self.expires_at.timestamp())

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe audit data without reasoning traces."""

        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "from_state": self.from_state.value if self.from_state is not None else None,
            "to_state": self.to_state.value,
            "occurred_at": _format_datetime(self.occurred_at),
            "expires_at": _format_datetime(self.expires_at),
            "ttl_epoch_seconds": self.ttl_epoch_seconds,
            "version": self.version,
            "reason_code": self.reason_code.value if self.reason_code is not None else None,
            "correlation_id": self.correlation_id,
        }


@runtime_checkable
class RunRepository(Protocol):
    """Atomic persistence boundary implemented by memory or DynamoDB."""

    def create_run(
        self,
        *,
        run: RunRecord,
        event: AuditEvent,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> tuple[RunRecord, bool]:
        """Create a run and first event, or return an idempotent replay."""

    def get_run(self, run_id: str) -> RunRecord | None:
        """Return a live run, excluding records past their TTL."""

    def save_transition(
        self, *, run: RunRecord, event: AuditEvent, expected_version: int
    ) -> RunRecord:
        """Atomically update a run and append its audit event."""

    def list_events(self, run_id: str) -> tuple[AuditEvent, ...]:
        """Return immutable event snapshots in append order."""

    def reset(self) -> None:
        """Reset a local store; shared cloud adapters may preserve append-only history."""


@runtime_checkable
class QuotaService(Protocol):
    """Public-request quota boundary replaceable by a durable adapter."""

    def check_and_consume(self, source_identifier: str) -> QuotaDecision:
        """Consume one request using only a derived identifier in storage."""


@dataclass(frozen=True)
class QuotaDecision:
    """Result of a daily quota check."""

    allowed: bool
    client_id: str
    remaining_client: int
    remaining_global: int
    resets_at: datetime
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe quota metadata."""

        return {
            "allowed": self.allowed,
            "client_id": self.client_id,
            "remaining_client": self.remaining_client,
            "remaining_global": self.remaining_global,
            "resets_at": _format_datetime(self.resets_at),
            "reason": self.reason,
        }


_ANALYSIS_STATES = {
    AnalysisOutcome.PREPARED: WorkflowState.PREPARED,
    AnalysisOutcome.REVIEW_REQUIRED: WorkflowState.REVIEW_REQUIRED,
    AnalysisOutcome.DEGRADED_REVIEW_REQUIRED: WorkflowState.DEGRADED_REVIEW_REQUIRED,
    AnalysisOutcome.FAILED: WorkflowState.FAILED,
}

_REVIEW_STATES = {
    ReviewDecision.APPROVE_DRAFT: WorkflowState.APPROVED_DRAFT,
    ReviewDecision.REQUEST_CHANGES: WorkflowState.CHANGES_REQUESTED,
    ReviewDecision.REJECT: WorkflowState.REJECTED,
}

_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SCENARIO_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CORRECTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class WorkflowService:
    """Coordinate valid lifecycle transitions and immutable audit writes."""

    def __init__(
        self,
        *,
        repository: RunRepository,
        clock: Clock | None = None,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
        if ttl <= timedelta(0):
            raise WorkflowValidationError("workflow TTL must be positive")
        self._repository = repository
        self._clock = clock or _utc_now
        self._ttl = ttl

    def create_run(self, scenario_id: str, idempotency_key: str) -> RunRecord:
        """Create a synthetic run, honoring replay-safe idempotency."""

        _validate_identifier("scenario_id", scenario_id, _SCENARIO_PATTERN)
        _validate_identifier("idempotency_key", idempotency_key, _IDEMPOTENCY_PATTERN)
        now = _aware_now(self._clock)
        expires_at = now + self._ttl
        run = RunRecord(
            run_id=f"run_{uuid4().hex}",
            scenario_id=scenario_id,
            state=WorkflowState.CREATED,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        event = _event_for(run=run, event_type="RUN_CREATED", from_state=None)
        fingerprint = hashlib.sha256(scenario_id.encode("utf-8")).hexdigest()
        stored, _created = self._repository.create_run(
            run=run,
            event=event,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        return stored

    def get_run(self, run_id: str) -> RunRecord:
        """Return one live run or raise a stable not-found error."""

        run = self._repository.get_run(run_id)
        if run is None:
            raise WorkflowNotFoundError("workflow run was not found")
        return run

    def get_events(self, run_id: str) -> tuple[AuditEvent, ...]:
        """Return detached immutable audit evidence."""

        return self._repository.list_events(run_id)

    def start_analysis(self, run_id: str) -> RunRecord:
        """Move a newly created run into analysis."""

        return self._transition(
            run_id=run_id,
            allowed_from=(WorkflowState.CREATED,),
            target=WorkflowState.ANALYZING,
            event_type="ANALYSIS_STARTED",
        )

    def complete_analysis(
        self,
        run_id: str,
        outcome: AnalysisOutcome | str,
        *,
        result: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> RunRecord:
        """Persist an allowlisted deterministic or degraded analysis outcome."""

        parsed_outcome = _parse_enum(AnalysisOutcome, outcome, "analysis outcome")
        if correlation_id is not None:
            _validate_identifier("correlation_id", correlation_id, _CORRELATION_PATTERN)
        return self._transition(
            run_id=run_id,
            allowed_from=(WorkflowState.ANALYZING,),
            target=_ANALYSIS_STATES[parsed_outcome],
            event_type="ANALYSIS_COMPLETED",
            result=result,
            correlation_id=correlation_id,
        )

    def review_run(
        self,
        run_id: str,
        decision: ReviewDecision | str,
        reason_code: ReviewReason | str,
    ) -> RunRecord:
        """Record a bounded human review; it never performs an external action."""

        parsed_decision = _parse_enum(ReviewDecision, decision, "review decision")
        parsed_reason = _parse_enum(ReviewReason, reason_code, "review reason")
        return self._transition(
            run_id=run_id,
            allowed_from=(WorkflowState.PREPARED, WorkflowState.REVIEW_REQUIRED),
            target=_REVIEW_STATES[parsed_decision],
            event_type="REVIEW_RECORDED",
            review_decision=parsed_decision,
            review_reason=parsed_reason,
        )

    def record_correction(
        self,
        run_id: str,
        *,
        correction_id: str,
        result: Mapping[str, Any],
    ) -> RunRecord:
        """Append one allowlisted synthetic evidence update without changing authority."""

        _validate_identifier("correction_id", correction_id, _CORRECTION_PATTERN)
        return self._transition(
            run_id=run_id,
            allowed_from=(WorkflowState.REVIEW_REQUIRED,),
            target=WorkflowState.REVIEW_REQUIRED,
            event_type="EVIDENCE_CORRECTED",
            result=result,
        )

    def reset_demo(self) -> None:
        """Reset only the replaceable local synthetic repository."""

        self._repository.reset()

    def _transition(
        self,
        *,
        run_id: str,
        allowed_from: tuple[WorkflowState, ...],
        target: WorkflowState,
        event_type: str,
        result: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
        review_decision: ReviewDecision | None = None,
        review_reason: ReviewReason | None = None,
    ) -> RunRecord:
        current = self.get_run(run_id)
        if current.state not in allowed_from:
            allowed = ", ".join(state.value for state in allowed_from)
            raise WorkflowConflictError(
                f"cannot transition from {current.state.value}; expected one of: {allowed}"
            )
        now = _aware_now(self._clock)
        immutable_result = current.result if result is None else _freeze_json_mapping(result)
        updated = replace(
            current,
            state=target,
            updated_at=now,
            version=current.version + 1,
            result=immutable_result,
            review_decision=review_decision,
            review_reason=review_reason,
        )
        event = _event_for(
            run=updated,
            event_type=event_type,
            from_state=current.state,
            correlation_id=correlation_id,
            reason_code=review_reason,
        )
        return self._repository.save_transition(
            run=updated,
            event=event,
            expected_version=current.version,
        )


class InMemoryQuotaService:
    """Thread-safe UTC daily quotas that never retain a raw source identifier."""

    def __init__(
        self,
        *,
        hmac_secret: bytes,
        per_client_daily_limit: int = 20,
        global_daily_limit: int = 500,
        clock: Clock | None = None,
    ) -> None:
        if not hmac_secret:
            raise WorkflowValidationError("quota HMAC secret is required")
        if per_client_daily_limit <= 0 or global_daily_limit <= 0:
            raise WorkflowValidationError("quota limits must be positive")
        if per_client_daily_limit > global_daily_limit:
            raise WorkflowValidationError("client quota cannot exceed global quota")
        self._secret = bytes(hmac_secret)
        self._per_client_limit = per_client_daily_limit
        self._global_limit = global_daily_limit
        self._clock = clock or _utc_now
        self._lock = threading.RLock()
        self._day: date | None = None
        self._client_counts: dict[str, int] = {}
        self._global_count = 0

    def check_and_consume(self, source_identifier: str) -> QuotaDecision:
        """Derive an HMAC client ID, then atomically consume one daily request."""

        if not isinstance(source_identifier, str) or not source_identifier.strip():
            raise WorkflowValidationError("source identifier is required")
        client_id = hmac.new(
            self._secret,
            source_identifier.strip().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        now = _aware_now(self._clock).astimezone(UTC)
        current_day = now.date()
        resets_at = datetime.combine(current_day + timedelta(days=1), time.min, tzinfo=UTC)

        with self._lock:
            if self._day != current_day:
                self._day = current_day
                self._client_counts.clear()
                self._global_count = 0
            client_count = self._client_counts.get(client_id, 0)
            if client_count >= self._per_client_limit:
                return self._quota_decision(
                    allowed=False,
                    client_id=client_id,
                    client_count=client_count,
                    resets_at=resets_at,
                    reason="client_daily_limit",
                )
            if self._global_count >= self._global_limit:
                return self._quota_decision(
                    allowed=False,
                    client_id=client_id,
                    client_count=client_count,
                    resets_at=resets_at,
                    reason="global_daily_limit",
                )
            client_count += 1
            self._client_counts[client_id] = client_count
            self._global_count += 1
            return self._quota_decision(
                allowed=True,
                client_id=client_id,
                client_count=client_count,
                resets_at=resets_at,
            )

    def snapshot(self) -> Mapping[str, object]:
        """Expose derived-key counts for diagnostics without raw identifiers."""

        with self._lock:
            return MappingProxyType(
                {
                    "day": self._day.isoformat() if self._day is not None else None,
                    "client_counts": MappingProxyType(dict(self._client_counts)),
                    "global_count": self._global_count,
                }
            )

    def _quota_decision(
        self,
        *,
        allowed: bool,
        client_id: str,
        client_count: int,
        resets_at: datetime,
        reason: str | None = None,
    ) -> QuotaDecision:
        return QuotaDecision(
            allowed=allowed,
            client_id=client_id,
            remaining_client=max(0, self._per_client_limit - client_count),
            remaining_global=max(0, self._global_limit - self._global_count),
            resets_at=resets_at,
            reason=reason,
        )


def build_demo_workflow_service(
    *, clock: Clock | None = None, ttl: timedelta = timedelta(hours=24)
) -> WorkflowService:
    """Build the local service without importing an AWS library."""

    from .repository import InMemoryRunRepository

    actual_clock = clock or _utc_now
    repository = InMemoryRunRepository(clock=actual_clock)
    return WorkflowService(repository=repository, clock=actual_clock, ttl=ttl)


def _event_for(
    *,
    run: RunRecord,
    event_type: str,
    from_state: WorkflowState | None,
    correlation_id: str | None = None,
    reason_code: ReviewReason | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=f"evt_{uuid4().hex}",
        run_id=run.run_id,
        event_type=event_type,
        from_state=from_state,
        to_state=run.state,
        occurred_at=run.updated_at,
        expires_at=run.expires_at,
        version=run.version,
        correlation_id=correlation_id,
        reason_code=reason_code,
    )


def _parse_enum(enum_type: type[Enum], raw_value: object, label: str) -> Any:
    try:
        return enum_type(raw_value)
    except (TypeError, ValueError) as error:
        raise WorkflowValidationError(f"unsupported {label}") from error


def _validate_identifier(label: str, value: object, pattern: re.Pattern[str]) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise WorkflowValidationError(f"invalid {label}")


def _freeze_json_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowValidationError("workflow result must be an object")
    frozen = _freeze_json(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - narrowed above
        raise WorkflowValidationError("workflow result must be an object")
    return frozen


def _freeze_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        frozen_items: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorkflowValidationError("workflow result keys must be strings")
            frozen_items[key] = _freeze_json(item)
        return MappingProxyType(frozen_items)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise WorkflowValidationError("workflow result must contain only JSON-safe values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _aware_now(clock: Clock) -> datetime:
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise WorkflowValidationError("clock must return a timezone-aware datetime")
    return now


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)
