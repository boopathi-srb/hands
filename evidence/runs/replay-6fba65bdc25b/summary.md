# Run replay-6fba65bdc25b

- Started: 2026-09-28T17:51:17.179012+00:00
- Last event: 2026-09-28T17:51:26.943736+00:00
- Events: 189 (control_transferred 1, run_started 1, step_started 17, subflow_started 3, observed 24, observation 15, policy_decision 28, action 14, action_attempted 14, action_result 28, checkpoint 8, step_finished 17, target_resolved 12, recovery_applied 1, subflow_finished 3, run_restarted 1, output_extracted 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.004s | run_started |  |  |  |  |  |
| 4 | +0.006s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.006s | subflow_started |  |  |  |  |  |
| 6 | +0.006s | step_started | login_open | open |  |  |  |
| 7 | +0.664s | observed |  |  |  |  |  |
| 8 | +0.665s | observation | login_open |  |  |  |  |
| 9 | +0.665s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.665s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.665s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.665s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.674s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.674s | action_result | login_open |  |  |  | ok |
| 15 | +1.344s | observed |  |  |  |  |  |
| 16 | +1.345s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.345s | step_finished | login_open |  |  |  | ok |
| 18 | +1.345s | step_started | login_user | type |  |  |  |
| 19 | +1.526s | observed |  |  |  |  |  |
| 20 | +1.526s | observation | login_user |  |  |  |  |
| 21 | +1.527s | target_resolved | login_user |  |  |  |  |
| 22 | +1.527s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.527s | action | login_user | type |  |  |  |
| 24 | +1.527s | action_attempted |  | type |  |  |  |
| 25 | +1.527s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.547s | action_result |  | type |  |  | ok |
| 27 | +1.547s | action_result | login_user |  |  |  | ok |
| 28 | +1.547s | step_finished | login_user |  |  |  | ok |
| 29 | +1.547s | step_started | login_password | type |  |  |  |
| 30 | +1.860s | observed |  |  |  |  |  |
| 31 | +1.860s | observation | login_password |  |  |  |  |
| 32 | +1.861s | target_resolved | login_password |  |  |  |  |
| 33 | +1.861s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.861s | action | login_password | type |  |  |  |
| 35 | +1.861s | action_attempted |  | type |  |  |  |
| 36 | +1.861s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.881s | action_result |  | type |  |  | ok |
| 38 | +1.881s | action_result | login_password |  |  |  | ok |
| 39 | +1.881s | step_finished | login_password |  |  |  | ok |
| 40 | +1.881s | step_started | login_submit | click |  |  |  |
| 41 | +2.227s | observed |  |  |  |  |  |
| 42 | +2.228s | observation | login_submit |  |  |  |  |
| 43 | +2.229s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.230s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.230s | action | login_submit | click |  |  |  |
| 46 | +2.230s | action_attempted |  | click |  |  |  |
| 47 | +2.230s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.235s | action_result |  | click |  |  | ok |
| 49 | +2.235s | action_result | login_submit |  |  |  | ok |
| 50 | +2.981s | observed |  |  |  |  |  |
| 51 | +2.982s | recovery_applied | login_submit |  |  |  |  |
| 52 | +2.983s | subflow_started |  |  |  |  |  |
| 53 | +2.983s | step_started | login_open | open |  |  |  |
| 54 | +3.196s | observed |  |  |  |  |  |
| 55 | +3.197s | observation | login_open |  |  |  |  |
| 56 | +3.197s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 57 | +3.197s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 58 | +3.197s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 59 | +3.197s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 60 | +3.210s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 61 | +3.211s | action_result | login_open |  |  |  | ok |
| 62 | +3.894s | observed |  |  |  |  |  |
| 63 | +3.897s | checkpoint | login_open |  |  |  | ok |
| 64 | +3.897s | step_finished | login_open |  |  |  | ok |
| 65 | +3.897s | step_started | login_user | type |  |  |  |
| 66 | +4.061s | observed |  |  |  |  |  |
| 67 | +4.061s | observation | login_user |  |  |  |  |
| 68 | +4.061s | target_resolved | login_user |  |  |  |  |
| 69 | +4.061s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 70 | +4.062s | action | login_user | type |  |  |  |
| 71 | +4.062s | action_attempted |  | type |  |  |  |
| 72 | +4.062s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +4.077s | action_result |  | type |  |  | ok |
| 74 | +4.077s | action_result | login_user |  |  |  | ok |
| 75 | +4.077s | step_finished | login_user |  |  |  | ok |
| 76 | +4.077s | step_started | login_password | type |  |  |  |
| 77 | +4.414s | observed |  |  |  |  |  |
| 78 | +4.414s | observation | login_password |  |  |  |  |
| 79 | +4.414s | target_resolved | login_password |  |  |  |  |
| 80 | +4.415s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 81 | +4.415s | action | login_password | type |  |  |  |
| 82 | +4.415s | action_attempted |  | type |  |  |  |
| 83 | +4.415s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 84 | +4.428s | action_result |  | type |  |  | ok |
| 85 | +4.428s | action_result | login_password |  |  |  | ok |
| 86 | +4.428s | step_finished | login_password |  |  |  | ok |
| 87 | +4.428s | step_started | login_submit | click |  |  |  |
| 88 | +4.764s | observed |  |  |  |  |  |
| 89 | +4.765s | observation | login_submit |  |  |  |  |
| 90 | +4.765s | target_resolved | login_submit |  |  |  |  |
| 91 | +4.765s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 92 | +4.765s | action | login_submit | click |  |  |  |
| 93 | +4.765s | action_attempted |  | click |  |  |  |
| 94 | +4.765s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 95 | +4.769s | action_result |  | click |  |  | ok |
| 96 | +4.769s | action_result | login_submit |  |  |  | ok |
| 97 | +5.514s | observed |  |  |  |  |  |
| 98 | +5.514s | checkpoint | login_submit |  |  |  | ok |
| 99 | +5.514s | step_finished | login_submit |  |  |  | ok |
| 100 | +5.515s | subflow_finished |  |  |  |  |  |
| 101 | +5.515s | step_finished | login_submit |  |  |  | recovered |
| 102 | +5.515s | subflow_finished |  |  |  |  |  |
| 103 | +5.515s | step_finished | sign_on |  |  |  | ok |
| 104 | +5.515s | run_restarted |  |  | recovery 'transient_app_error' ran subflow 'login' then restart |  |  |
| 105 | +5.515s | step_started | sign_on | subflow |  |  |  |
| 106 | +5.515s | subflow_started |  |  |  |  |  |
| 107 | +5.515s | step_started | login_open | open |  |  |  |
| 108 | +5.695s | observed |  |  |  |  |  |
| 109 | +5.696s | observation | login_open |  |  |  |  |
| 110 | +5.696s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 111 | +5.696s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 112 | +5.696s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 113 | +5.696s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 114 | +5.702s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 115 | +5.702s | action_result | login_open |  |  |  | ok |
| 116 | +6.383s | observed |  |  |  |  |  |
| 117 | +6.383s | checkpoint | login_open |  |  |  | ok |
| 118 | +6.383s | step_finished | login_open |  |  |  | ok |
| 119 | +6.383s | step_started | login_user | type |  |  |  |
| 120 | +6.547s | observed |  |  |  |  |  |
| 121 | +6.547s | observation | login_user |  |  |  |  |
| 122 | +6.547s | target_resolved | login_user |  |  |  |  |
| 123 | +6.547s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 124 | +6.547s | action | login_user | type |  |  |  |
| 125 | +6.548s | action_attempted |  | type |  |  |  |
| 126 | +6.548s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 127 | +6.556s | action_result |  | type |  |  | ok |
| 128 | +6.556s | action_result | login_user |  |  |  | ok |
| 129 | +6.556s | step_finished | login_user |  |  |  | ok |
| 130 | +6.557s | step_started | login_password | type |  |  |  |
| 131 | +6.880s | observed |  |  |  |  |  |
| 132 | +6.881s | observation | login_password |  |  |  |  |
| 133 | +6.881s | target_resolved | login_password |  |  |  |  |
| 134 | +6.881s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 135 | +6.881s | action | login_password | type |  |  |  |
| 136 | +6.881s | action_attempted |  | type |  |  |  |
| 137 | +6.882s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 138 | +6.893s | action_result |  | type |  |  | ok |
| 139 | +6.893s | action_result | login_password |  |  |  | ok |
| 140 | +6.893s | step_finished | login_password |  |  |  | ok |
| 141 | +6.893s | step_started | login_submit | click |  |  |  |
| 142 | +7.212s | observed |  |  |  |  |  |
| 143 | +7.212s | observation | login_submit |  |  |  |  |
| 144 | +7.213s | target_resolved | login_submit |  |  |  |  |
| 145 | +7.213s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 146 | +7.213s | action | login_submit | click |  |  |  |
| 147 | +7.213s | action_attempted |  | click |  |  |  |
| 148 | +7.213s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 149 | +7.216s | action_result |  | click |  |  | ok |
| 150 | +7.216s | action_result | login_submit |  |  |  | ok |
| 151 | +7.930s | observed |  |  |  |  |  |
| 152 | +7.931s | checkpoint | login_submit |  |  |  | ok |
| 153 | +7.931s | step_finished | login_submit |  |  |  | ok |
| 154 | +7.931s | subflow_finished |  |  |  |  |  |
| 155 | +8.111s | observed |  |  |  |  |  |
| 156 | +8.112s | checkpoint | sign_on |  |  |  | ok |
| 157 | +8.112s | step_finished | sign_on |  |  |  | ok |
| 158 | +8.112s | step_started | type_member_number_textbox | type |  |  |  |
| 159 | +8.295s | observed |  |  |  |  |  |
| 160 | +8.295s | observation | type_member_number_textbox |  |  |  |  |
| 161 | +8.295s | target_resolved | type_member_number_textbox |  |  |  |  |
| 162 | +8.295s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 163 | +8.295s | action | type_member_number_textbox | type |  |  |  |
| 164 | +8.296s | action_attempted |  | type |  |  |  |
| 165 | +8.296s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 166 | +8.304s | action_result |  | type |  |  | ok |
| 167 | +8.304s | action_result | type_member_number_textbox |  |  |  | ok |
| 168 | +8.304s | step_finished | type_member_number_textbox |  |  |  | ok |
| 169 | +8.304s | step_started | click_search_button | click |  |  |  |
| 170 | +8.677s | observed |  |  |  |  |  |
| 171 | +8.677s | observation | click_search_button |  |  |  |  |
| 172 | +8.677s | target_resolved | click_search_button |  |  |  |  |
| 173 | +8.677s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 174 | +8.677s | action | click_search_button | click |  |  |  |
| 175 | +8.677s | action_attempted |  | click |  |  |  |
| 176 | +8.677s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 177 | +8.680s | action_result |  | click |  |  | ok |
| 178 | +8.680s | action_result | click_search_button |  |  |  | ok |
| 179 | +9.398s | observed |  |  |  |  |  |
| 180 | +9.399s | checkpoint | click_search_button |  |  |  | ok |
| 181 | +9.399s | step_finished | click_search_button |  |  |  | ok |
| 182 | +9.399s | step_started | read_savings_balance | extract |  |  |  |
| 183 | +9.580s | observed |  |  |  |  |  |
| 184 | +9.580s | observation | read_savings_balance |  |  |  |  |
| 185 | +9.580s | target_resolved | read_savings_balance |  |  |  |  |
| 186 | +9.581s | output_extracted | read_savings_balance |  |  |  |  |
| 187 | +9.581s | step_finished | read_savings_balance |  |  |  | ok |
| 188 | +9.763s | observed |  |  |  |  |  |
| 189 | +9.764s | checkpoint |  |  |  |  | ok |
| 191 | +9.765s | run_finished |  |  |  |  | success |

## Files

- `capability.json` (json, seq 2)
- `result.json` (json, seq 190)

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
- `output_extracted`: custom event kind
- `run_finished`: run ended
