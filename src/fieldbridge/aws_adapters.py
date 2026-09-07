"""AWS persistence adapters used by the submitted Lambda façade."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any

from botocore.exceptions import ClientError

from .workflow import (
    AuditEvent,
    QuotaDecision,
    ReviewDecision,
    ReviewReason,
    RunRecord,
    WorkflowConflictError,
    WorkflowState,
    WorkflowValidationError,
    _freeze_json_mapping,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DynamoDBRunRepository:
    """Single-table run, idempotency, and append-only event repository."""

    def __init__(
        self,
        *,
        table_name: str,
        client: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        region_name: str | None = None,
    ) -> None:
        if not table_name:
            raise WorkflowValidationError("DynamoDB table name is required")
        if client is None:
            import boto3

            client = boto3.client("dynamodb", region_name=region_name)
        self._table_name = table_name
        self._client = client
        self._clock = clock or _utc_now

    def create_run(
        self,
        *,
        run: RunRecord,
        event: AuditEvent,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> tuple[RunRecord, bool]:
        """Atomically create a run, its first event, and replay index."""

        writes = [
            self._put(_run_item(run), condition="attribute_not_exists(PK)"),
            self._put(_event_item(event), condition="attribute_not_exists(PK)"),
            self._put(
                _idempotency_item(
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    run=run,
                ),
                condition="attribute_not_exists(PK)",
            ),
        ]
        try:
            self._client.transact_write_items(TransactItems=writes)
            return run, True
        except ClientError as error:
            if _error_code(error) != "TransactionCanceledException":
                raise
        replay = self._get_item(f"IDEMPOTENCY#{idempotency_key}", "REQUEST")
        if replay is None:
            raise WorkflowConflictError("DynamoDB creation conflict")
        if replay.get("request_fingerprint", {}).get("S") != request_fingerprint:
            raise WorkflowConflictError(
                "idempotency key was already used for a different request"
            )
        existing = self.get_run(replay["run_id"]["S"])
        if existing is None:
            raise WorkflowConflictError("idempotent workflow run is unavailable")
        return existing, False

    def get_run(self, run_id: str) -> RunRecord | None:
        item = self._get_item(f"RUN#{run_id}", "METADATA")
        if item is None:
            return None
        run = _run_from_item(item)
        if run.expires_at <= _aware_now(self._clock):
            return None
        return run

    def save_transition(
        self, *, run: RunRecord, event: AuditEvent, expected_version: int
    ) -> RunRecord:
        writes = [
            self._put(
                _run_item(run),
                condition="attribute_exists(PK) AND version = :expected_version",
                values={":expected_version": {"N": str(expected_version)}},
            ),
            self._put(_event_item(event), condition="attribute_not_exists(PK)"),
        ]
        try:
            self._client.transact_write_items(TransactItems=writes)
        except ClientError as error:
            if _error_code(error) == "TransactionCanceledException":
                raise WorkflowConflictError("workflow run version conflict") from error
            raise
        return run

    def list_events(self, run_id: str) -> tuple[AuditEvent, ...]:
        items: list[dict[str, Any]] = []
        request: dict[str, Any] = {
            "TableName": self._table_name,
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :event_prefix)",
            "ExpressionAttributeValues": {
                ":pk": {"S": f"RUN#{run_id}"},
                ":event_prefix": {"S": "EVENT#"},
            },
            "ConsistentRead": True,
        }
        while True:
            response = self._client.query(**request)
            items.extend(response.get("Items", []))
            cursor = response.get("LastEvaluatedKey")
            if not cursor:
                break
            request["ExclusiveStartKey"] = cursor
        now = _aware_now(self._clock)
        return tuple(
            _event_from_item(item)
            for item in items
            if datetime.fromisoformat(item["expires_at_iso"]["S"]) > now
        )

    def reset(self) -> None:
        """Leave shared cloud history intact; the browser reset starts a fresh view."""

    def _put(
        self,
        item: dict[str, Any],
        *,
        condition: str,
        values: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        request: dict[str, object] = {
            "TableName": self._table_name,
            "Item": item,
            "ConditionExpression": condition,
        }
        if values is not None:
            request["ExpressionAttributeValues"] = values
        return {"Put": request}

    def _get_item(self, partition_key: str, sort_key: str) -> dict[str, Any] | None:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"PK": {"S": partition_key}, "SK": {"S": sort_key}},
            ConsistentRead=True,
        )
        return response.get("Item")


class DynamoDBQuotaService:
    """Atomic daily quotas that persist only an HMAC-derived source identifier."""

    def __init__(
        self,
        *,
        table_name: str,
        hmac_secret: bytes,
        client: Any | None = None,
        per_client_daily_limit: int = 20,
        global_daily_limit: int = 500,
        clock: Callable[[], datetime] | None = None,
        region_name: str | None = None,
    ) -> None:
        if not table_name or not hmac_secret:
            raise WorkflowValidationError("quota table and HMAC secret are required")
        if per_client_daily_limit <= 0 or global_daily_limit <= 0:
            raise WorkflowValidationError("quota limits must be positive")
        if per_client_daily_limit > global_daily_limit:
            raise WorkflowValidationError("client quota cannot exceed global quota")
        if client is None:
            import boto3

            client = boto3.client("dynamodb", region_name=region_name)
        self._table_name = table_name
        self._secret = bytes(hmac_secret)
        self._client = client
        self._per_client_limit = per_client_daily_limit
        self._global_limit = global_daily_limit
        self._clock = clock or _utc_now

    def check_and_consume(self, source_identifier: str) -> QuotaDecision:
        if not isinstance(source_identifier, str) or not source_identifier.strip():
            raise WorkflowValidationError("source identifier is required")
        client_id = hmac.new(
            self._secret,
            source_identifier.strip().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        now = _aware_now(self._clock).astimezone(UTC)
        resets_at = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=UTC)
        partition_key = f"QUOTA#{now.date().isoformat()}"
        expires_at = int((resets_at + timedelta(days=1)).timestamp())
        try:
            self._client.transact_write_items(
                TransactItems=[
                    self._quota_update(
                        partition_key, "GLOBAL", self._global_limit, expires_at
                    ),
                    self._quota_update(
                        partition_key,
                        f"CLIENT#{client_id}",
                        self._per_client_limit,
                        expires_at,
                    ),
                ]
            )
        except ClientError as error:
            if _error_code(error) != "TransactionCanceledException":
                raise
            return self._quota_result(
                allowed=False,
                partition_key=partition_key,
                client_id=client_id,
                resets_at=resets_at,
            )
        return self._quota_result(
            allowed=True,
            partition_key=partition_key,
            client_id=client_id,
            resets_at=resets_at,
        )

    def _quota_update(
        self, partition_key: str, sort_key: str, limit: int, expires_at: int
    ) -> dict[str, object]:
        return {
            "Update": {
                "TableName": self._table_name,
                "Key": {"PK": {"S": partition_key}, "SK": {"S": sort_key}},
                "UpdateExpression": (
                    "SET request_count = if_not_exists(request_count, :zero) + :one, "
                    "expires_at = :expires"
                ),
                "ConditionExpression": (
                    "attribute_not_exists(request_count) OR request_count < :limit"
                ),
                "ExpressionAttributeValues": {
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                    ":limit": {"N": str(limit)},
                    ":expires": {"N": str(expires_at)},
                },
            }
        }

    def _quota_result(
        self,
        *,
        allowed: bool,
        partition_key: str,
        client_id: str,
        resets_at: datetime,
    ) -> QuotaDecision:
        global_count = self._count(partition_key, "GLOBAL")
        client_count = self._count(partition_key, f"CLIENT#{client_id}")
        reason = None
        if not allowed:
            reason = (
                "client_daily_limit"
                if client_count >= self._per_client_limit
                else "global_daily_limit"
            )
        return QuotaDecision(
            allowed=allowed,
            client_id=client_id,
            remaining_client=max(0, self._per_client_limit - client_count),
            remaining_global=max(0, self._global_limit - global_count),
            resets_at=resets_at,
            reason=reason,
        )

    def _count(self, partition_key: str, sort_key: str) -> int:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"PK": {"S": partition_key}, "SK": {"S": sort_key}},
            ConsistentRead=True,
        )
        return int(response.get("Item", {}).get("request_count", {}).get("N", "0"))


def _run_item(run: RunRecord) -> dict[str, Any]:
    payload = run.as_dict()
    item = {
        "PK": {"S": f"RUN#{run.run_id}"},
        "SK": {"S": "METADATA"},
        "entity_type": {"S": "RUN"},
        "run_id": {"S": run.run_id},
        "scenario_id": {"S": run.scenario_id},
        "state": {"S": run.state.value},
        "created_at": {"S": payload["created_at"]},
        "updated_at": {"S": payload["updated_at"]},
        "expires_at_iso": {"S": payload["expires_at"]},
        "expires_at": {"N": str(run.ttl_epoch_seconds)},
        "version": {"N": str(run.version)},
        "result_json": {"S": json.dumps(payload["result"], separators=(",", ":"))},
    }
    if run.review_decision is not None:
        item["review_decision"] = {"S": run.review_decision.value}
    if run.review_reason is not None:
        item["review_reason"] = {"S": run.review_reason.value}
    return item


def _run_from_item(item: dict[str, Any]) -> RunRecord:
    decision = item.get("review_decision", {}).get("S")
    reason = item.get("review_reason", {}).get("S")
    return RunRecord(
        run_id=item["run_id"]["S"],
        scenario_id=item["scenario_id"]["S"],
        state=WorkflowState(item["state"]["S"]),
        created_at=datetime.fromisoformat(item["created_at"]["S"]),
        updated_at=datetime.fromisoformat(item["updated_at"]["S"]),
        expires_at=datetime.fromisoformat(item["expires_at_iso"]["S"]),
        version=int(item["version"]["N"]),
        result=_freeze_json_mapping(json.loads(item["result_json"]["S"])),
        review_decision=ReviewDecision(decision) if decision else None,
        review_reason=ReviewReason(reason) if reason else None,
    )


def _event_item(event: AuditEvent) -> dict[str, Any]:
    payload = event.as_dict()
    item = {
        "PK": {"S": f"RUN#{event.run_id}"},
        "SK": {"S": f"EVENT#{event.version:08d}"},
        "entity_type": {"S": "EVENT"},
        "event_id": {"S": event.event_id},
        "run_id": {"S": event.run_id},
        "event_type": {"S": event.event_type},
        "to_state": {"S": event.to_state.value},
        "occurred_at": {"S": payload["occurred_at"]},
        "expires_at_iso": {"S": payload["expires_at"]},
        "expires_at": {"N": str(event.ttl_epoch_seconds)},
        "version": {"N": str(event.version)},
    }
    if event.from_state is not None:
        item["from_state"] = {"S": event.from_state.value}
    if event.reason_code is not None:
        item["reason_code"] = {"S": event.reason_code.value}
    if event.correlation_id is not None:
        item["correlation_id"] = {"S": event.correlation_id}
    return item


def _event_from_item(item: dict[str, Any]) -> AuditEvent:
    from_state = item.get("from_state", {}).get("S")
    reason = item.get("reason_code", {}).get("S")
    return AuditEvent(
        event_id=item["event_id"]["S"],
        run_id=item["run_id"]["S"],
        event_type=item["event_type"]["S"],
        from_state=WorkflowState(from_state) if from_state else None,
        to_state=WorkflowState(item["to_state"]["S"]),
        occurred_at=datetime.fromisoformat(item["occurred_at"]["S"]),
        expires_at=datetime.fromisoformat(item["expires_at_iso"]["S"]),
        version=int(item["version"]["N"]),
        reason_code=ReviewReason(reason) if reason else None,
        correlation_id=item.get("correlation_id", {}).get("S"),
    )


def _idempotency_item(
    *, idempotency_key: str, request_fingerprint: str, run: RunRecord
) -> dict[str, Any]:
    return {
        "PK": {"S": f"IDEMPOTENCY#{idempotency_key}"},
        "SK": {"S": "REQUEST"},
        "entity_type": {"S": "IDEMPOTENCY"},
        "request_fingerprint": {"S": request_fingerprint},
        "run_id": {"S": run.run_id},
        "expires_at": {"N": str(run.ttl_epoch_seconds)},
    }


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorkflowValidationError("clock must return a timezone-aware datetime")
    return value


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))
