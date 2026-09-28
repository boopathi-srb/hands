#!/usr/bin/env bash
# Replays the saved capability through every result class against the live mock app and keeps the evidence.
# Prerequisites: the mock app on :8700 (`uv run python -m target_app --port 8700`) and a discovered capability
# in artifacts/. Each run writes evidence/runs/<run_id>/ and a one-line summary to evidence/replays.jsonl.
set -uo pipefail
cd "$(dirname "$0")/.."

EVIDENCE_ROOT="evidence/runs"
SUMMARY_FILE="evidence/replays.jsonl"
CAPABILITY="coreone.member_balance"
: > "$SUMMARY_FILE"

replay_case() {
  local case_name="$1"; shift
  uv run hands replay "$CAPABILITY" --escalation none --evidence-root "$EVIDENCE_ROOT" "$@" 2>/dev/null \
    | python3 -c "
import json, sys
result = json.load(sys.stdin)
failure = result.get('failure') or {}
print(json.dumps({
    'case': '$case_name',
    'status': result.get('status'),
    'outputs': result.get('outputs'),
    'code': result.get('code') or failure.get('code'),
    'message': result.get('message') or failure.get('message'),
    'recoveries': [[s['step_id'], s['recoveries_applied']] for s in result.get('steps', []) if s['recoveries_applied']],
    'fallback_steps': result.get('drift', {}).get('fallback_steps'),
    'evidence_dir': result.get('evidence_dir'),
}))" | tee -a "$SUMMARY_FILE"
}

replay_case success_other_member        -i member_number=10002
replay_case business_not_found          -i member_number=99999
replay_case business_restricted         -i member_number=40300
replay_case invalid_input_rejected      -i member_number=abc
replay_case recover_session_expired     -i member_number=10001 --fault session_expired:1
replay_case recover_maintenance_notice  -i member_number=10001 --fault maintenance_notice:1
replay_case recover_native_alert        -i member_number=10001 --fault native_alert:1
replay_case recover_slow_load           -i member_number=10001 --fault slow:1
replay_case recover_app_error_once      -i member_number=10001 --fault app_error:1
replay_case hard_fail_app_error_twice   -i member_number=10001 --fault app_error:2
replay_case hard_fail_identity_no_human -i member_number=10001 --fault identity_check:1
replay_case tenant_prairie_overlay      -i member_number=10002 --tenant prairie
