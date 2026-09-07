#!/usr/bin/env python3
"""Run deterministic FieldBridge product evals against the public HTTP API."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float,
) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=data, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = {"error": "non-JSON error response"}
        return error.code, payload


def resolve(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.split(".") if path else ():
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            current = current[int(segment)]
        else:
            raise ValueError(f"missing response path: {path}")
    return current


def assert_expected(payload: Any, expected: dict[str, Any]) -> None:
    for path, value in expected.get("equals", {}).items():
        actual = resolve(payload, path)
        if actual != value:
            raise ValueError(f"{path}: expected {value!r}, got {actual!r}")
    for path in expected.get("present", []):
        actual = resolve(payload, path)
        if actual is None or actual == "" or actual == "UNKNOWN":
            raise ValueError(f"{path}: expected a known, non-empty value")
    for path, value in expected.get("contains", {}).items():
        actual = resolve(payload, path)
        if value not in actual:
            raise ValueError(f"{path}: expected to contain {value!r}")
    for path, value in expected.get("contains_ci", {}).items():
        actual = json.dumps(resolve(payload, path), sort_keys=True).casefold()
        if str(value).casefold() not in actual:
            raise ValueError(f"{path}: expected to contain {value!r} (case-insensitive)")
    for path, value in expected.get("not_contains_ci", {}).items():
        actual = json.dumps(resolve(payload, path), sort_keys=True).casefold()
        if str(value).casefold() in actual:
            raise ValueError(f"{path}: must not contain {value!r} (case-insensitive)")


def run_case(case: dict[str, Any], base_url: str, timeout: float) -> None:
    kind = case["kind"]
    default_status = 201 if kind in {"run", "idempotent_review"} else 200
    expected_status = int(case.get("expected_status", default_status))
    expected = case.get("expected", {})

    if kind == "get":
        status, payload = request_json(base_url, "GET", case["path"], timeout=timeout)
    elif kind in {"run", "reject"}:
        headers = {"Idempotency-Key": f"eval-{case['id']}-{uuid.uuid4().hex[:12]}"}
        status, payload = request_json(
            base_url,
            "POST",
            "/api/v1/runs",
            body=case["request"],
            headers=headers,
            timeout=timeout,
        )
    elif kind == "idempotent_review":
        idempotency_key = f"eval-{case['id']}-{uuid.uuid4().hex[:12]}"
        headers = {"Idempotency-Key": idempotency_key}
        status, first = request_json(
            base_url,
            "POST",
            "/api/v1/runs",
            body=case["request"],
            headers=headers,
            timeout=timeout,
        )
        if status != expected_status:
            raise ValueError(f"initial run: expected HTTP {expected_status}, got {status}")
        second_status, second = request_json(
            base_url,
            "POST",
            "/api/v1/runs",
            body=case["request"],
            headers=headers,
            timeout=timeout,
        )
        if second_status != expected_status or first.get("run_id") != second.get("run_id"):
            raise ValueError("Idempotency-Key did not return the original run")
        run_id = first["run_id"]
        status, payload = request_json(
            base_url,
            "POST",
            f"/api/v1/runs/{run_id}/reviews",
            body=case["review"],
            timeout=timeout,
        )
        if first.get("state") == "DEGRADED_REVIEW_REQUIRED":
            expected_status = int(case.get("degraded_review_status", 409))
            expected = case.get(
                "degraded_expected", {"equals": {"detail": "run is not reviewable"}}
            )
        else:
            expected_status = int(case.get("review_status", 200))
    else:
        raise ValueError(f"unsupported eval kind: {kind}")

    if status != expected_status:
        raise ValueError(f"expected HTTP {expected_status}, got {status}")
    assert_expected(payload, expected)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/cases.json")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.attempts <= 3:
        print("--attempts must be between 1 and 3", file=sys.stderr)
        return 2
    suite = json.loads(args.cases.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    started = time.monotonic()

    for case in suite["cases"]:
        errors: list[str] = []
        for _ in range(args.attempts):
            try:
                run_case(case, args.base_url, args.timeout)
            except (KeyError, TypeError, ValueError, urllib.error.URLError) as error:
                errors.append(str(error))
        passed = not errors
        results.append({"id": case["id"], "passed": passed, "errors": errors})
        print(f"{'PASS' if passed else 'FAIL'} {case['id']}")

    passed_count = sum(result["passed"] for result in results)
    report = {
        "suite": suite["name"],
        "base_url": args.base_url,
        "attempts_per_case": args.attempts,
        "metric": "pass@1" if args.attempts == 1 else f"pass^{args.attempts}",
        "passed": passed_count,
        "total": len(results),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "status": "PASS" if passed_count == len(results) else "FAIL",
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "passed", "total", "metric")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
