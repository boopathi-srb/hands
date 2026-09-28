# Run replay-27f4c86ba1c9

- Started: 2026-09-28T17:50:55.038811+00:00
- Last event: 2026-09-28T17:51:00.278802+00:00
- Events: 96 (control_transferred 1, run_started 1, step_started 8, subflow_started 1, observed 13, observation 7, policy_decision 14, action 7, action_attempted 7, action_result 14, checkpoint 5, step_finished 8, target_resolved 6, recovery_applied 1, subflow_finished 1, output_extracted 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.002s | run_started |  |  |  |  |  |
| 4 | +0.003s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.686s | observed |  |  |  |  |  |
| 8 | +0.686s | observation | login_open |  |  |  |  |
| 9 | +0.686s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.687s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.687s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.687s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.696s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.697s | action_result | login_open |  |  |  | ok |
| 15 | +1.405s | observed |  |  |  |  |  |
| 16 | +1.406s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.406s | step_finished | login_open |  |  |  | ok |
| 18 | +1.406s | step_started | login_user | type |  |  |  |
| 19 | +1.571s | observed |  |  |  |  |  |
| 20 | +1.571s | observation | login_user |  |  |  |  |
| 21 | +1.572s | target_resolved | login_user |  |  |  |  |
| 22 | +1.572s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.572s | action | login_user | type |  |  |  |
| 24 | +1.572s | action_attempted |  | type |  |  |  |
| 25 | +1.572s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.601s | action_result |  | type |  |  | ok |
| 27 | +1.601s | action_result | login_user |  |  |  | ok |
| 28 | +1.601s | step_finished | login_user |  |  |  | ok |
| 29 | +1.601s | step_started | login_password | type |  |  |  |
| 30 | +1.940s | observed |  |  |  |  |  |
| 31 | +1.940s | observation | login_password |  |  |  |  |
| 32 | +1.940s | target_resolved | login_password |  |  |  |  |
| 33 | +1.940s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.940s | action | login_password | type |  |  |  |
| 35 | +1.941s | action_attempted |  | type |  |  |  |
| 36 | +1.941s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.959s | action_result |  | type |  |  | ok |
| 38 | +1.960s | action_result | login_password |  |  |  | ok |
| 39 | +1.960s | step_finished | login_password |  |  |  | ok |
| 40 | +1.960s | step_started | login_submit | click |  |  |  |
| 41 | +2.295s | observed |  |  |  |  |  |
| 42 | +2.296s | observation | login_submit |  |  |  |  |
| 43 | +2.296s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.297s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.297s | action | login_submit | click |  |  |  |
| 46 | +2.297s | action_attempted |  | click |  |  |  |
| 47 | +2.297s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.300s | action_result |  | click |  |  | ok |
| 49 | +2.301s | action_result | login_submit |  |  |  | ok |
| 50 | +3.078s | observed |  |  |  |  |  |
| 51 | +3.078s | recovery_applied | login_submit |  |  |  |  |
| 52 | +3.079s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 53 | +3.079s | action | login_submit | click |  |  |  |
| 54 | +3.079s | action_attempted |  | click |  |  |  |
| 55 | +3.079s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 56 | +3.087s | action_result |  | click |  |  | ok |
| 57 | +3.087s | action_result | login_submit |  |  |  | ok |
| 58 | +3.421s | observed |  |  |  |  |  |
| 59 | +3.421s | checkpoint | login_submit |  |  |  | ok |
| 60 | +3.421s | step_finished | login_submit |  |  |  | recovered |
| 61 | +3.421s | subflow_finished |  |  |  |  |  |
| 62 | +3.604s | observed |  |  |  |  |  |
| 63 | +3.605s | checkpoint | sign_on |  |  |  | ok |
| 64 | +3.605s | step_finished | sign_on |  |  |  | ok |
| 65 | +3.605s | step_started | type_member_number_textbox | type |  |  |  |
| 66 | +3.788s | observed |  |  |  |  |  |
| 67 | +3.788s | observation | type_member_number_textbox |  |  |  |  |
| 68 | +3.788s | target_resolved | type_member_number_textbox |  |  |  |  |
| 69 | +3.789s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 70 | +3.789s | action | type_member_number_textbox | type |  |  |  |
| 71 | +3.789s | action_attempted |  | type |  |  |  |
| 72 | +3.789s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 73 | +3.798s | action_result |  | type |  |  | ok |
| 74 | +3.798s | action_result | type_member_number_textbox |  |  |  | ok |
| 75 | +3.798s | step_finished | type_member_number_textbox |  |  |  | ok |
| 76 | +3.798s | step_started | click_search_button | click |  |  |  |
| 77 | +4.137s | observed |  |  |  |  |  |
| 78 | +4.138s | observation | click_search_button |  |  |  |  |
| 79 | +4.138s | target_resolved | click_search_button |  |  |  |  |
| 80 | +4.138s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 81 | +4.138s | action | click_search_button | click |  |  |  |
| 82 | +4.138s | action_attempted |  | click |  |  |  |
| 83 | +4.139s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 84 | +4.143s | action_result |  | click |  |  | ok |
| 85 | +4.143s | action_result | click_search_button |  |  |  | ok |
| 86 | +4.872s | observed |  |  |  |  |  |
| 87 | +4.873s | checkpoint | click_search_button |  |  |  | ok |
| 88 | +4.873s | step_finished | click_search_button |  |  |  | ok |
| 89 | +4.873s | step_started | read_savings_balance | extract |  |  |  |
| 90 | +5.056s | observed |  |  |  |  |  |
| 91 | +5.056s | observation | read_savings_balance |  |  |  |  |
| 92 | +5.057s | target_resolved | read_savings_balance |  |  |  |  |
| 93 | +5.057s | output_extracted | read_savings_balance |  |  |  |  |
| 94 | +5.057s | step_finished | read_savings_balance |  |  |  | ok |
| 95 | +5.239s | observed |  |  |  |  |  |
| 96 | +5.239s | checkpoint |  |  |  |  | ok |
| 98 | +5.240s | run_finished |  |  |  |  | success |

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
