# Run replay-336aef34b540

- Started: 2026-09-28T17:51:28.564061+00:00
- Last event: 2026-09-28T17:51:34.260368+00:00
- Events: 111 (control_transferred 1, run_started 1, step_started 11, subflow_started 3, observed 13, observation 8, policy_decision 16, action 8, action_attempted 8, action_result 16, checkpoint 3, step_finished 11, target_resolved 6, recovery_applied 1, subflow_finished 3, run_restarted 1, run_finished 1)
- Files: json 2, snapshot 1, screenshot 1

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.003s | run_started |  |  |  |  |  |
| 4 | +0.003s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.691s | observed |  |  |  |  |  |
| 8 | +0.692s | observation | login_open |  |  |  |  |
| 9 | +0.692s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.692s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.692s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.692s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.702s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.702s | action_result | login_open |  |  |  | ok |
| 15 | +1.400s | observed |  |  |  |  |  |
| 16 | +1.400s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.400s | step_finished | login_open |  |  |  | ok |
| 18 | +1.400s | step_started | login_user | type |  |  |  |
| 19 | +1.560s | observed |  |  |  |  |  |
| 20 | +1.561s | observation | login_user |  |  |  |  |
| 21 | +1.561s | target_resolved | login_user |  |  |  |  |
| 22 | +1.561s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.561s | action | login_user | type |  |  |  |
| 24 | +1.561s | action_attempted |  | type |  |  |  |
| 25 | +1.562s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.598s | action_result |  | type |  |  | ok |
| 27 | +1.598s | action_result | login_user |  |  |  | ok |
| 28 | +1.598s | step_finished | login_user |  |  |  | ok |
| 29 | +1.598s | step_started | login_password | type |  |  |  |
| 30 | +1.929s | observed |  |  |  |  |  |
| 31 | +1.930s | observation | login_password |  |  |  |  |
| 32 | +1.930s | target_resolved | login_password |  |  |  |  |
| 33 | +1.930s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.930s | action | login_password | type |  |  |  |
| 35 | +1.931s | action_attempted |  | type |  |  |  |
| 36 | +1.931s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.956s | action_result |  | type |  |  | ok |
| 38 | +1.956s | action_result | login_password |  |  |  | ok |
| 39 | +1.956s | step_finished | login_password |  |  |  | ok |
| 40 | +1.956s | step_started | login_submit | click |  |  |  |
| 41 | +2.296s | observed |  |  |  |  |  |
| 42 | +2.297s | observation | login_submit |  |  |  |  |
| 43 | +2.297s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.298s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.298s | action | login_submit | click |  |  |  |
| 46 | +2.298s | action_attempted |  | click |  |  |  |
| 47 | +2.298s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.301s | action_result |  | click |  |  | ok |
| 49 | +2.301s | action_result | login_submit |  |  |  | ok |
| 50 | +3.029s | observed |  |  |  |  |  |
| 51 | +3.030s | recovery_applied | login_submit |  |  |  |  |
| 52 | +3.030s | subflow_started |  |  |  |  |  |
| 53 | +3.030s | step_started | login_open | open |  |  |  |
| 54 | +3.221s | observed |  |  |  |  |  |
| 55 | +3.221s | observation | login_open |  |  |  |  |
| 56 | +3.221s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 57 | +3.221s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 58 | +3.221s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 59 | +3.221s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 60 | +3.228s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 61 | +3.228s | action_result | login_open |  |  |  | ok |
| 62 | +3.911s | observed |  |  |  |  |  |
| 63 | +3.912s | checkpoint | login_open |  |  |  | ok |
| 64 | +3.912s | step_finished | login_open |  |  |  | ok |
| 65 | +3.912s | step_started | login_user | type |  |  |  |
| 66 | +4.077s | observed |  |  |  |  |  |
| 67 | +4.078s | observation | login_user |  |  |  |  |
| 68 | +4.078s | target_resolved | login_user |  |  |  |  |
| 69 | +4.078s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 70 | +4.078s | action | login_user | type |  |  |  |
| 71 | +4.078s | action_attempted |  | type |  |  |  |
| 72 | +4.078s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +4.086s | action_result |  | type |  |  | ok |
| 74 | +4.087s | action_result | login_user |  |  |  | ok |
| 75 | +4.087s | step_finished | login_user |  |  |  | ok |
| 76 | +4.087s | step_started | login_password | type |  |  |  |
| 77 | +4.412s | observed |  |  |  |  |  |
| 78 | +4.412s | observation | login_password |  |  |  |  |
| 79 | +4.412s | target_resolved | login_password |  |  |  |  |
| 80 | +4.412s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 81 | +4.412s | action | login_password | type |  |  |  |
| 82 | +4.413s | action_attempted |  | type |  |  |  |
| 83 | +4.413s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 84 | +4.423s | action_result |  | type |  |  | ok |
| 85 | +4.423s | action_result | login_password |  |  |  | ok |
| 86 | +4.424s | step_finished | login_password |  |  |  | ok |
| 87 | +4.424s | step_started | login_submit | click |  |  |  |
| 88 | +4.747s | observed |  |  |  |  |  |
| 89 | +4.748s | observation | login_submit |  |  |  |  |
| 90 | +4.748s | target_resolved | login_submit |  |  |  |  |
| 91 | +4.748s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 92 | +4.748s | action | login_submit | click |  |  |  |
| 93 | +4.748s | action_attempted |  | click |  |  |  |
| 94 | +4.748s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 95 | +4.752s | action_result |  | click |  |  | ok |
| 96 | +4.752s | action_result | login_submit |  |  |  | ok |
| 97 | +5.495s | observed |  |  |  |  |  |
| 98 | +5.495s | checkpoint | login_submit |  |  |  | ok |
| 99 | +5.495s | step_finished | login_submit |  |  |  | ok |
| 100 | +5.495s | subflow_finished |  |  |  |  |  |
| 101 | +5.496s | step_finished | login_submit |  |  |  | recovered |
| 102 | +5.496s | subflow_finished |  |  |  |  |  |
| 103 | +5.496s | step_finished | sign_on |  |  |  | ok |
| 104 | +5.496s | run_restarted |  |  | recovery 'transient_app_error' ran subflow 'login' then restart |  |  |
| 105 | +5.496s | step_started | sign_on | subflow |  |  |  |
| 106 | +5.496s | subflow_started |  |  |  |  |  |
| 107 | +5.496s | step_started | login_open | open |  |  |  |
| 108 | +5.665s | observed |  |  |  |  |  |
| 109 | +5.665s | step_finished | login_open |  |  |  | failed |
| 110 | +5.665s | subflow_finished |  |  |  |  |  |
| 111 | +5.665s | step_finished | sign_on |  |  |  | failed |
| 115 | +5.696s | run_finished | login_open |  |  |  | failed |

## Files

- `capability.json` (json, seq 2)
- `snapshots/112-failure-login_open.json` (snapshot, seq 112)
- `screenshots/113-failure-login_open.png` (screenshot, seq 113)
- `result.json` (json, seq 114)

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
- `run_restarted`: custom event kind
- `run_finished`: run ended
