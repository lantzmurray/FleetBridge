"""Environment-driven composition for local and AWS façade runtimes."""

from __future__ import annotations

import base64
import os
from secrets import token_bytes
from typing import Any

from .aws_adapters import DynamoDBQuotaService, DynamoDBRunRepository
from .run_service import LocalRunService
from .workflow import InMemoryQuotaService, QuotaService, WorkflowService


def build_run_service(*, dynamodb_client: Any | None = None) -> LocalRunService:
    """Use DynamoDB in the submitted façade and immutable memory locally."""

    table_name = os.getenv("RUN_LEDGER_TABLE")
    if not table_name:
        return LocalRunService()
    repository = DynamoDBRunRepository(
        table_name=table_name,
        client=dynamodb_client,
        region_name=_region(),
    )
    return LocalRunService(workflow=WorkflowService(repository=repository))


def build_quota_service(
    *,
    dynamodb_client: Any | None = None,
    secrets_client: Any | None = None,
) -> QuotaService:
    """Build durable HMAC quotas in AWS and process-local quotas for local demos."""

    table_name = os.getenv("RUN_LEDGER_TABLE")
    secret_arn = os.getenv("SOURCE_HMAC_SECRET_ARN")
    # Keep the local judge loop usable for the 15-case pass^3 evaluator while
    # retaining a tighter default once the durable cloud ledger is configured.
    client_default = 20 if table_name else 100
    client_limit = _positive_int("DEMO_CLIENT_DAILY_LIMIT", client_default)
    global_limit = _positive_int("DEMO_GLOBAL_DAILY_LIMIT", 500)
    if table_name and secret_arn and secret_arn != "UNKNOWN":
        secret = _load_secret(secret_arn, client=secrets_client)
        return DynamoDBQuotaService(
            table_name=table_name,
            hmac_secret=secret,
            client=dynamodb_client,
            per_client_daily_limit=client_limit,
            global_daily_limit=global_limit,
            region_name=_region(),
        )
    return InMemoryQuotaService(
        hmac_secret=token_bytes(32),
        per_client_daily_limit=client_limit,
        global_daily_limit=global_limit,
    )


def _load_secret(secret_arn: str, *, client: Any | None = None) -> bytes:
    if client is None:
        import boto3

        client = boto3.client("secretsmanager", region_name=_region())
    response = client.get_secret_value(SecretId=secret_arn)
    secret_string = response.get("SecretString")
    if isinstance(secret_string, str) and secret_string:
        return secret_string.encode("utf-8")
    secret_binary = response.get("SecretBinary")
    if isinstance(secret_binary, bytes) and secret_binary:
        return base64.b64decode(secret_binary)
    raise RuntimeError("quota HMAC secret is unavailable")


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _region() -> str:
    return os.getenv("AWS_REGION", os.getenv("AWS_REGION_NAME", "us-east-1"))
