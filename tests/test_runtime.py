"""Tests for the public demo and Strands tool wiring without a model invocation."""

from __future__ import annotations

import contextlib
import io
import json
import runpy
import unittest

from fieldbridge.demo import main, run_demo
from fieldbridge.strands_layer import build_agent
from fieldbridge.tools import (
    create_handoff_draft,
    inspect_contract,
    inspect_routing,
    safety_boundary,
)


class FieldBridgeRuntimeTests(unittest.TestCase):
    def test_demo_produces_a_repeatable_draft_only_handoff(self) -> None:
        self.assertEqual(run_demo()["execution_state"], "draft_only")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main()
        self.assertEqual(json.loads(output.getvalue())["ticket_id"], "FB-DEMO-001")

    def test_module_entrypoint_prints_the_demo(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            runpy.run_module("fieldbridge.__main__", run_name="__main__")
        self.assertIn("FB-DEMO-001", output.getvalue())

    def test_read_only_tools_expose_only_approved_synthetic_behavior(self) -> None:
        contract = inspect_contract("northstar-health")
        route = inspect_routing("enterprise_fax")
        boundary = safety_boundary()
        handoff = create_handoff_draft(
            {
                "ticket_id": "FB-401",
                "contract_id": "metro-financial",
                "priority": "P2",
                "category": "enterprise_fax",
                "summary": "Synthetic fax service issue.",
                "serial_number": None,
                "replacement_needed": False,
                "part_available_locally": False,
                "site_access": "stationed",
            }
        )

        self.assertIn("P1", contract["allowed_priorities"])
        self.assertEqual(route["owner"], "enterprise_fax_support")
        self.assertIn("close_ticket", boundary["blocked_operations"])
        self.assertEqual(handoff["execution_state"], "draft_only")

    def test_strands_agent_builds_with_bounded_tool_set_without_a_model_call(self) -> None:
        agent = build_agent()

        self.assertEqual(agent.__class__.__name__, "Agent")
