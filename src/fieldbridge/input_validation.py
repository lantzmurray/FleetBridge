"""Strict public-safe input validation for FieldBridge boundaries."""

from __future__ import annotations

import re
from typing import Any

from .engine import CONTRACTS, SUPPORTED_CATEGORIES
from .models import Ticket

_REQUIRED_FIELDS = {
    "ticket_id",
    "contract_id",
    "priority",
    "category",
    "summary",
    "serial_number",
    "replacement_needed",
    "part_available_locally",
    "site_access",
}
_OPTIONAL_FIELDS = {"actual_user_known"}
_ACCESS_VALUES = {"escorted", "chaperone_required", "stationed", "unknown"}
_SECRET_PATTERN = re.compile(r"(?:password|api[_-]?key|authorization|bearer)\s*[:=]", re.IGNORECASE)
_CONTACT_PATTERN = re.compile(
    r"(?:\b[\w.+-]+@[\w-]+\.[\w.-]+\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)",
    re.IGNORECASE,
)


def ticket_from_payload(payload: Any) -> Ticket:
    """Validate a small synthetic ticket payload before agent or API use.

    The allowlist intentionally rejects names, email addresses, locations,
    account values, credentials, attachments, and unbounded free text.
    """

    if not isinstance(payload, dict):
        raise ValueError("ticket payload must be an object")  # noqa: TRY004
    unexpected = set(payload) - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unexpected:
        raise ValueError("ticket payload contains unapproved fields")
    missing = _REQUIRED_FIELDS - set(payload)
    if missing:
        raise ValueError("ticket payload is missing required fields")

    ticket_id = _bounded_text(payload["ticket_id"], "ticket_id", 64)
    if not ticket_id.startswith("FB-"):
        raise ValueError("ticket_id must use the synthetic FB- prefix")
    contract_id = _bounded_text(payload["contract_id"], "contract_id", 64)
    if contract_id not in CONTRACTS:
        raise ValueError("contract_id is not an approved synthetic profile")

    priority = _bounded_text(payload["priority"], "priority", 2)
    if priority not in {"P1", "P2"}:
        raise ValueError("priority must be P1 or P2")
    category = _bounded_text(payload["category"], "category", 64)
    if category not in SUPPORTED_CATEGORIES:
        raise ValueError("category is not supported")
    summary = _bounded_text(payload["summary"], "summary", 1000)
    if _SECRET_PATTERN.search(summary):
        raise ValueError("summary contains secret-like content")
    if _CONTACT_PATTERN.search(summary):
        raise ValueError("summary contains contact-like content")

    serial_number = payload["serial_number"]
    if serial_number is not None:
        serial_number = _bounded_text(serial_number, "serial_number", 80)
        if not serial_number.startswith("SYN-"):
            raise ValueError("serial_number must use the synthetic SYN- prefix")
    _require_bool(payload["replacement_needed"], "replacement_needed")
    _require_bool(payload["part_available_locally"], "part_available_locally")
    site_access = _bounded_text(payload["site_access"], "site_access", 40)
    if site_access not in _ACCESS_VALUES:
        raise ValueError("site_access is not supported")
    actual_user_known = payload.get("actual_user_known", True)
    _require_bool(actual_user_known, "actual_user_known")

    return Ticket(
        ticket_id=ticket_id,
        contract_id=contract_id,
        priority=priority,
        category=category,
        summary=summary,
        serial_number=serial_number,
        replacement_needed=payload["replacement_needed"],
        part_available_locally=payload["part_available_locally"],
        site_access=site_access,
        actual_user_known=actual_user_known,
    )


def _bounded_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be non-empty and at most {maximum} characters")
    return value.strip()


def _require_bool(value: Any, field: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")  # noqa: TRY004
