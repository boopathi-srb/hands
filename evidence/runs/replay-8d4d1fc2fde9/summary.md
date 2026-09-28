# Run replay-8d4d1fc2fde9

- Started: 2026-09-28T17:51:35.224986+00:00
- Last event: 2026-09-28T17:51:38.279929+00:00
- Events: 54 (control_transferred 1, run_started 1, step_started 5, subflow_started 1, observed 6, observation 4, policy_decision 8, action 4, action_attempted 4, action_result 8, checkpoint 1, step_finished 5, target_resolved 3, recovery_applied 1, subflow_finished 1, run_finished 1)
- Files: json 2, snapshot 1, screenshot 1

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.002s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.002s | subflow_started |  |  |  |  |  |
| 6 | +0.002s | step_started | login_open | open |  |  |  |
| 7 | +0.667s | observed |  |  |  |  |  |
| 8 | +0.667s | observation | login_open |  |  |  |  |
| 9 | +0.668s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.668s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.668s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.668s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.676s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.677s | action_result | login_open |  |  |  | ok |
| 15 | +1.367s | observed |  |  |  |  |  |
| 16 | +1.368s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.368s | step_finished | login_open |  |  |  | ok |
| 18 | +1.368s | step_started | login_user | type |  |  |  |
| 19 | +1.533s | observed |  |  |  |  |  |
| 20 | +1.533s | observation | login_user |  |  |  |  |
| 21 | +1.533s | target_resolved | login_user |  |  |  |  |
| 22 | +1.533s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.534s | action | login_user | type |  |  |  |
| 24 | +1.534s | action_attempted |  | type |  |  |  |
| 25 | +1.534s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.554s | action_result |  | type |  |  | ok |
| 27 | +1.554s | action_result | login_user |  |  |  | ok |
| 28 | +1.554s | step_finished | login_user |  |  |  | ok |
| 29 | +1.554s | step_started | login_password | type |  |  |  |
| 30 | +1.884s | observed |  |  |  |  |  |
| 31 | +1.884s | observation | login_password |  |  |  |  |
| 32 | +1.884s | target_resolved | login_password |  |  |  |  |
| 33 | +1.885s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.885s | action | login_password | type |  |  |  |
| 35 | +1.885s | action_attempted |  | type |  |  |  |
| 36 | +1.885s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.907s | action_result |  | type |  |  | ok |
| 38 | +1.907s | action_result | login_password |  |  |  | ok |
| 39 | +1.907s | step_finished | login_password |  |  |  | ok |
| 40 | +1.907s | step_started | login_submit | click |  |  |  |
| 41 | +2.233s | observed |  |  |  |  |  |
| 42 | +2.234s | observation | login_submit |  |  |  |  |
| 43 | +2.234s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.234s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.234s | action | login_submit | click |  |  |  |
| 46 | +2.234s | action_attempted |  | click |  |  |  |
| 47 | +2.235s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.238s | action_result |  | click |  |  | ok |
| 49 | +2.238s | action_result | login_submit |  |  |  | ok |
| 50 | +3.034s | observed |  |  |  |  |  |
| 51 | +3.035s | recovery_applied | login_submit |  |  |  |  |
| 52 | +3.035s | step_finished | login_submit |  |  |  | failed |
| 53 | +3.035s | subflow_finished |  |  |  |  |  |
| 54 | +3.035s | step_finished | sign_on |  |  |  | failed |
| 58 | +3.055s | run_finished | login_submit |  |  |  | failed |

## Files

- `capability.json` (json, seq 2)
- `snapshots/055-failure-login_submit.json` (snapshot, seq 55)
- `screenshots/056-failure-login_submit.png` (screenshot, seq 56)
- `result.json` (json, seq 57)

## Event kinds

- `control_transferred`: control lease transferred
- `run_started`: run began
- `step_started`: custom event kind
- `subflow_started`: custom event kind
- `observed`: custom event kind
- `observation`: surface observed
- `policy_decision`: policy gate verdict
- `action`: action sent to surface
- `action_attempted`: custom event kind
- `action_result`: surface reported result
- `checkpoint`: checkpoint evaluated
- `step_finished`: custom event kind
- `target_resolved`: custom event kind
- `recovery_applied`: recovery rule applied
- `subflow_finished`: custom event kind
- `run_finished`: run ended
