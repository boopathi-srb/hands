# Run replay-d6c721fe95a6

- Started: 2026-09-28T17:53:25.534197+00:00
- Last event: 2026-09-28T17:53:28.629166+00:00
- Events: 61 (control_transferred 4, run_started 1, step_started 5, subflow_started 1, observed 6, observation 4, policy_decision 8, action 4, action_attempted 4, action_result 8, checkpoint 1, step_finished 5, target_resolved 3, recovery_applied 1, escalation_requested 1, escalation_raised 1, escalation_resolved 1, escalation_handled 1, subflow_finished 1, run_finished 1)
- Files: json 2, snapshot 1, screenshot 1

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.003s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.654s | observed |  |  |  |  |  |
| 8 | +0.655s | observation | login_open |  |  |  |  |
| 9 | +0.655s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.655s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.655s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.655s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.682s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.682s | action_result | login_open |  |  |  | ok |
| 15 | +1.385s | observed |  |  |  |  |  |
| 16 | +1.386s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.386s | step_finished | login_open |  |  |  | ok |
| 18 | +1.386s | step_started | login_user | type |  |  |  |
| 19 | +1.553s | observed |  |  |  |  |  |
| 20 | +1.553s | observation | login_user |  |  |  |  |
| 21 | +1.553s | target_resolved | login_user |  |  |  |  |
| 22 | +1.553s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.554s | action | login_user | type |  |  |  |
| 24 | +1.554s | action_attempted |  | type |  |  |  |
| 25 | +1.554s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.605s | action_result |  | type |  |  | ok |
| 27 | +1.606s | action_result | login_user |  |  |  | ok |
| 28 | +1.606s | step_finished | login_user |  |  |  | ok |
| 29 | +1.606s | step_started | login_password | type |  |  |  |
| 30 | +1.919s | observed |  |  |  |  |  |
| 31 | +1.919s | observation | login_password |  |  |  |  |
| 32 | +1.919s | target_resolved | login_password |  |  |  |  |
| 33 | +1.919s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.919s | action | login_password | type |  |  |  |
| 35 | +1.920s | action_attempted |  | type |  |  |  |
| 36 | +1.920s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.944s | action_result |  | type |  |  | ok |
| 38 | +1.945s | action_result | login_password |  |  |  | ok |
| 39 | +1.945s | step_finished | login_password |  |  |  | ok |
| 40 | +1.945s | step_started | login_submit | click |  |  |  |
| 41 | +2.267s | observed |  |  |  |  |  |
| 42 | +2.267s | observation | login_submit |  |  |  |  |
| 43 | +2.267s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.268s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.268s | action | login_submit | click |  |  |  |
| 46 | +2.268s | action_attempted |  | click |  |  |  |
| 47 | +2.268s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.271s | action_result |  | click |  |  | ok |
| 49 | +2.272s | action_result | login_submit |  |  |  | ok |
| 50 | +3.071s | observed |  |  |  |  |  |
| 51 | +3.071s | recovery_applied | login_submit |  |  |  |  |
| 54 | +3.094s | escalation_requested | login_submit |  | Member identity verification requires a human operator. |  |  |
| 55 | +3.094s | escalation_raised | login_submit |  | Member identity verification requires a human operator. |  |  |
| 56 | +3.094s | control_transferred |  |  | escalation replay-d6c721fe95a6-intervention-1: stuck |  |  |
| 57 | +3.094s | control_transferred |  |  | scripted operator for replay-d6c721fe95a6-intervention-1 |  |  |
| 58 | +3.094s | control_transferred |  |  | operator handed back control |  |  |
| 59 | +3.094s | escalation_resolved |  |  | scripted operator chose abort |  | abort |
| 60 | +3.094s | escalation_handled |  |  | scripted operator chose abort |  | abort |
| 61 | +3.094s | step_finished | login_submit |  |  |  | failed |
| 62 | +3.095s | subflow_finished |  |  |  |  |  |
| 63 | +3.095s | step_finished | sign_on |  |  |  | failed |
| 65 | +3.095s | run_finished |  |  | Member identity verification requires a human operator. |  | escalated |

## Files

- `capability.json` (json, seq 2)
- `snapshots/052-replay-d6c721fe95a6-intervention-1.json` (snapshot, seq 52)
- `screenshots/053-replay-d6c721fe95a6-intervention-1.png` (screenshot, seq 53)
- `result.json` (json, seq 64)

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
- `escalation_requested`: custom event kind
- `escalation_raised`: human intervention raised
- `escalation_resolved`: custom event kind
- `escalation_handled`: custom event kind
- `subflow_finished`: custom event kind
- `run_finished`: run ended
