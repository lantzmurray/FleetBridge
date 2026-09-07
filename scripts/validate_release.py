#!/usr/bin/env python3
"""Deterministic release-artifact checks for FieldBridge.

This intentionally uses only the Python standard library so it can run before
project dependencies are installed and in a clean CI checkout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_file(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.is_file():
        raise ValueError(f"missing required release artifact: {relative_path}")
    return path.read_text(encoding="utf-8")


def require_all(text: str, values: tuple[str, ...], label: str) -> None:
    missing = [value for value in values if value not in text]
    if missing:
        raise ValueError(f"{label} is missing: {', '.join(missing)}")


def validate_dataset() -> None:
    path = ROOT / "evals/cases.json"
    if not path.is_file():
        raise ValueError("missing required release artifact: evals/cases.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) < 12:
        raise ValueError("evals/cases.json must contain at least 12 cases")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or len(set(ids)) != len(ids):
        raise ValueError("every eval case must have a unique id")
    for case in cases:
        require_all(
            json.dumps(case, sort_keys=True),
            ('"scenario_id"', '"expected"'),
            f"eval case {case.get('id', '<unknown>')}",
        )


def validate() -> None:
    template = require_file("deploy/template.yaml")
    require_all(
        template,
        (
            "AWS::Serverless::Function",
            "AWS::BedrockAgentCore::Runtime",
            "AWS::DynamoDB::Table",
            "TimeToLiveSpecification",
            "AWS::WAFv2::WebACL",
            "ReservedConcurrentExecutions",
            "bedrock-agentcore:InvokeAgentRuntime",
            "bedrock:InvokeModel",
            "SourceAccount",
        ),
        "deploy/template.yaml",
    )
    if "AdministratorAccess" in template or "BedrockAgentCoreFullAccess" in template:
        raise ValueError("deployment template must not use broad managed policies")

    dockerfile = require_file("Dockerfile")
    require_all(dockerfile, ("python:3.12", "USER appuser", "HEALTHCHECK"), "Dockerfile")

    readme = require_file("README.md")
    require_all(
        readme,
        ("Professional Agents", "UNKNOWN", "synthetic", "Run background sweep"),
        "README.md",
    )

    deploy_doc = require_file("docs/DEPLOYMENT.md")
    require_all(
        deploy_doc,
        ("UNKNOWN", "sam validate --lint", "Transaction Search", "three consecutive"),
        "docs/DEPLOYMENT.md",
    )

    require_file("docs/architecture.svg")
    drawio = require_file("docs/architecture.drawio")
    require_all(
        drawio,
        (
            "<mxfile",
            "mxgraph.aws4.waf",
            "mxgraph.aws4.api_gateway",
            "mxgraph.aws4.lambda_function",
            "mxgraph.aws4.dynamodb",
            "mxgraph.aws4.bedrock",
            "mxgraph.aws4.cloudwatch_2",
            "mxgraph.aws4.secrets_manager",
        ),
        "docs/architecture.drawio",
    )
    require_file("docs/DEVPOST_SUBMISSION.md")
    require_file("docs/BUILDER_POSTS.md")
    require_file("evals/run_evals.py")
    validate_dataset()


def main() -> int:
    try:
        validate()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"release validation failed: {error}", file=sys.stderr)
        return 1
    print("release artifacts: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
