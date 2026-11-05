"""Print a replay result (JSON on stdin) as a short, readable summary for the CLI demo."""

from __future__ import annotations

import json
import sys


def describe_step(step: dict) -> str:
    recoveries = step["recoveries_applied"]
    note = f"  recovered via {', '.join(recoveries)}" if recoveries else ""
    return f"    {step['status']:9} {step['step_id']}{note}"


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        print("  (no result: is the mock app running on :8700?)")
        return
    result = json.loads(raw)
    failure = result.get("failure") or {}
    print(f"  status  : {result.get('status')}")
    if result.get("outputs"):
        print(f"  outputs : {result['outputs']}")
    if result.get("code"):
        print(f"  outcome : {result['code']} - {result.get('message') or ''}")
    if failure:
        print(f"  failure : {failure['code']} - {failure['message'][:110]}")
    for step in result.get("steps", []):
        print(describe_step(step))
    print(f"  evidence: {result.get('evidence_dir')}")


if __name__ == "__main__":
    main()
