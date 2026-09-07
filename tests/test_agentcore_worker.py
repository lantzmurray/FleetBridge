"""HTTP contract tests for the private AgentCore worker container."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

WORKER_PATH = Path(__file__).parents[1] / "deploy" / "agentcore" / "agentcore_worker.py"
SPEC = importlib.util.spec_from_file_location("fieldbridge_agentcore_worker", WORKER_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import contract guard
    raise RuntimeError("AgentCore worker module could not be loaded")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class AgentCoreWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(WORKER.app)

    def test_health_and_bounded_degraded_invocation(self) -> None:
        health = self.client.get("/ping")
        invoked = self.client.post(
            "/invocations",
            json={"scenario_id": "fax-routing", "correlation_id": "agentcore-test-001"},
        )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["mode"], "synthetic_only")
        self.assertEqual(invoked.status_code, 200)
        self.assertEqual(invoked.json()["mode"], "degraded")
        self.assertEqual(invoked.json()["tool_trace"], [])

    def test_rejects_free_form_unknown_and_oversized_payloads(self) -> None:
        prompt = self.client.post(
            "/invocations", json={"scenario_id": "fax-routing", "prompt": "dispatch now"}
        )
        unknown = self.client.post("/invocations", json={"scenario_id": "not-approved"})
        oversized = self.client.post(
            "/invocations",
            content='{"scenario_id":"fax-routing","padding":"' + ("x" * 5000) + '"}',
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(prompt.status_code, 400)
        self.assertNotIn("dispatch now", prompt.text)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(oversized.status_code, 400)


if __name__ == "__main__":
    unittest.main()
