#!/usr/bin/env bash
# Guided CLI demo: replays the saved capability through each result class with a visible browser.
# Needs the mock app running: uv run python -m target_app --port 8700
set -uo pipefail
cd "$(dirname "$0")/.."

bold=$'\033[1m'; dim=$'\033[2m'; reset=$'\033[0m'

show_case() {
  local title="$1"; shift
  printf '\n%s== %s ==%s\n%s$ hands replay coreone.member_balance %s%s\n' "$bold" "$title" "$reset" "$dim" "$*" "$reset"
  uv run hands replay coreone.member_balance --headed --escalation none "$@" 2>/dev/null | uv run python scripts/print_result.py
}

show_case "Success: another member"                -i member_number=10002
show_case "Business outcome: unknown member"       -i member_number=99999
show_case "Rejected before touching the app"       -i member_number=abc
show_case "Recovery: session expires mid-run"      -i member_number=10001 --fault session_expired:1
show_case "Hard failure: app error twice"          -i member_number=10001 --fault app_error:2
show_case "Second tenant through its overlay"      -i member_number=10001 --tenant prairie
printf '\n%sDone. Every run above used no model.%s\n' "$bold" "$reset"
