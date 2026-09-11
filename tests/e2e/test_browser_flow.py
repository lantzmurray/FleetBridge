"""Playwright proof of the critical coordinator workflow."""

from __future__ import annotations

import os
import socket
import threading
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

import uvicorn
from playwright.sync_api import sync_playwright

from fieldbridge.api import app, set_quota_service, set_run_service
from fieldbridge.engine import decision_card_for
from fieldbridge.evidence import known_facts
from fieldbridge.models import InvestigationResult, RawTicket, ToolTraceEvent
from fieldbridge.run_service import LocalRunService
from fieldbridge.workflow import InMemoryQuotaService


def _live_investigator(raw: RawTicket, correlation_id: str) -> InvestigationResult:
    tool_names = (
        (
            "load_case",
            "contract_policy",
            "service_history",
            "site_access_policy",
            "fulfillment_requirements",
            "validate_draft",
            "safety_boundary",
        )
        if raw.ticket_id == "FB-DEMO-001"
        else ("load_case", "contract_policy", "routing_policy", "validate_draft", "safety_boundary")
    )
    return InvestigationResult(
        mode="live",
        model_id="us.amazon.nova-lite-v1:0",
        correlation_id=correlation_id,
        extracted_facts=known_facts(raw.ticket_id),
        decision_card=decision_card_for(raw, known_facts(raw.ticket_id)),
        tool_trace=tuple(
            ToolTraceEvent(
                tool_name=name,
                status="ok",
                duration_ms=index + 1,
                correlation_id=correlation_id,
            )
            for index, name in enumerate(tool_names)
        ),
    )


class BrowserWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        set_run_service(LocalRunService(investigator=_live_investigator))
        set_quota_service(
            InMemoryQuotaService(
                hmac_secret=b"browser-test-only",
                per_client_daily_limit=20,
                global_daily_limit=20,
            )
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            cls.port = listener.getsockname()[1]
        cls.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        )
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{cls.port}/health", timeout=1):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("browser test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def test_reset_triage_decision_approval_and_audit_timeline(self) -> None:
        browser_path = os.getenv("FIELD_BRIDGE_CHROME_PATH")
        mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if browser_path is None and mac_chrome.exists():
            browser_path = str(mac_chrome)

        with sync_playwright() as playwright:
            launch = {"headless": True}
            if browser_path:
                launch["executable_path"] = browser_path
            browser = playwright.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"http://127.0.0.1:{self.port}", wait_until="networkidle")

            page.get_by_role("button", name="Reset").click()
            page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="Run triage").click()
            page.get_by_text("Coordinator review required").wait_for()

            self.assertEqual(page.locator("#mode-badge").inner_text(), "LIVE")
            self.assertEqual(page.locator("#owner").inner_text(), "field service dispatch")
            self.assertIn("2026-09-07", page.locator("#deadline").inner_text())
            self.assertIn("Civic Research", page.locator("#route-team").inner_text())
            self.assertIn("Human coordinator decides", page.locator("#dispatch-recommendation").inner_text())
            self.assertGreaterEqual(page.locator("#tool-timeline li").count(), 7)
            self.assertIn("contract_policy", page.locator("#tool-timeline").inner_text())

            page.get_by_role("button", name="Apply approved synthetic evidence").click()
            page.get_by_text(
                "Approved synthetic serial and user-role evidence added to the draft."
            ).wait_for()
            self.assertEqual(page.locator("#missing-evidence").inner_text(), "None identified")

            page.get_by_role("button", name="Approve draft").click()
            page.get_by_text("Review recorded. No operational action was executed.").wait_for()
            self.assertIn("Draft approved", page.locator("#audit-timeline").inner_text())
            self.assertEqual(page.locator("#state-badge").inner_text(), "APPROVED DRAFT")
            browser.close()

    def test_queue_filters_and_information_request_draft_are_day_work_ready(self) -> None:
        browser_path = os.getenv("FIELD_BRIDGE_CHROME_PATH")
        mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if browser_path is None and mac_chrome.exists():
            browser_path = str(mac_chrome)

        with sync_playwright() as playwright:
            launch = {"headless": True}
            if browser_path:
                launch["executable_path"] = browser_path
            browser = playwright.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(f"http://127.0.0.1:{self.port}", wait_until="networkidle")

            self.assertEqual(page.locator("#ticket-requester").inner_text(), "Site operations coordinator")
            self.assertEqual(page.locator("#ticket-account").inner_text(), "Civic Research")
            self.assertEqual(page.locator("#queue-row-count").inner_text(), "2 tickets")
            self.assertIn("Managed print", page.locator("#scenario-list").inner_text())
            self.assertIn("Unknown", page.locator("#scenario-list").inner_text())
            self.assertIn("Due today", page.locator("#scenario-list").inner_text())

            page.get_by_role("button", name="Open 1").click()
            self.assertEqual(page.locator(".scenario-card").count(), 1)
            page.get_by_role("button", name="Prepared 1").click()
            self.assertEqual(page.locator(".scenario-card").count(), 1)
            page.get_by_role("button", name="All 2").click()

            page.get_by_role("button", name="Run triage").click()
            page.get_by_text("Coordinator review required").wait_for()
            page.get_by_role("button", name="Prepare information request").click()
            page.get_by_text("Draft only · not sent").wait_for()

            self.assertIn("serial number", page.locator("#outreach-draft").inner_text())
            self.assertEqual(page.locator("#state-badge").inner_text(), "CHANGES REQUESTED")
            self.assertIn("Changes requested", page.locator("#audit-timeline").inner_text())
            self.assertEqual(page.locator("#ticket-status").inner_text(), "Awaiting requester")
            browser.close()


if __name__ == "__main__":
    unittest.main()
