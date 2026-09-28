# Run replay-b8fd4634c051

- Started: 2026-09-28T17:51:58.880478+00:00
- Last event: 2026-09-28T17:53:07.306301+00:00
- Events: 120 (control_transferred 5, run_started 1, step_started 8, subflow_started 1, observed 15, observation 7, policy_decision 12, action 6, action_attempted 6, action_result 12, checkpoint 4, step_finished 8, target_resolved 6, recovery_applied 1, escalation_requested 1, escalation_raised 1, human_action 21, escalation_resolved 1, escalation_handled 1, subflow_finished 1, output_extracted 1, run_finished 1)
- Files: json 2, snapshot 1, screenshot 1

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.038s | run_started |  |  |  |  |  |
| 4 | +0.038s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.038s | subflow_started |  |  |  |  |  |
| 6 | +0.038s | step_started | login_open | open |  |  |  |
| 7 | +0.647s | observed |  |  |  |  |  |
| 8 | +0.647s | observation | login_open |  |  |  |  |
| 9 | +0.647s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.647s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.647s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.648s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.666s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.666s | action_result | login_open |  |  |  | ok |
| 15 | +1.410s | observed |  |  |  |  |  |
| 16 | +1.410s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.410s | step_finished | login_open |  |  |  | ok |
| 18 | +1.410s | step_started | login_user | type |  |  |  |
| 19 | +1.577s | observed |  |  |  |  |  |
| 20 | +1.577s | observation | login_user |  |  |  |  |
| 21 | +1.577s | target_resolved | login_user |  |  |  |  |
| 22 | +1.578s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.578s | action | login_user | type |  |  |  |
| 24 | +1.578s | action_attempted |  | type |  |  |  |
| 25 | +1.578s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.631s | action_result |  | type |  |  | ok |
| 27 | +1.631s | action_result | login_user |  |  |  | ok |
| 28 | +1.631s | step_finished | login_user |  |  |  | ok |
| 29 | +1.631s | step_started | login_password | type |  |  |  |
| 30 | +1.940s | observed |  |  |  |  |  |
| 31 | +1.940s | observation | login_password |  |  |  |  |
| 32 | +1.940s | target_resolved | login_password |  |  |  |  |
| 33 | +1.941s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.941s | action | login_password | type |  |  |  |
| 35 | +1.941s | action_attempted |  | type |  |  |  |
| 36 | +1.941s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.966s | action_result |  | type |  |  | ok |
| 38 | +1.966s | action_result | login_password |  |  |  | ok |
| 39 | +1.966s | step_finished | login_password |  |  |  | ok |
| 40 | +1.966s | step_started | login_submit | click |  |  |  |
| 41 | +2.290s | observed |  |  |  |  |  |
| 42 | +2.291s | observation | login_submit |  |  |  |  |
| 43 | +2.291s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.291s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.291s | action | login_submit | click |  |  |  |
| 46 | +2.291s | action_attempted |  | click |  |  |  |
| 47 | +2.292s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.294s | action_result |  | click |  |  | ok |
| 49 | +2.294s | action_result | login_submit |  |  |  | ok |
| 50 | +3.045s | observed |  |  |  |  |  |
| 51 | +3.045s | recovery_applied | login_submit |  |  |  |  |
| 54 | +3.066s | escalation_requested | login_submit |  | Member identity verification requires a human operator. |  |  |
| 55 | +3.066s | escalation_raised | login_submit |  | Member identity verification requires a human operator. |  |  |
| 56 | +3.067s | control_transferred |  |  | escalation replay-b8fd4634c051-intervention-1: stuck |  |  |
| 57 | +52.445s | control_transferred |  |  | took control for replay-b8fd4634c051-intervention-1 |  |  |
| 58 | +52.787s | observed |  |  |  |  |  |
| 59 | +52.954s | human_action |  | click |  |  |  |
| 60 | +53.309s | human_action |  | type |  |  |  |
| 61 | +53.321s | human_action |  | type |  |  |  |
| 62 | +53.324s | human_action |  | type |  |  |  |
| 63 | +53.327s | human_action |  | type |  |  |  |
| 64 | +53.330s | human_action |  | type |  |  |  |
| 65 | +53.332s | human_action |  | type |  |  |  |
| 66 | +53.333s | human_action |  | type |  |  |  |
| 67 | +53.334s | human_action |  | type |  |  |  |
| 68 | +53.335s | human_action |  | type |  |  |  |
| 69 | +53.336s | human_action |  | type |  |  |  |
| 70 | +53.337s | human_action |  | type |  |  |  |
| 71 | +53.338s | human_action |  | type |  |  |  |
| 72 | +53.339s | human_action |  | type |  |  |  |
| 73 | +53.340s | human_action |  | type |  |  |  |
| 74 | +53.340s | human_action |  | type |  |  |  |
| 75 | +53.341s | human_action |  | type |  |  |  |
| 76 | +53.341s | human_action |  | type |  |  |  |
| 77 | +53.342s | human_action |  | type |  |  |  |
| 78 | +53.342s | human_action |  | type |  |  |  |
| 79 | +53.958s | observed |  |  |  |  |  |
| 80 | +53.981s | human_action |  | click |  |  |  |
| 81 | +66.215s | control_transferred |  |  | handed back replay-b8fd4634c051-intervention-1 |  |  |
| 82 | +66.216s | control_transferred |  |  | resumed after replay-b8fd4634c051-intervention-1: resume |  |  |
| 83 | +66.216s | escalation_resolved |  |  | Verified member identity with a supervisor override; resuming automation. |  | resume |
| 84 | +66.217s | escalation_handled |  |  | Verified member identity with a supervisor override; resuming automation. |  | resume |
| 85 | +66.457s | observed |  |  |  |  |  |
| 86 | +66.458s | step_finished | login_submit |  |  |  | human |
| 87 | +66.459s | subflow_finished |  |  |  |  |  |
| 88 | +66.639s | observed |  |  |  |  |  |
| 89 | +66.640s | checkpoint | sign_on |  |  |  | ok |
| 90 | +66.640s | step_finished | sign_on |  |  |  | ok |
| 91 | +66.641s | step_started | type_member_number_textbox | type |  |  |  |
| 92 | +66.825s | observed |  |  |  |  |  |
| 93 | +66.825s | observation | type_member_number_textbox |  |  |  |  |
| 94 | +66.825s | target_resolved | type_member_number_textbox |  |  |  |  |
| 95 | +66.826s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 96 | +66.826s | action | type_member_number_textbox | type |  |  |  |
| 97 | +66.826s | action_attempted |  | type |  |  |  |
| 98 | +66.827s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 99 | +66.869s | action_result |  | type |  |  | ok |
| 100 | +66.869s | action_result | type_member_number_textbox |  |  |  | ok |
| 101 | +66.869s | step_finished | type_member_number_textbox |  |  |  | ok |
| 102 | +66.869s | step_started | click_search_button | click |  |  |  |
| 103 | +67.210s | observed |  |  |  |  |  |
| 104 | +67.211s | observation | click_search_button |  |  |  |  |
| 105 | +67.211s | target_resolved | click_search_button |  |  |  |  |
| 106 | +67.211s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 107 | +67.211s | action | click_search_button | click |  |  |  |
| 108 | +67.211s | action_attempted |  | click |  |  |  |
| 109 | +67.211s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 110 | +67.218s | action_result |  | click |  |  | ok |
| 111 | +67.218s | action_result | click_search_button |  |  |  | ok |
| 112 | +68.057s | observed |  |  |  |  |  |
| 113 | +68.058s | checkpoint | click_search_button |  |  |  | ok |
| 114 | +68.058s | step_finished | click_search_button |  |  |  | ok |
| 115 | +68.058s | step_started | read_savings_balance | extract |  |  |  |
| 116 | +68.240s | observed |  |  |  |  |  |
| 117 | +68.240s | observation | read_savings_balance |  |  |  |  |
| 118 | +68.240s | target_resolved | read_savings_balance |  |  |  |  |
| 119 | +68.241s | output_extracted | read_savings_balance |  |  |  |  |
| 120 | +68.241s | step_finished | read_savings_balance |  |  |  | ok |
| 121 | +68.425s | observed |  |  |  |  |  |
| 122 | +68.425s | checkpoint |  |  |  |  | ok |
| 124 | +68.426s | run_finished |  |  |  |  | success |

## Files

- `capability.json` (json, seq 2)
- `snapshots/052-replay-b8fd4634c051-intervention-1.json` (snapshot, seq 52)
- `screenshots/053-replay-b8fd4634c051-intervention-1.png` (screenshot, seq 53)
- `result.json` (json, seq 123)

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
- `human_action`: operator input
- `escalation_resolved`: custom event kind
- `escalation_handled`: custom event kind
- `subflow_finished`: custom event kind
- `output_extracted`: custom event kind
- `run_finished`: run ended
