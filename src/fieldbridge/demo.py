"""A repeatable synthetic-only CLI demonstration."""

from __future__ import annotations

import json

from .engine import evaluate_ticket
from .models import Ticket


def run_demo() -> dict[str, object]:
    """Return the demo decision without writing state or contacting anyone."""

    ticket = Ticket(
        ticket_id="FB-DEMO-001",
        contract_id="civic-research",
        priority="P2",
        category="device_print_unavailable",
        summary="Synthetic replacement request after a repeat paper-path issue.",
        serial_number="SYN-DEMO-001",
        replacement_needed=True,
        part_available_locally=True,
        site_access="chaperone_required",
        actual_user_known=False,
    )
    return evaluate_ticket(ticket).as_dict()


def main() -> None:
    print(json.dumps(run_demo(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
