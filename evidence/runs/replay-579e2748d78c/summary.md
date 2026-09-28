# Run replay-579e2748d78c

- Started: 2026-09-28T17:51:38.917771+00:00
- Last event: 2026-09-28T17:51:43.676417+00:00
- Events: 88 (control_transferred 1, run_started 1, step_started 8, subflow_started 1, observed 12, observation 7, policy_decision 12, action 6, action_attempted 6, action_result 12, checkpoint 5, step_finished 8, target_resolved 6, subflow_finished 1, output_extracted 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.003s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.657s | observed |  |  |  |  |  |
| 8 | +0.657s | observation | login_open |  |  |  |  |
| 9 | +0.658s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/prairie/login' | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'open' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 10 | +0.658s | action | login_open | open 'http://127.0.0.1:8700/t/prairie/login' |  |  |  |
| 11 | +0.658s | action_attempted |  | open 'http://127.0.0.1:8700/t/prairie/login' |  |  |  |
| 12 | +0.658s | policy_decision |  | open 'http://127.0.0.1:8700/t/prairie/login' | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'open' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 13 | +0.676s | action_result |  | open 'http://127.0.0.1:8700/t/prairie/login' |  |  | ok |
| 14 | +0.676s | action_result | login_open |  |  |  | ok |
| 15 | +1.376s | observed |  |  |  |  |  |
| 16 | +1.377s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.377s | step_finished | login_open |  |  |  | ok |
| 18 | +1.377s | step_started | login_user | type |  |  |  |
| 19 | +1.540s | observed |  |  |  |  |  |
| 20 | +1.540s | observation | login_user |  |  |  |  |
| 21 | +1.540s | target_resolved | login_user |  |  |  |  |
| 22 | +1.541s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'type' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 23 | +1.541s | action | login_user | type |  |  |  |
| 24 | +1.541s | action_attempted |  | type |  |  |  |
| 25 | +1.541s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'type' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 26 | +1.557s | action_result |  | type |  |  | ok |
| 27 | +1.557s | action_result | login_user |  |  |  | ok |
| 28 | +1.557s | step_finished | login_user |  |  |  | ok |
| 29 | +1.557s | step_started | login_password | type |  |  |  |
| 30 | +1.879s | observed |  |  |  |  |  |
| 31 | +1.880s | observation | login_password |  |  |  |  |
| 32 | +1.880s | target_resolved | login_password |  |  |  |  |
| 33 | +1.880s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'type' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 34 | +1.880s | action | login_password | type |  |  |  |
| 35 | +1.880s | action_attempted |  | type |  |  |  |
| 36 | +1.880s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'type' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 37 | +1.893s | action_result |  | type |  |  | ok |
| 38 | +1.893s | action_result | login_password |  |  |  | ok |
| 39 | +1.893s | step_finished | login_password |  |  |  | ok |
| 40 | +1.893s | step_started | login_submit | click |  |  |  |
| 41 | +2.222s | observed |  |  |  |  |  |
| 42 | +2.223s | observation | login_submit |  |  |  |  |
| 43 | +2.223s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.224s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'click' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 45 | +2.224s | action | login_submit | click |  |  |  |
| 46 | +2.224s | action_attempted |  | click |  |  |  |
| 47 | +2.224s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/prairie/login allowed by '/t/prairie/**'; 'click' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 48 | +2.227s | action_result |  | click |  |  | ok |
| 49 | +2.227s | action_result | login_submit |  |  |  | ok |
| 50 | +2.956s | observed |  |  |  |  |  |
| 51 | +2.956s | checkpoint | login_submit |  |  |  | ok |
| 52 | +2.956s | step_finished | login_submit |  |  |  | ok |
| 53 | +2.957s | subflow_finished |  |  |  |  |  |
| 54 | +3.138s | observed |  |  |  |  |  |
| 55 | +3.138s | checkpoint | sign_on |  |  |  | ok |
| 56 | +3.138s | step_finished | sign_on |  |  |  | ok |
| 57 | +3.138s | step_started | type_member_number_textbox | type |  |  |  |
| 58 | +3.306s | observed |  |  |  |  |  |
| 59 | +3.306s | observation | type_member_number_textbox |  |  |  |  |
| 60 | +3.306s | target_resolved | type_member_number_textbox |  |  |  |  |
| 61 | +3.306s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/prairie/main allowed by '/t/prairie/**'; 'type' is allowed in replay mode; no risk rule matche… | allow (risk.default) |  |
| 62 | +3.306s | action | type_member_number_textbox | type |  |  |  |
| 63 | +3.307s | action_attempted |  | type |  |  |  |
| 64 | +3.307s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/prairie/main allowed by '/t/prairie/**'; 'type' is allowed in replay mode; no risk rule matche… | allow (risk.default) |  |
| 65 | +3.316s | action_result |  | type |  |  | ok |
| 66 | +3.316s | action_result | type_member_number_textbox |  |  |  | ok |
| 67 | +3.316s | step_finished | type_member_number_textbox |  |  |  | ok |
| 68 | +3.316s | step_started | click_search_button | click |  |  |  |
| 69 | +3.658s | observed |  |  |  |  |  |
| 70 | +3.658s | observation | click_search_button |  |  |  |  |
| 71 | +3.658s | target_resolved | click_search_button |  |  |  |  |
| 72 | +3.658s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/prairie/main allowed by '/t/prairie/**'; 'click' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 73 | +3.658s | action | click_search_button | click |  |  |  |
| 74 | +3.659s | action_attempted |  | click |  |  |  |
| 75 | +3.659s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/prairie/main allowed by '/t/prairie/**'; 'click' is allowed in replay mode; no risk rule match… | allow (risk.default) |  |
| 76 | +3.662s | action_result |  | click |  |  | ok |
| 77 | +3.662s | action_result | click_search_button |  |  |  | ok |
| 78 | +4.391s | observed |  |  |  |  |  |
| 79 | +4.391s | checkpoint | click_search_button |  |  |  | ok |
| 80 | +4.391s | step_finished | click_search_button |  |  |  | ok |
| 81 | +4.391s | step_started | read_savings_balance | extract |  |  |  |
| 82 | +4.574s | observed |  |  |  |  |  |
| 83 | +4.574s | observation | read_savings_balance |  |  |  |  |
| 84 | +4.575s | target_resolved | read_savings_balance |  |  |  |  |
| 85 | +4.575s | output_extracted | read_savings_balance |  |  |  |  |
| 86 | +4.575s | step_finished | read_savings_balance |  |  |  | ok |
| 87 | +4.757s | observed |  |  |  |  |  |
| 88 | +4.758s | checkpoint |  |  |  |  | ok |
| 90 | +4.759s | run_finished |  |  |  |  | success |

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
