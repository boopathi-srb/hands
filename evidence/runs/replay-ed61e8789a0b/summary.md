# Run replay-ed61e8789a0b

- Started: 2026-09-28T17:50:37.948153+00:00
- Last event: 2026-09-28T17:50:42.345433+00:00
- Events: 80 (control_transferred 1, run_started 1, step_started 7, subflow_started 1, observed 10, observation 6, policy_decision 12, action 6, action_attempted 6, action_result 12, checkpoint 3, step_finished 7, target_resolved 5, subflow_finished 1, outcome_detected 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.002s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.663s | observed |  |  |  |  |  |
| 8 | +0.663s | observation | login_open |  |  |  |  |
| 9 | +0.663s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.663s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.664s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.664s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.672s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.672s | action_result | login_open |  |  |  | ok |
| 15 | +1.382s | observed |  |  |  |  |  |
| 16 | +1.383s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.383s | step_finished | login_open |  |  |  | ok |
| 18 | +1.383s | step_started | login_user | type |  |  |  |
| 19 | +1.543s | observed |  |  |  |  |  |
| 20 | +1.543s | observation | login_user |  |  |  |  |
| 21 | +1.543s | target_resolved | login_user |  |  |  |  |
| 22 | +1.543s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.544s | action | login_user | type |  |  |  |
| 24 | +1.544s | action_attempted |  | type |  |  |  |
| 25 | +1.544s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.558s | action_result |  | type |  |  | ok |
| 27 | +1.558s | action_result | login_user |  |  |  | ok |
| 28 | +1.558s | step_finished | login_user |  |  |  | ok |
| 29 | +1.558s | step_started | login_password | type |  |  |  |
| 30 | +1.880s | observed |  |  |  |  |  |
| 31 | +1.881s | observation | login_password |  |  |  |  |
| 32 | +1.881s | target_resolved | login_password |  |  |  |  |
| 33 | +1.881s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.881s | action | login_password | type |  |  |  |
| 35 | +1.881s | action_attempted |  | type |  |  |  |
| 36 | +1.882s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.894s | action_result |  | type |  |  | ok |
| 38 | +1.894s | action_result | login_password |  |  |  | ok |
| 39 | +1.894s | step_finished | login_password |  |  |  | ok |
| 40 | +1.894s | step_started | login_submit | click |  |  |  |
| 41 | +2.246s | observed |  |  |  |  |  |
| 42 | +2.246s | observation | login_submit |  |  |  |  |
| 43 | +2.246s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.247s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.247s | action | login_submit | click |  |  |  |
| 46 | +2.248s | action_attempted |  | click |  |  |  |
| 47 | +2.248s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.252s | action_result |  | click |  |  | ok |
| 49 | +2.252s | action_result | login_submit |  |  |  | ok |
| 50 | +2.980s | observed |  |  |  |  |  |
| 51 | +2.981s | checkpoint | login_submit |  |  |  | ok |
| 52 | +2.981s | step_finished | login_submit |  |  |  | ok |
| 53 | +2.981s | subflow_finished |  |  |  |  |  |
| 54 | +3.175s | observed |  |  |  |  |  |
| 55 | +3.176s | checkpoint | sign_on |  |  |  | ok |
| 56 | +3.176s | step_finished | sign_on |  |  |  | ok |
| 57 | +3.176s | step_started | type_member_number_textbox | type |  |  |  |
| 58 | +3.344s | observed |  |  |  |  |  |
| 59 | +3.345s | observation | type_member_number_textbox |  |  |  |  |
| 60 | +3.345s | target_resolved | type_member_number_textbox |  |  |  |  |
| 61 | +3.345s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 62 | +3.345s | action | type_member_number_textbox | type |  |  |  |
| 63 | +3.345s | action_attempted |  | type |  |  |  |
| 64 | +3.345s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 65 | +3.354s | action_result |  | type |  |  | ok |
| 66 | +3.354s | action_result | type_member_number_textbox |  |  |  | ok |
| 67 | +3.354s | step_finished | type_member_number_textbox |  |  |  | ok |
| 68 | +3.354s | step_started | click_search_button | click |  |  |  |
| 69 | +3.694s | observed |  |  |  |  |  |
| 70 | +3.695s | observation | click_search_button |  |  |  |  |
| 71 | +3.695s | target_resolved | click_search_button |  |  |  |  |
| 72 | +3.695s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +3.695s | action | click_search_button | click |  |  |  |
| 74 | +3.695s | action_attempted |  | click |  |  |  |
| 75 | +3.695s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 76 | +3.698s | action_result |  | click |  |  | ok |
| 77 | +3.698s | action_result | click_search_button |  |  |  | ok |
| 78 | +4.396s | observed |  |  |  |  |  |
| 79 | +4.396s | outcome_detected | click_search_button |  | ACCESS DENIED: Member record is restricted (code 403-R) |  | MEMBER_RESTRICTED |
| 80 | +4.397s | step_finished | click_search_button |  |  |  | ok |
| 82 | +4.397s | run_finished | click_search_button |  |  |  | business_outcome |

## Files

- `capability.json` (json, seq 2)
- `result.json` (json, seq 81)

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
- `subflow_finished`: custom event kind
- `outcome_detected`: business outcome detected
- `run_finished`: run ended
