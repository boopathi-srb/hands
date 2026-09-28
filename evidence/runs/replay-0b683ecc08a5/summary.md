# Run replay-0b683ecc08a5

- Started: 2026-09-28T17:50:27.092233+00:00
- Last event: 2026-09-28T17:50:31.993400+00:00
- Events: 88 (control_transferred 1, run_started 1, step_started 8, subflow_started 1, observed 12, observation 7, policy_decision 12, action 6, action_attempted 6, action_result 12, checkpoint 5, step_finished 8, target_resolved 6, subflow_finished 1, output_extracted 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.002s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.646s | observed |  |  |  |  |  |
| 8 | +0.647s | observation | login_open |  |  |  |  |
| 9 | +0.647s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.647s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.648s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.648s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.676s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.676s | action_result | login_open |  |  |  | ok |
| 15 | +1.420s | observed |  |  |  |  |  |
| 16 | +1.420s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.420s | step_finished | login_open |  |  |  | ok |
| 18 | +1.420s | step_started | login_user | type |  |  |  |
| 19 | +1.585s | observed |  |  |  |  |  |
| 20 | +1.586s | observation | login_user |  |  |  |  |
| 21 | +1.586s | target_resolved | login_user |  |  |  |  |
| 22 | +1.586s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.586s | action | login_user | type |  |  |  |
| 24 | +1.586s | action_attempted |  | type |  |  |  |
| 25 | +1.586s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.648s | action_result |  | type |  |  | ok |
| 27 | +1.649s | action_result | login_user |  |  |  | ok |
| 28 | +1.649s | step_finished | login_user |  |  |  | ok |
| 29 | +1.649s | step_started | login_password | type |  |  |  |
| 30 | +1.972s | observed |  |  |  |  |  |
| 31 | +1.972s | observation | login_password |  |  |  |  |
| 32 | +1.972s | target_resolved | login_password |  |  |  |  |
| 33 | +1.972s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.972s | action | login_password | type |  |  |  |
| 35 | +1.972s | action_attempted |  | type |  |  |  |
| 36 | +1.973s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +2.000s | action_result |  | type |  |  | ok |
| 38 | +2.000s | action_result | login_password |  |  |  | ok |
| 39 | +2.000s | step_finished | login_password |  |  |  | ok |
| 40 | +2.000s | step_started | login_submit | click |  |  |  |
| 41 | +2.338s | observed |  |  |  |  |  |
| 42 | +2.338s | observation | login_submit |  |  |  |  |
| 43 | +2.338s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.339s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.339s | action | login_submit | click |  |  |  |
| 46 | +2.339s | action_attempted |  | click |  |  |  |
| 47 | +2.340s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.344s | action_result |  | click |  |  | ok |
| 49 | +2.344s | action_result | login_submit |  |  |  | ok |
| 50 | +3.087s | observed |  |  |  |  |  |
| 51 | +3.087s | checkpoint | login_submit |  |  |  | ok |
| 52 | +3.088s | step_finished | login_submit |  |  |  | ok |
| 53 | +3.088s | subflow_finished |  |  |  |  |  |
| 54 | +3.284s | observed |  |  |  |  |  |
| 55 | +3.284s | checkpoint | sign_on |  |  |  | ok |
| 56 | +3.284s | step_finished | sign_on |  |  |  | ok |
| 57 | +3.284s | step_started | type_member_number_textbox | type |  |  |  |
| 58 | +3.450s | observed |  |  |  |  |  |
| 59 | +3.450s | observation | type_member_number_textbox |  |  |  |  |
| 60 | +3.450s | target_resolved | type_member_number_textbox |  |  |  |  |
| 61 | +3.451s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 62 | +3.451s | action | type_member_number_textbox | type |  |  |  |
| 63 | +3.451s | action_attempted |  | type |  |  |  |
| 64 | +3.451s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 65 | +3.459s | action_result |  | type |  |  | ok |
| 66 | +3.460s | action_result | type_member_number_textbox |  |  |  | ok |
| 67 | +3.460s | step_finished | type_member_number_textbox |  |  |  | ok |
| 68 | +3.460s | step_started | click_search_button | click |  |  |  |
| 69 | +3.803s | observed |  |  |  |  |  |
| 70 | +3.803s | observation | click_search_button |  |  |  |  |
| 71 | +3.803s | target_resolved | click_search_button |  |  |  |  |
| 72 | +3.804s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +3.804s | action | click_search_button | click |  |  |  |
| 74 | +3.804s | action_attempted |  | click |  |  |  |
| 75 | +3.804s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 76 | +3.807s | action_result |  | click |  |  | ok |
| 77 | +3.807s | action_result | click_search_button |  |  |  | ok |
| 78 | +4.536s | observed |  |  |  |  |  |
| 79 | +4.537s | checkpoint | click_search_button |  |  |  | ok |
| 80 | +4.537s | step_finished | click_search_button |  |  |  | ok |
| 81 | +4.537s | step_started | read_savings_balance | extract |  |  |  |
| 82 | +4.719s | observed |  |  |  |  |  |
| 83 | +4.720s | observation | read_savings_balance |  |  |  |  |
| 84 | +4.720s | target_resolved | read_savings_balance |  |  |  |  |
| 85 | +4.720s | output_extracted | read_savings_balance |  |  |  |  |
| 86 | +4.720s | step_finished | read_savings_balance |  |  |  | ok |
| 87 | +4.900s | observed |  |  |  |  |  |
| 88 | +4.901s | checkpoint |  |  |  |  | ok |
| 90 | +4.901s | run_finished |  |  |  |  | success |

## Files

- `capability.json` (json, seq 2)
- `result.json` (json, seq 89)

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
- `output_extracted`: custom event kind
- `run_finished`: run ended
