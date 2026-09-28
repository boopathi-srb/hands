"""`python -m hands.surfaces.desktop_macos <bundle_id> <out.json> [--quit-if-launched]`

Observes a native app once and writes its Observation JSON (plus a PNG screenshot next to it).
Prints the ObserveOutcome as JSON. Exit codes: 0 ok, 2 accessibility permission missing, 1 other.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from hands.surfaces.desktop_macos.observe_app import ObserveOutcome, observe_app_to_json

EXIT_CODES = {"ok": 0, "permission_missing": 2}


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m hands.surfaces.desktop_macos", description=__doc__
    )
    parser.add_argument("bundle_id", help="e.g. com.apple.calculator")
    parser.add_argument("out_path", help="where to write the Observation JSON")
    parser.add_argument(
        "--quit-if-launched", action="store_true", help="quit the app afterwards if we launched it"
    )
    return parser.parse_args(list(argv))


def exit_code_for(outcome: ObserveOutcome) -> int:
    return EXIT_CODES.get(outcome.status, 1)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    outcome = observe_app_to_json(
        arguments.bundle_id, arguments.out_path, arguments.quit_if_launched
    )
    print(outcome.model_dump_json(indent=2))
    return exit_code_for(outcome)


if __name__ == "__main__":
    sys.exit(main())
