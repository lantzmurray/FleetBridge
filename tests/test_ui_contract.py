"""Static UI contract checks for the zero-build judge dashboard."""

from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).parents[1] / "src" / "fieldbridge" / "web"
RECORDING_SCRIPT = Path(__file__).parents[1] / "scripts" / "record_demo.py"


class FieldBridgeUiContractTests(unittest.TestCase):
    def test_javascript_uses_safe_dom_updates_and_all_review_actions(self) -> None:
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertIn("textContent", script)
        self.assertIn("approve", script)
        self.assertIn("request_changes", script)
        self.assertIn("reject", script)
        self.assertIn("/api/v1/runs", script)
        self.assertIn('event.type === "tool"', script)
        self.assertIn("No tool trace", script)
        self.assertIn('run.state === "PREPARED" || run.state === "REVIEW_REQUIRED"', script)
        self.assertIn("serial_and_user_confirmed", script)
        self.assertIn("Apply approved synthetic evidence", html)
        self.assertNotIn('id="requested-priority"', html)
        self.assertNotIn('id="allowed-priority"', html)
        self.assertNotIn("requestedPriority", script)
        self.assertNotIn("allowedPriority", script)
        self.assertIn('id="deadline"', html)
        self.assertIn('id="route-team"', html)
        self.assertIn('id="dispatch-recommendation"', html)

    def test_workspace_has_filterable_queue_context_and_bounded_followup(self) -> None:
        script = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

        for filter_name in ("all", "open", "awaiting", "closed"):
            self.assertIn(f'data-queue-filter="{filter_name}"', html)
        self.assertIn('id="ticket-requester"', html)
        self.assertIn('id="ticket-account"', html)
        self.assertIn('id="ticket-channel"', html)
        self.assertIn('id="ticket-status"', html)
        self.assertIn('id="request-info-button"', html)
        self.assertIn('id="outreach-draft"', html)
        self.assertIn("Draft only · not sent", html)
        for column in ("Time", "Summary", "Serial", "Application", "Contact", "Client", "Due", "Ticket"):
            self.assertIn(f'data-queue-column="{column.lower()}"', html)
        self.assertIn('class="queue-top inbox"', html)
        self.assertIn('class="ticket-record case-workspace"', html)
        self.assertIn('id="nav-my-queue-count"', html)
        self.assertIn('id="nav-awaiting-count"', html)
        self.assertIn('id="nav-prepared-count"', html)
        self.assertIn("filterQueue", script)
        self.assertIn("prepareInformationRequest", script)
        self.assertIn('reason_code: "insufficient_evidence"', script)
        self.assertNotIn("mailto:", html)

    def test_styles_include_responsive_focus_and_reduced_motion_rules(self) -> None:
        styles = (WEB_ROOT / "app.css").read_text(encoding="utf-8")

        self.assertIn(":focus-visible", styles)
        self.assertIn("prefers-reduced-motion", styles)
        self.assertIn("@media", styles)
        self.assertIn("min-height: 44px", styles)

    def test_demo_recorder_supports_voiceover_pacing_and_verified_live_target(self) -> None:
        script_path = RECORDING_SCRIPT
        if not script_path.exists():
            self.skipTest("recording script is an untracked local artifact")
        script = script_path.read_text(encoding="utf-8")

        self.assertIn('"--base-url"', script)
        self.assertIn('"--pace"', script)
        self.assertIn('choices=("quick", "voiceover")', script)
        self.assertIn('"voiceover": 5.5', script)
        self.assertIn("Practice capture · synthetic fixtures only", script)
        self.assertIn("#boundary-title", script)


if __name__ == "__main__":
    unittest.main()
