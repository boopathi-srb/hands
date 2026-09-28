# Run replay-b88ec552cd42

- Started: 2026-09-28T17:51:01.743290+00:00
- Last event: 2026-09-28T17:51:06.660697+00:00
- Events: 96 (control_transferred 1, run_started 1, step_started 8, subflow_started 1, observed 13, observation 7, policy_decision 14, action 7, action_attempted 7, action_result 14, checkpoint 5, step_finished 8, target_resolved 6, recovery_applied 1, subflow_finished 1, output_extracted 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.002s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.681s | observed |  |  |  |  |  |
| 8 | +0.681s | observation | login_open |  |  |  |  |
| 9 | +0.681s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.682s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.682s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.682s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.690s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.690s | action_result | login_open |  |  |  | ok |
| 15 | +1.384s | observed |  |  |  |  |  |
| 16 | +1.384s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.384s | step_finished | login_open |  |  |  | ok |
| 18 | +1.385s | step_started | login_user | type |  |  |  |
| 19 | +1.550s | observed |  |  |  |  |  |
| 20 | +1.550s | observation | login_user |  |  |  |  |
| 21 | +1.550s | target_resolved | login_user |  |  |  |  |
| 22 | +1.550s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.550s | action | login_user | type |  |  |  |
| 24 | +1.551s | action_attempted |  | type |  |  |  |
| 25 | +1.551s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.613s | action_result |  | type |  |  | ok |
| 27 | +1.613s | action_result | login_user |  |  |  | ok |
| 28 | +1.613s | step_finished | login_user |  |  |  | ok |
| 29 | +1.613s | step_started | login_password | type |  |  |  |
| 30 | +1.950s | observed |  |  |  |  |  |
| 31 | +1.950s | observation | login_password |  |  |  |  |
| 32 | +1.951s | target_resolved | login_password |  |  |  |  |
| 33 | +1.951s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.951s | action | login_password | type |  |  |  |
| 35 | +1.951s | action_attempted |  | type |  |  |  |
| 36 | +1.951s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.972s | action_result |  | type |  |  | ok |
| 38 | +1.972s | action_result | login_password |  |  |  | ok |
| 39 | +1.972s | step_finished | login_password |  |  |  | ok |
| 40 | +1.972s | step_started | login_submit | click |  |  |  |
| 41 | +2.300s | observed |  |  |  |  |  |
| 42 | +2.300s | observation | login_submit |  |  |  |  |
| 43 | +2.300s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.301s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.301s | action | login_submit | click |  |  |  |
| 46 | +2.301s | action_attempted |  | click |  |  |  |
| 47 | +2.301s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.304s | action_result |  | click |  |  | ok |
| 49 | +2.304s | action_result | login_submit |  |  |  | ok |
| 50 | +2.457s | observed |  |  |  |  |  |
| 51 | +2.457s | recovery_applied | login_submit |  |  |  |  |
| 52 | +2.458s | policy_decision | login_submit | press 'Enter' | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'press' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 53 | +2.458s | action | login_submit | press 'Enter' |  |  |  |
| 54 | +2.459s | action_attempted |  | press 'Enter' |  |  |  |
| 55 | +2.459s | policy_decision |  | press 'Enter' | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'press' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 56 | +2.463s | action_result |  | press 'Enter' |  |  | ok |
| 57 | +2.463s | action_result | login_submit |  |  |  | ok |
| 58 | +3.033s | observed |  |  |  |  |  |
| 59 | +3.034s | checkpoint | login_submit |  |  |  | ok |
| 60 | +3.034s | step_finished | login_submit |  |  |  | recovered |
| 61 | +3.034s | subflow_finished |  |  |  |  |  |
| 62 | +3.248s | observed |  |  |  |  |  |
| 63 | +3.249s | checkpoint | sign_on |  |  |  | ok |
| 64 | +3.249s | step_finished | sign_on |  |  |  | ok |
| 65 | +3.249s | step_started | type_member_number_textbox | type |  |  |  |
| 66 | +3.450s | observed |  |  |  |  |  |
| 67 | +3.450s | observation | type_member_number_textbox |  |  |  |  |
| 68 | +3.450s | target_resolved | type_member_number_textbox |  |  |  |  |
| 69 | +3.451s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 70 | +3.451s | action | type_member_number_textbox | type |  |  |  |
| 71 | +3.451s | action_attempted |  | type |  |  |  |
| 72 | +3.451s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 73 | +3.460s | action_result |  | type |  |  | ok |
| 74 | +3.460s | action_result | type_member_number_textbox |  |  |  | ok |
| 75 | +3.460s | step_finished | type_member_number_textbox |  |  |  | ok |
| 76 | +3.460s | step_started | click_search_button | click |  |  |  |
| 77 | +3.799s | observed |  |  |  |  |  |
| 78 | +3.800s | observation | click_search_button |  |  |  |  |
| 79 | +3.800s | target_resolved | click_search_button |  |  |  |  |
| 80 | +3.800s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 81 | +3.800s | action | click_search_button | click |  |  |  |
| 82 | +3.800s | action_attempted |  | click |  |  |  |
| 83 | +3.800s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 84 | +3.803s | action_result |  | click |  |  | ok |
| 85 | +3.803s | action_result | click_search_button |  |  |  | ok |
| 86 | +4.535s | observed |  |  |  |  |  |
| 87 | +4.535s | checkpoint | click_search_button |  |  |  | ok |
| 88 | +4.535s | step_finished | click_search_button |  |  |  | ok |
| 89 | +4.536s | step_started | read_savings_balance | extract |  |  |  |
| 90 | +4.734s | observed |  |  |  |  |  |
| 91 | +4.734s | observation | read_savings_balance |  |  |  |  |
| 92 | +4.734s | target_resolved | read_savings_balance |  |  |  |  |
| 93 | +4.734s | output_extracted | read_savings_balance |  |  |  |  |
| 94 | +4.734s | step_finished | read_savings_balance |  |  |  | ok |
| 95 | +4.916s | observed |  |  |  |  |  |
| 96 | +4.917s | checkpoint |  |  |  |  | ok |
| 98 | +4.917s | run_finished |  |  |  |  | success |

## Files

- `capability.json` (json, seq 2)
- `result.json` (json, seq 97)

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
- `output_extracted`: custom event kind
- `run_finished`: run ended
