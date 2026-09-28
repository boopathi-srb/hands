# Run replay-6c8720c5f346

- Started: 2026-09-28T17:50:32.757720+00:00
- Last event: 2026-09-28T17:50:37.126040+00:00
- Events: 80 (control_transferred 1, run_started 1, step_started 7, subflow_started 1, observed 10, observation 6, policy_decision 12, action 6, action_attempted 6, action_result 12, checkpoint 3, step_finished 7, target_resolved 5, subflow_finished 1, outcome_detected 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.003s | run_started |  |  |  |  |  |
| 4 | +0.003s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.003s | subflow_started |  |  |  |  |  |
| 6 | +0.003s | step_started | login_open | open |  |  |  |
| 7 | +0.650s | observed |  |  |  |  |  |
| 8 | +0.651s | observation | login_open |  |  |  |  |
| 9 | +0.651s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.651s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.651s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.651s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.659s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.659s | action_result | login_open |  |  |  | ok |
| 15 | +1.354s | observed |  |  |  |  |  |
| 16 | +1.354s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.354s | step_finished | login_open |  |  |  | ok |
| 18 | +1.354s | step_started | login_user | type |  |  |  |
| 19 | +1.520s | observed |  |  |  |  |  |
| 20 | +1.521s | observation | login_user |  |  |  |  |
| 21 | +1.521s | target_resolved | login_user |  |  |  |  |
| 22 | +1.521s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.521s | action | login_user | type |  |  |  |
| 24 | +1.521s | action_attempted |  | type |  |  |  |
| 25 | +1.521s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.536s | action_result |  | type |  |  | ok |
| 27 | +1.536s | action_result | login_user |  |  |  | ok |
| 28 | +1.536s | step_finished | login_user |  |  |  | ok |
| 29 | +1.537s | step_started | login_password | type |  |  |  |
| 30 | +1.871s | observed |  |  |  |  |  |
| 31 | +1.871s | observation | login_password |  |  |  |  |
| 32 | +1.872s | target_resolved | login_password |  |  |  |  |
| 33 | +1.872s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.872s | action | login_password | type |  |  |  |
| 35 | +1.872s | action_attempted |  | type |  |  |  |
| 36 | +1.872s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.884s | action_result |  | type |  |  | ok |
| 38 | +1.884s | action_result | login_password |  |  |  | ok |
| 39 | +1.884s | step_finished | login_password |  |  |  | ok |
| 40 | +1.884s | step_started | login_submit | click |  |  |  |
| 41 | +2.221s | observed |  |  |  |  |  |
| 42 | +2.221s | observation | login_submit |  |  |  |  |
| 43 | +2.221s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.222s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.222s | action | login_submit | click |  |  |  |
| 46 | +2.222s | action_attempted |  | click |  |  |  |
| 47 | +2.222s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.225s | action_result |  | click |  |  | ok |
| 49 | +2.225s | action_result | login_submit |  |  |  | ok |
| 50 | +2.954s | observed |  |  |  |  |  |
| 51 | +2.954s | checkpoint | login_submit |  |  |  | ok |
| 52 | +2.954s | step_finished | login_submit |  |  |  | ok |
| 53 | +2.954s | subflow_finished |  |  |  |  |  |
| 54 | +3.152s | observed |  |  |  |  |  |
| 55 | +3.152s | checkpoint | sign_on |  |  |  | ok |
| 56 | +3.152s | step_finished | sign_on |  |  |  | ok |
| 57 | +3.152s | step_started | type_member_number_textbox | type |  |  |  |
| 58 | +3.319s | observed |  |  |  |  |  |
| 59 | +3.319s | observation | type_member_number_textbox |  |  |  |  |
| 60 | +3.319s | target_resolved | type_member_number_textbox |  |  |  |  |
| 61 | +3.319s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 62 | +3.319s | action | type_member_number_textbox | type |  |  |  |
| 63 | +3.320s | action_attempted |  | type |  |  |  |
| 64 | +3.320s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 65 | +3.328s | action_result |  | type |  |  | ok |
| 66 | +3.328s | action_result | type_member_number_textbox |  |  |  | ok |
| 67 | +3.328s | step_finished | type_member_number_textbox |  |  |  | ok |
| 68 | +3.328s | step_started | click_search_button | click |  |  |  |
| 69 | +3.670s | observed |  |  |  |  |  |
| 70 | +3.671s | observation | click_search_button |  |  |  |  |
| 71 | +3.671s | target_resolved | click_search_button |  |  |  |  |
| 72 | +3.671s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +3.671s | action | click_search_button | click |  |  |  |
| 74 | +3.671s | action_attempted |  | click |  |  |  |
| 75 | +3.671s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 76 | +3.674s | action_result |  | click |  |  | ok |
| 77 | +3.674s | action_result | click_search_button |  |  |  | ok |
| 78 | +4.367s | observed |  |  |  |  |  |
| 79 | +4.368s | outcome_detected | click_search_button |  | No member found for number 99999. |  | MEMBER_NOT_FOUND |
| 80 | +4.368s | step_finished | click_search_button |  |  |  | ok |
| 82 | +4.368s | run_finished | click_search_button |  |  |  | business_outcome |

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
