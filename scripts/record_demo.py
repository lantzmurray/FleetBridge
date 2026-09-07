"""Rehearse and record the FieldBridge judge workflow.

By default, this script uses a deterministic in-process investigator so a
practice recording is repeatable without AWS credentials. A verified deployed
URL can be supplied explicitly for the final capture. The local overlay labels
the result as practice and must not be presented as AgentCore evidence.
"""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from playwright.sync_api import Page, sync_playwright

from fieldbridge.api import app, set_quota_service, set_run_service
from fieldbridge.engine import decision_card_for
from fieldbridge.evidence import known_facts
from fieldbridge.models import InvestigationResult, RawTicket, ToolTraceEvent
from fieldbridge.run_service import LocalRunService
from fieldbridge.workflow import InMemoryQuotaService

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "playwright"
VIDEO_NAME = "fieldbridge-judge-demo.webm"
PACE_SCALES = {"quick": 1.0, "voiceover": 5.5}


def _recording_investigator(raw: RawTicket, correlation_id: str) -> InvestigationResult:
    """Return the approved synthetic path used for a repeatable recording."""

    if raw.ticket_id == "FB-DEMO-001":
        tool_names = (
            "load_case",
            "contract_policy",
            "service_history",
            "site_access_policy",
            "fulfillment_requirements",
            "safety_boundary",
            "validate_draft",
        )
    else:
        tool_names = (
            "load_case",
            "contract_policy",
            "routing_policy",
            "safety_boundary",
            "validate_draft",
        )
    facts = known_facts(raw.ticket_id)
    return InvestigationResult(
        mode="live",
        model_id="scripted-local-fixture",
        correlation_id=correlation_id,
        extracted_facts=facts,
        decision_card=decision_card_for(raw, facts),
        tool_trace=tuple(
            ToolTraceEvent(
                tool_name=name,
                status="ok",
                duration_ms=180 + index * 47,
                correlation_id=correlation_id,
            )
            for index, name in enumerate(tool_names)
        ),
    )


def _start_server(port: int = 0) -> tuple[uvicorn.Server, threading.Thread, int]:
    """Start the same FastAPI surface used by the browser test."""

    set_run_service(
        LocalRunService(investigator=_recording_investigator, rehearsal=True)
    )
    set_quota_service(
        InMemoryQuotaService(
            hmac_secret=b"recording-only",
            per_client_daily_limit=20,
            global_daily_limit=20,
        )
    )
    if port == 0:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return server, thread, port
        except OSError:
            time.sleep(0.05)
    server.should_exit = True
    raise RuntimeError("local demo server did not start")


def _inject_overlays(page: Page) -> None:
    """Add a visible cursor and voiceover-friendly subtitle bar."""

    page.evaluate(
        """
        () => {
          if (!document.getElementById('demo-cursor')) {
            const cursor = document.createElement('div');
            cursor.id = 'demo-cursor';
            cursor.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
            </svg>`;
            cursor.style.cssText = 'position:fixed;z-index:999999;pointer-events:none;width:24px;height:24px;transition:left .1s,top .1s;filter:drop-shadow(1px 1px 2px rgba(0,0,0,.3));';
            document.body.appendChild(cursor);
            document.addEventListener('mousemove', (event) => {
              cursor.style.left = `${event.clientX}px`;
              cursor.style.top = `${event.clientY}px`;
            });
          }
          if (!document.getElementById('demo-subtitle')) {
            const bar = document.createElement('div');
            bar.id = 'demo-subtitle';
            bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:999998;text-align:center;padding:12px 24px;background:rgba(8,15,29,.88);color:white;font-family:-apple-system,Segoe UI,sans-serif;font-size:16px;font-weight:600;letter-spacing:.2px;pointer-events:none;';
            document.body.appendChild(bar);
          }
        }
        """
    )


def _wait(page: Page, pause_ms: int, pace_scale: float) -> None:
    page.wait_for_timeout(round(pause_ms * pace_scale))


def _subtitle(page: Page, text: str, pause_ms: int, pace_scale: float) -> None:
    page.evaluate(
        """(value) => {
          const bar = document.getElementById('demo-subtitle');
          if (bar) bar.textContent = value;
        }""",
        text,
    )
    _wait(page, pause_ms, pace_scale)


def _move_and_click(page: Page, locator: Any, label: str, pace_scale: float) -> None:
    """Move visibly to a control before clicking it."""

    if not locator.is_visible():
        raise RuntimeError(f"recording selector is not visible: {label}")
    locator.scroll_into_view_if_needed()
    _wait(page, 250, pace_scale)
    box = locator.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=10)
        _wait(page, 350, pace_scale)
    locator.click()
    _wait(page, 1100, pace_scale)


def _assert_visible(page: Page, selector: str, label: str) -> None:
    if not page.locator(selector).first.is_visible():
        raise RuntimeError(f"rehearsal selector is not visible: {label} ({selector})")


def _run_flow(
    page: Page,
    *,
    record: bool,
    pace_scale: float,
    local_rehearsal: bool,
) -> None:
    """Run the flagship correction/approval and the contrasting fax path."""

    page.goto(page.url, wait_until="networkidle")
    _inject_overlays(page)
    opening_label = (
        "Practice capture · synthetic fixtures only"
        if local_rehearsal
        else "FieldBridge · verified deployment capture"
    )
    _subtitle(page, opening_label, 1800, pace_scale)

    _assert_visible(page, "#reset-button", "Reset")
    _assert_visible(page, "#run-button", "Run background sweep")
    _assert_visible(page, "[data-scenario-id='replacement-pressure']", "replacement scenario")
    _subtitle(page, "01 · A perfect replacement can still fail", 1700, pace_scale)
    _move_and_click(page, page.get_by_role("button", name="Reset"), "Reset demo", pace_scale)
    page.wait_for_load_state("networkidle")
    _inject_overlays(page)
    _subtitle(page, "02 · Start with a thin ticket", 1200, pace_scale)
    _move_and_click(
        page,
        page.get_by_role("button", name="Run background sweep"),
        "Run background sweep",
        pace_scale,
    )
    page.get_by_text("Coordinator review required").wait_for()
    page.screenshot(path=str(OUTPUT_DIR / "02-decision-card.png"), full_page=True)
    _subtitle(
        page,
        "03 · Investigate contract, access, routing, and fulfillment",
        1800,
        pace_scale,
    )
    page.evaluate("window.scrollTo({top: 440, behavior: 'smooth'})")
    _wait(page, 1300, pace_scale)
    _subtitle(
        page,
        "04 · SLA, access, user, and serial gaps become visible",
        1800,
        pace_scale,
    )

    _move_and_click(
        page,
        page.get_by_role("button", name="Prepare information request"),
        "Prepare information request",
        pace_scale,
    )
    page.get_by_text("Draft only · not sent").wait_for()
    page.screenshot(path=str(OUTPUT_DIR / "03-information-request.png"), full_page=True)
    _subtitle(
        page,
        "05 · Missing facts become a draft request—never an automatic message",
        1800,
        pace_scale,
    )

    _move_and_click(
        page,
        page.get_by_role("button", name="Reset view"),
        "Reset demo",
        pace_scale,
    )
    page.wait_for_load_state("networkidle")
    _inject_overlays(page)
    _move_and_click(
        page,
        page.get_by_role("button", name="Run background sweep"),
        "Run background sweep",
        pace_scale,
    )
    page.get_by_text("Coordinator review required").wait_for()
    page.evaluate("window.scrollTo({top: 440, behavior: 'smooth'})")
    _wait(page, 900, pace_scale)

    _move_and_click(
        page,
        page.get_by_role("button", name="Apply approved synthetic evidence"),
        "Apply approved synthetic evidence",
        pace_scale,
    )
    page.get_by_text("Approved synthetic serial and user-role evidence added to the draft.").wait_for()
    _subtitle(
        page,
        "06 · One bounded correction closes the evidence gap",
        1500,
        pace_scale,
    )
    _move_and_click(
        page,
        page.get_by_role("button", name="Approve draft"),
        "Approve draft",
        pace_scale,
    )
    page.get_by_text("Review recorded. No operational action was executed.").wait_for()
    page.screenshot(path=str(OUTPUT_DIR / "04-approved-audit.png"), full_page=True)
    _subtitle(page, "07 · Approval records review, never dispatch", 1800, pace_scale)

    _move_and_click(
        page,
        page.locator("[data-scenario-id='fax-routing']"),
        "Fax routing case",
        pace_scale,
    )
    _subtitle(
        page,
        "08 · A different case chooses a different tool path",
        1500,
        pace_scale,
    )
    _move_and_click(
        page,
        page.get_by_role("button", name="Run background sweep"),
        "Run fax sweep",
        pace_scale,
    )
    page.get_by_text("Ready to route").wait_for()
    page.screenshot(path=str(OUTPUT_DIR / "05-fax-routing.png"), full_page=True)
    _subtitle(
        page,
        "09 · Fax routing without inventing a device serial",
        1800,
        pace_scale,
    )
    if record:
        page.locator("#boundary-title").scroll_into_view_if_needed()
        _wait(page, 900, pace_scale)
        _subtitle(
            page,
            "10 · Prepare the safest next human decision",
            1800,
            pace_scale,
        )


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("--base-url must not contain credentials")
    return value.rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearse", action="store_true", help="run selectors without saving video")
    parser.add_argument("--serve", action="store_true", help="open an interactive local rehearsal server")
    parser.add_argument("--port", type=int, default=8081, help="port used with --serve")
    parser.add_argument(
        "--base-url",
        help="record an already verified HTTP(S) deployment instead of the local fixture",
    )
    parser.add_argument(
        "--pace",
        choices=("quick", "voiceover"),
        default="voiceover",
        help="quick smoke capture or narration-ready pacing",
    )
    args = parser.parse_args()
    if args.serve and args.base_url:
        parser.error("--serve and --base-url cannot be combined")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    if args.base_url:
        target_url = _validated_base_url(args.base_url)
    else:
        os.environ["DEPLOYMENT_REVISION"] = "recording-rehearsal"
        server, thread, port = _start_server(args.port if args.serve else 0)
        target_url = f"http://127.0.0.1:{port}"
    if args.serve:
        print(f"FieldBridge rehearsal: http://127.0.0.1:{port}/#operations")
        print("Synthetic scripted investigator · no live AWS claim")
        try:
            assert thread is not None
            thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            assert server is not None
            server.should_exit = True
            thread.join(timeout=5)
        return 0
    video_path: Path | None = None
    pace_scale = PACE_SCALES["quick"] if args.rehearse else PACE_SCALES[args.pace]
    try:
        with sync_playwright() as playwright:
            launch: dict[str, object] = {"headless": True}
            chrome_path = os.getenv("FIELD_BRIDGE_CHROME_PATH")
            default_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            if not chrome_path and default_chrome.exists():
                chrome_path = str(default_chrome)
            if chrome_path:
                launch["executable_path"] = chrome_path
            browser = playwright.chromium.launch(**launch)
            context_kwargs: dict[str, object] = {"viewport": {"width": 1280, "height": 900}}
            if not args.rehearse:
                context_kwargs["record_video_dir"] = str(OUTPUT_DIR)
                context_kwargs["record_video_size"] = {"width": 1280, "height": 900}
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(target_url, wait_until="networkidle")
            _run_flow(
                page,
                record=not args.rehearse,
                pace_scale=pace_scale,
                local_rehearsal=args.base_url is None,
            )
            if not args.rehearse:
                context.close()
                source = page.video.path() if page.video else None
                if source:
                    video_path = OUTPUT_DIR / VIDEO_NAME
                    Path(source).replace(video_path)
                    print(f"Video saved: {video_path}")
            else:
                context.close()
                print("REHEARSAL PASSED")
            browser.close()
    finally:
        if server is not None and thread is not None:
            server.should_exit = True
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
