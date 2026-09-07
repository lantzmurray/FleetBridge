"""Contract tests for the deployable DynamoDB persistence and quota adapters."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fieldbridge.aws_adapters import DynamoDBQuotaService, DynamoDBRunRepository
from fieldbridge.runtime_config import build_quota_service, build_run_service
from fieldbridge.workflow import WorkflowService


class RecordingDynamoClient:
    """Minimal recording client for request-shape tests without AWS access."""

    def __init__(self) -> None:
        self.transactions: list[list[dict[str, object]]] = []
        self.items: dict[tuple[str, str], dict[str, object]] = {}

    def transact_write_items(self, *, TransactItems: list[dict[str, object]]) -> None:
        self.transactions.append(TransactItems)
        for operation in TransactItems:
            if "Put" in operation:
                item = operation["Put"]["Item"]
                key = (item["PK"]["S"], item["SK"]["S"])
                self.items[key] = item
            elif "Update" in operation:
                update = operation["Update"]
                key = (update["Key"]["PK"]["S"], update["Key"]["SK"]["S"])
                item = self.items.setdefault(key, {"PK": update["Key"]["PK"], "SK": update["Key"]["SK"]})
                values = update["ExpressionAttributeValues"]
                current = int(item.get("request_count", {"N": "0"})["N"])
                item["request_count"] = {"N": str(current + int(values[":one"]["N"]))}
                item["expires_at"] = values[":expires"]

    def get_item(self, *, Key: dict[str, object], **_kwargs: object) -> dict[str, object]:
        item = self.items.get((Key["PK"]["S"], Key["SK"]["S"]))
        return {"Item": item} if item is not None else {}

    def query(self, **_kwargs: object) -> dict[str, object]:
        return {"Items": []}


class SecretClient:
    def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
        if SecretId != "arn:aws:secretsmanager:us-east-1:123456789012:secret:test":
            raise AssertionError("unexpected secret ARN")
        return {"SecretString": "runtime-secret-value"}


class DynamoDBAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 4, 14, 0, tzinfo=UTC)
        self.client = RecordingDynamoClient()

    def test_run_repository_writes_run_idempotency_and_append_only_event_items(self) -> None:
        repository = DynamoDBRunRepository(
            table_name="fieldbridge-test", client=self.client, clock=lambda: self.now
        )
        service = WorkflowService(repository=repository, clock=lambda: self.now)

        run = service.create_run("fax-routing", "dynamo-idem-001")

        writes = self.client.transactions[0]
        keys = {
            (operation["Put"]["Item"]["PK"]["S"], operation["Put"]["Item"]["SK"]["S"])
            for operation in writes
        }
        self.assertEqual(
            keys,
            {
                (f"RUN#{run.run_id}", "METADATA"),
                (f"RUN#{run.run_id}", "EVENT#00000000"),
                ("IDEMPOTENCY#dynamo-idem-001", "REQUEST"),
            },
        )
        self.assertTrue(all("expires_at" in operation["Put"]["Item"] for operation in writes))
        self.assertEqual(repository.get_run(run.run_id), run)
        repository.reset()
        self.assertEqual(repository.get_run(run.run_id), run)

    def test_dynamodb_quota_uses_only_hmac_identifier_and_atomic_counters(self) -> None:
        quota = DynamoDBQuotaService(
            table_name="fieldbridge-test",
            hmac_secret=b"quota-test-secret",
            client=self.client,
            clock=lambda: self.now,
            per_client_daily_limit=2,
            global_daily_limit=3,
        )

        decision = quota.check_and_consume("198.51.100.44")
        serialized_writes = repr(self.client.transactions[-1])

        self.assertTrue(decision.allowed)
        self.assertNotEqual(decision.client_id, "198.51.100.44")
        self.assertNotIn("198.51.100.44", serialized_writes)
        self.assertIn(decision.client_id, serialized_writes)
        self.assertEqual(decision.remaining_client, 1)
        self.assertEqual(decision.remaining_global, 2)

    def test_runtime_composition_selects_aws_adapters_when_resources_are_configured(self) -> None:
        environment = {
            "RUN_LEDGER_TABLE": "fieldbridge-test",
            "SOURCE_HMAC_SECRET_ARN": (
                "arn:aws:secretsmanager:us-east-1:123456789012:secret:test"
            ),
            "DEMO_CLIENT_DAILY_LIMIT": "2",
            "DEMO_GLOBAL_DAILY_LIMIT": "3",
        }
        with patch.dict("os.environ", environment, clear=True):
            run_service = build_run_service(dynamodb_client=self.client)
            quota_service = build_quota_service(
                dynamodb_client=self.client, secrets_client=SecretClient()
            )

        self.assertIsInstance(run_service._workflow._repository, DynamoDBRunRepository)
        self.assertIsInstance(quota_service, DynamoDBQuotaService)

    def test_local_quota_default_supports_full_pass3_evaluator(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            quota_service = build_quota_service()

        self.assertEqual(quota_service._per_client_limit, 100)
        self.assertEqual(quota_service._global_limit, 500)


if __name__ == "__main__":
    unittest.main()
