# Run replay-4ece1ded80fc

- Started: 2026-09-28T17:51:07.518789+00:00
- Last event: 2026-09-28T17:51:16.329833+00:00
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
| 9 | +0.657s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.658s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.658s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.658s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.665s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.665s | action_result | login_open |  |  |  | ok |
| 15 | +1.359s | observed |  |  |  |  |  |
| 16 | +1.360s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.360s | step_finished | login_open |  |  |  | ok |
| 18 | +1.360s | step_started | login_user | type |  |  |  |
| 19 | +1.524s | observed |  |  |  |  |  |
| 20 | +1.524s | observation | login_user |  |  |  |  |
| 21 | +1.524s | target_resolved | login_user |  |  |  |  |
| 22 | +1.524s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.525s | action | login_user | type |  |  |  |
| 24 | +1.525s | action_attempted |  | type |  |  |  |
| 25 | +1.525s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.540s | action_result |  | type |  |  | ok |
| 27 | +1.540s | action_result | login_user |  |  |  | ok |
| 28 | +1.540s | step_finished | login_user |  |  |  | ok |
| 29 | +1.540s | step_started | login_password | type |  |  |  |
| 30 | +1.855s | observed |  |  |  |  |  |
| 31 | +1.855s | observation | login_password |  |  |  |  |
| 32 | +1.855s | target_resolved | login_password |  |  |  |  |
| 33 | +1.856s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.856s | action | login_password | type |  |  |  |
| 35 | +1.856s | action_attempted |  | type |  |  |  |
| 36 | +1.856s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.870s | action_result |  | type |  |  | ok |
| 38 | +1.870s | action_result | login_password |  |  |  | ok |
| 39 | +1.870s | step_finished | login_password |  |  |  | ok |
| 40 | +1.870s | step_started | login_submit | click |  |  |  |
| 41 | +2.208s | observed |  |  |  |  |  |
| 42 | +2.208s | observation | login_submit |  |  |  |  |
| 43 | +2.208s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.209s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.209s | action | login_submit | click |  |  |  |
| 46 | +2.209s | action_attempted |  | click |  |  |  |
| 47 | +2.209s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.212s | action_result |  | click |  |  | ok |
| 49 | +2.212s | action_result | login_submit |  |  |  | ok |
| 50 | +6.975s | observed |  |  |  |  |  |
| 51 | +6.976s | checkpoint | login_submit |  |  |  | ok |
| 52 | +6.976s | step_finished | login_submit |  |  |  | ok |
| 53 | +6.976s | subflow_finished |  |  |  |  |  |
| 54 | +7.171s | observed |  |  |  |  |  |
| 55 | +7.171s | checkpoint | sign_on |  |  |  | ok |
| 56 | +7.172s | step_finished | sign_on |  |  |  | ok |
| 57 | +7.172s | step_started | type_member_number_textbox | type |  |  |  |
| 58 | +7.339s | observed |  |  |  |  |  |
| 59 | +7.339s | observation | type_member_number_textbox |  |  |  |  |
| 60 | +7.339s | target_resolved | type_member_number_textbox |  |  |  |  |
| 61 | +7.340s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 62 | +7.340s | action | type_member_number_textbox | type |  |  |  |
| 63 | +7.340s | action_attempted |  | type |  |  |  |
| 64 | +7.340s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 65 | +7.349s | action_result |  | type |  |  | ok |
| 66 | +7.349s | action_result | type_member_number_textbox |  |  |  | ok |
| 67 | +7.349s | step_finished | type_member_number_textbox |  |  |  | ok |
| 68 | +7.349s | step_started | click_search_button | click |  |  |  |
| 69 | +7.690s | observed |  |  |  |  |  |
| 70 | +7.691s | observation | click_search_button |  |  |  |  |
| 71 | +7.691s | target_resolved | click_search_button |  |  |  |  |
| 72 | +7.691s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +7.691s | action | click_search_button | click |  |  |  |
| 74 | +7.691s | action_attempted |  | click |  |  |  |
| 75 | +7.691s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 76 | +7.694s | action_result |  | click |  |  | ok |
| 77 | +7.694s | action_result | click_search_button |  |  |  | ok |
| 78 | +8.441s | observed |  |  |  |  |  |
| 79 | +8.442s | checkpoint | click_search_button |  |  |  | ok |
| 80 | +8.442s | step_finished | click_search_button |  |  |  | ok |
| 81 | +8.442s | step_started | read_savings_balance | extract |  |  |  |
| 82 | +8.625s | observed |  |  |  |  |  |
| 83 | +8.625s | observation | read_savings_balance |  |  |  |  |
| 84 | +8.625s | target_resolved | read_savings_balance |  |  |  |  |
| 85 | +8.626s | output_extracted | read_savings_balance |  |  |  |  |
| 86 | +8.626s | step_finished | read_savings_balance |  |  |  | ok |
| 87 | +8.810s | observed |  |  |  |  |  |
| 88 | +8.810s | checkpoint |  |  |  |  | ok |
| 90 | +8.811s | run_finished |  |  |  |  | success |

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
