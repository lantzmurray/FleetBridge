"""A repeatable synthetic-only CLI demonstration of the investigation path."""

from __future__ import annotations

import json

from .evidence import get_scenario
from .strands_layer import run_investigation


def run_demo() -> dict[str, object]:
    """Run the approved flagship case through Strands or its labeled fallback."""

    result = run_investigation(get_scenario("replacement-pressure"))
    return result.model_dump(mode="json")


def main() -> None:
    print(json.dumps(run_demo(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
