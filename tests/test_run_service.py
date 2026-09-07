"""Application-service tests for local and AgentCore investigation paths."""

from __future__ import annotations

import json
import unittest

from fieldbridge.evidence import get_scenario
from fieldbridge.run_service import AgentCoreInvestigator, LocalRunService
from fieldbridge.strands_layer import run_investigation


class _FailingAgent:
    def __call__(self, _prompt: str) -> None:
        raise TimeoutError("synthetic provider outage")


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _AgentCoreClient:
    def __init__(self, response_payload: dict[str, object]) -> None:
        self.response_payload = response_payload
        self.calls: list[dict[str, object]] = []

    def invoke_agent_runtime(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {
            "statusCode": 200,
            "response": _Body(json.dumps(self.response_payload).encode("utf-8")),
        }


class AgentCoreInvestigatorTests(unittest.TestCase):
    def test_scenario_catalog_contains_day_work_queue_metadata(self) -> None:
        scenarios = LocalRunService().list_scenarios()

        self.assertEqual({item["queue_status"] for item in scenarios}, {"OPEN", "PREPARED"})
        for item in scenarios:
            with self.subTest(scenario=item["id"]):
                self.assertTrue(item["requester"])
                self.assertTrue(item["account"])
                self.assertTrue(item["channel"])
                self.assertTrue(item["received_at"])
                self.assertTrue(item["sla_preview"])
                self.assertTrue(item["assigned_team"])
                for field in ("serial", "application", "contact", "client", "due"):
                    self.assertIn(field, item)
                    self.assertTrue(item[field])

    def test_agentcore_invocation_accepts_only_scenario_and_correlation(self) -> None:
        raw = get_scenario("fax-routing")
        fallback = run_investigation(raw, agent=_FailingAgent(), correlation_id="corr-source")
        remote_result = fallback.model_copy(update={"mode": "live", "model_id": "nova-lite"})
        client = _AgentCoreClient(remote_result.model_dump(mode="json"))
        investigator = AgentCoreInvestigator(
            runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test",
            client=client,
        )

        result = investigator(raw, "corr-agentcore-001")

        self.assertEqual(result.mode, "live")
        sent = json.loads(client.calls[0]["payload"])
        self.assertEqual(
            sent,
            {"scenario_id": "fax-routing", "correlation_id": "corr-agentcore-001"},
        )
        self.assertEqual(client.calls[0]["contentType"], "application/json")
        self.assertEqual(client.calls[0]["accept"], "application/json")
        self.assertEqual(len(client.calls[0]["runtimeSessionId"]), 40)
        self.assertEqual(client.calls[0]["qualifier"], "DEFAULT")

    def test_local_service_uses_injected_investigator_and_real_workflow_events(self) -> None:
        raw = get_scenario("replacement-pressure")
        fallback = run_investigation(raw, agent=_FailingAgent(), correlation_id="corr-local-001")
        service = LocalRunService(investigator=lambda _raw, _correlation: fallback)

        run = service.create_run("replacement-pressure", "run-service-001")
        events = service.get_events(run["run_id"])

        self.assertEqual(run["mode"], "DEGRADED")
        self.assertEqual(run["state"], "DEGRADED_REVIEW_REQUIRED")
        self.assertEqual([event["type"] for event in events], ["workflow"] * 3)
        self.assertNotIn("tool", repr(events).lower())

    def test_rehearsal_service_is_interactive_without_claiming_live_aws(self) -> None:
        raw = get_scenario("replacement-pressure")
        fallback = run_investigation(raw, agent=_FailingAgent(), correlation_id="corr-rehearsal")
        scripted = fallback.model_copy(
            update={"mode": "live", "model_id": "scripted-local-fixture"}
        )
        service = LocalRunService(
            investigator=lambda _raw, _correlation: scripted,
            rehearsal=True,
        )

        run = service.create_run("replacement-pressure", "run-service-rehearsal-001")

        self.assertEqual(run["mode"], "REHEARSAL")
        self.assertEqual(run["state"], "REVIEW_REQUIRED")
        self.assertEqual(run["mode_label"], "Local scripted investigator · synthetic fixtures")
        self.assertEqual(run["model_id"], "scripted-local-fixture")


if __name__ == "__main__":
    unittest.main()
