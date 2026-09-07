"""Bounded synthetic evidence available to the FieldBridge agent tools."""

from __future__ import annotations

from datetime import UTC, datetime

from .models import ExtractedFacts, RawTicket

_SCENARIOS = {
    "replacement-pressure": RawTicket(
        ticket_id="FB-DEMO-001",
        contract_id="civic-research",
        reported_at=datetime(2026, 9, 4, 19, 30, tzinfo=UTC),
        note="Urgent—replace the printer. Send someone today.",
        device_ref="DEVICE-DEMO-001",
        site_ref="SITE-CIVIC-01",
        unknown_fields=("actual_user", "serial_number"),
    ),
    "fax-routing": RawTicket(
        ticket_id="FB-DEMO-002",
        contract_id="metro-financial",
        reported_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
        note="Inbound enterprise fax delivery stopped for a business workflow.",
        device_ref=None,
        site_ref="SITE-METRO-01",
        unknown_fields=("serial_number",),
    ),
}

_FACTS = {
    "FB-DEMO-001": ExtractedFacts(
        requested_priority="P1",
        category="device_print_unavailable",
        replacement_needed=True,
        serial_number=None,
        actual_user_known=False,
        site_access="chaperone_required",
        part_available_locally=True,
        unknown_fields=("serial_number", "actual_user"),
    ),
    "FB-DEMO-002": ExtractedFacts(
        requested_priority="P2",
        category="enterprise_fax",
        replacement_needed=False,
        serial_number=None,
        actual_user_known=True,
        site_access="stationed",
        part_available_locally=False,
        unknown_fields=("serial_number",),
    ),
}

_SERVICE_HISTORY = {
    "FB-DEMO-001": {
        "summary": "Two prior synthetic visits found a repeat paper-path fault.",
        "repeat_issue": True,
        "completion_evidence": "unknown",
    },
    "FB-DEMO-002": {
        "summary": "No device repair history applies to this platform incident.",
        "repeat_issue": False,
        "completion_evidence": "unknown",
    },
}

_SITE_ACCESS = {
    "SITE-CIVIC-01": {
        "access": "chaperone_required",
        "constraint": "A site-provided chaperone must be confirmed before scheduling.",
    },
    "SITE-METRO-01": {
        "access": "stationed",
        "constraint": "Onsite support is stationed; no visit is required for this platform case.",
    },
}

_INVENTORY = {
    "FB-DEMO-001": {
        "local_part_available": True,
        "source": "synthetic regional inventory snapshot",
    },
    "FB-DEMO-002": {
        "local_part_available": False,
        "source": "not applicable to platform routing",
    },
}

_REPLACEMENT_DEPENDENCIES = {
    "FB-DEMO-001": (
        "register replacement IP",
        "reconfigure managed print access",
        "reconnect document workflows",
    ),
    "FB-DEMO-002": (),
}


def list_scenarios() -> tuple[dict[str, object], ...]:
    """Return the fixed public demo scenario catalog."""

    return tuple(
        {
            "scenario_id": scenario_id,
            "ticket_id": ticket.ticket_id,
            "note": ticket.note,
        }
        for scenario_id, ticket in _SCENARIOS.items()
    )


def get_scenario(scenario_id: str) -> RawTicket:
    """Load one approved immutable scenario."""

    try:
        return _SCENARIOS[scenario_id]
    except KeyError as error:
        raise ValueError("scenario_id is not an approved synthetic scenario") from error


def get_case(ticket_id: str) -> RawTicket:
    """Load a case by its synthetic ticket identifier."""

    for ticket in _SCENARIOS.values():
        if ticket.ticket_id == ticket_id:
            return ticket
    raise ValueError("ticket_id is not an approved synthetic case")


def known_facts(ticket_id: str) -> ExtractedFacts:
    """Return the deterministic fixture truth used to validate model output."""

    try:
        return _FACTS[ticket_id]
    except KeyError as error:
        raise ValueError("ticket_id is not an approved synthetic case") from error


def get_service_history(ticket_id: str) -> dict[str, object]:
    """Return a copy of bounded synthetic service-history evidence."""

    try:
        return dict(_SERVICE_HISTORY[ticket_id])
    except KeyError as error:
        raise ValueError("ticket_id is not an approved synthetic case") from error


def get_site_access(site_ref: str) -> dict[str, object]:
    """Return a copy of bounded synthetic access policy evidence."""

    try:
        return dict(_SITE_ACCESS[site_ref])
    except KeyError as error:
        raise ValueError("site_ref is not an approved synthetic site") from error


def get_inventory(ticket_id: str) -> dict[str, object]:
    """Return a copy of bounded synthetic inventory evidence."""

    try:
        return dict(_INVENTORY[ticket_id])
    except KeyError as error:
        raise ValueError("ticket_id is not an approved synthetic case") from error


def get_replacement_dependencies(ticket_id: str) -> tuple[str, ...]:
    """Return bounded post-replacement dependencies for one approved case."""

    try:
        return _REPLACEMENT_DEPENDENCIES[ticket_id]
    except KeyError as error:
        raise ValueError("ticket_id is not an approved synthetic case") from error
