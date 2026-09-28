# Run replay-ca4e14e44bbb

- Started: 2026-09-28T17:50:43.703438+00:00
- Last event: 2026-09-28T17:50:53.613324+00:00
- Events: 189 (control_transferred 1, run_started 1, step_started 17, subflow_started 3, observed 24, observation 15, policy_decision 28, action 14, action_attempted 14, action_result 28, checkpoint 8, step_finished 17, target_resolved 12, recovery_applied 1, subflow_finished 3, run_restarted 1, output_extracted 1, run_finished 1)
- Files: json 2

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | replay run started |  |  |
| 3 | +0.003s | run_started |  |  |  |  |  |
| 4 | +0.003s | step_started | sign_on | subflow |  |  |  |
| 5 | +0.004s | subflow_started |  |  |  |  |  |
| 6 | +0.004s | step_started | login_open | open |  |  |  |
| 7 | +0.674s | observed |  |  |  |  |  |
| 8 | +0.674s | observation | login_open |  |  |  |  |
| 9 | +0.675s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 10 | +0.675s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 11 | +0.675s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 12 | +0.675s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 13 | +0.684s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 14 | +0.684s | action_result | login_open |  |  |  | ok |
| 15 | +1.373s | observed |  |  |  |  |  |
| 16 | +1.373s | checkpoint | login_open |  |  |  | ok |
| 17 | +1.373s | step_finished | login_open |  |  |  | ok |
| 18 | +1.374s | step_started | login_user | type |  |  |  |
| 19 | +1.540s | observed |  |  |  |  |  |
| 20 | +1.541s | observation | login_user |  |  |  |  |
| 21 | +1.541s | target_resolved | login_user |  |  |  |  |
| 22 | +1.541s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 23 | +1.541s | action | login_user | type |  |  |  |
| 24 | +1.541s | action_attempted |  | type |  |  |  |
| 25 | +1.541s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 26 | +1.643s | action_result |  | type |  |  | ok |
| 27 | +1.643s | action_result | login_user |  |  |  | ok |
| 28 | +1.643s | step_finished | login_user |  |  |  | ok |
| 29 | +1.644s | step_started | login_password | type |  |  |  |
| 30 | +1.975s | observed |  |  |  |  |  |
| 31 | +1.975s | observation | login_password |  |  |  |  |
| 32 | +1.975s | target_resolved | login_password |  |  |  |  |
| 33 | +1.975s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 34 | +1.975s | action | login_password | type |  |  |  |
| 35 | +1.976s | action_attempted |  | type |  |  |  |
| 36 | +1.976s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 37 | +1.997s | action_result |  | type |  |  | ok |
| 38 | +1.998s | action_result | login_password |  |  |  | ok |
| 39 | +1.998s | step_finished | login_password |  |  |  | ok |
| 40 | +1.998s | step_started | login_submit | click |  |  |  |
| 41 | +2.323s | observed |  |  |  |  |  |
| 42 | +2.323s | observation | login_submit |  |  |  |  |
| 43 | +2.323s | target_resolved | login_submit |  |  |  |  |
| 44 | +2.324s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 45 | +2.324s | action | login_submit | click |  |  |  |
| 46 | +2.324s | action_attempted |  | click |  |  |  |
| 47 | +2.324s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 48 | +2.328s | action_result |  | click |  |  | ok |
| 49 | +2.328s | action_result | login_submit |  |  |  | ok |
| 50 | +3.057s | observed |  |  |  |  |  |
| 51 | +3.058s | recovery_applied | login_submit |  |  |  |  |
| 52 | +3.058s | subflow_started |  |  |  |  |  |
| 53 | +3.058s | step_started | login_open | open |  |  |  |
| 54 | +3.240s | observed |  |  |  |  |  |
| 55 | +3.241s | observation | login_open |  |  |  |  |
| 56 | +3.241s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 57 | +3.241s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 58 | +3.241s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 59 | +3.241s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 60 | +3.248s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 61 | +3.248s | action_result | login_open |  |  |  | ok |
| 62 | +3.941s | observed |  |  |  |  |  |
| 63 | +3.941s | checkpoint | login_open |  |  |  | ok |
| 64 | +3.942s | step_finished | login_open |  |  |  | ok |
| 65 | +3.942s | step_started | login_user | type |  |  |  |
| 66 | +4.106s | observed |  |  |  |  |  |
| 67 | +4.107s | observation | login_user |  |  |  |  |
| 68 | +4.107s | target_resolved | login_user |  |  |  |  |
| 69 | +4.107s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 70 | +4.107s | action | login_user | type |  |  |  |
| 71 | +4.107s | action_attempted |  | type |  |  |  |
| 72 | +4.108s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 73 | +4.116s | action_result |  | type |  |  | ok |
| 74 | +4.116s | action_result | login_user |  |  |  | ok |
| 75 | +4.116s | step_finished | login_user |  |  |  | ok |
| 76 | +4.117s | step_started | login_password | type |  |  |  |
| 77 | +4.457s | observed |  |  |  |  |  |
| 78 | +4.457s | observation | login_password |  |  |  |  |
| 79 | +4.458s | target_resolved | login_password |  |  |  |  |
| 80 | +4.458s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 81 | +4.458s | action | login_password | type |  |  |  |
| 82 | +4.458s | action_attempted |  | type |  |  |  |
| 83 | +4.458s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 84 | +4.469s | action_result |  | type |  |  | ok |
| 85 | +4.469s | action_result | login_password |  |  |  | ok |
| 86 | +4.469s | step_finished | login_password |  |  |  | ok |
| 87 | +4.469s | step_started | login_submit | click |  |  |  |
| 88 | +4.809s | observed |  |  |  |  |  |
| 89 | +4.810s | observation | login_submit |  |  |  |  |
| 90 | +4.810s | target_resolved | login_submit |  |  |  |  |
| 91 | +4.810s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 92 | +4.810s | action | login_submit | click |  |  |  |
| 93 | +4.810s | action_attempted |  | click |  |  |  |
| 94 | +4.810s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 95 | +4.814s | action_result |  | click |  |  | ok |
| 96 | +4.814s | action_result | login_submit |  |  |  | ok |
| 97 | +5.574s | observed |  |  |  |  |  |
| 98 | +5.575s | checkpoint | login_submit |  |  |  | ok |
| 99 | +5.575s | step_finished | login_submit |  |  |  | ok |
| 100 | +5.575s | subflow_finished |  |  |  |  |  |
| 101 | +5.575s | step_finished | login_submit |  |  |  | recovered |
| 102 | +5.575s | subflow_finished |  |  |  |  |  |
| 103 | +5.575s | step_finished | sign_on |  |  |  | ok |
| 104 | +5.575s | run_restarted |  |  | recovery 'session_expired' ran subflow 'login' then restart |  |  |
| 105 | +5.575s | step_started | sign_on | subflow |  |  |  |
| 106 | +5.575s | subflow_started |  |  |  |  |  |
| 107 | +5.576s | step_started | login_open | open |  |  |  |
| 108 | +5.740s | observed |  |  |  |  |  |
| 109 | +5.740s | observation | login_open |  |  |  |  |
| 110 | +5.740s | policy_decision | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 111 | +5.740s | action | login_open | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 112 | +5.740s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 113 | +5.741s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 114 | +5.747s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 115 | +5.748s | action_result | login_open |  |  |  | ok |
| 116 | +6.441s | observed |  |  |  |  |  |
| 117 | +6.443s | checkpoint | login_open |  |  |  | ok |
| 118 | +6.443s | step_finished | login_open |  |  |  | ok |
| 119 | +6.443s | step_started | login_user | type |  |  |  |
| 120 | +6.605s | observed |  |  |  |  |  |
| 121 | +6.605s | observation | login_user |  |  |  |  |
| 122 | +6.605s | target_resolved | login_user |  |  |  |  |
| 123 | +6.605s | policy_decision | login_user | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 124 | +6.605s | action | login_user | type |  |  |  |
| 125 | +6.606s | action_attempted |  | type |  |  |  |
| 126 | +6.606s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 127 | +6.614s | action_result |  | type |  |  | ok |
| 128 | +6.615s | action_result | login_user |  |  |  | ok |
| 129 | +6.615s | step_finished | login_user |  |  |  | ok |
| 130 | +6.615s | step_started | login_password | type |  |  |  |
| 131 | +6.919s | observed |  |  |  |  |  |
| 132 | +6.919s | observation | login_password |  |  |  |  |
| 133 | +6.919s | target_resolved | login_password |  |  |  |  |
| 134 | +6.919s | policy_decision | login_password | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 135 | +6.919s | action | login_password | type |  |  |  |
| 136 | +6.919s | action_attempted |  | type |  |  |  |
| 137 | +6.919s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 138 | +6.943s | action_result |  | type |  |  | ok |
| 139 | +6.944s | action_result | login_password |  |  |  | ok |
| 140 | +6.944s | step_finished | login_password |  |  |  | ok |
| 141 | +6.944s | step_started | login_submit | click |  |  |  |
| 142 | +7.274s | observed |  |  |  |  |  |
| 143 | +7.275s | observation | login_submit |  |  |  |  |
| 144 | +7.275s | target_resolved | login_submit |  |  |  |  |
| 145 | +7.275s | policy_decision | login_submit | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 146 | +7.275s | action | login_submit | click |  |  |  |
| 147 | +7.275s | action_attempted |  | click |  |  |  |
| 148 | +7.275s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule ma… | allow (risk.default) |  |
| 149 | +7.278s | action_result |  | click |  |  | ok |
| 150 | +7.278s | action_result | login_submit |  |  |  | ok |
| 151 | +8.008s | observed |  |  |  |  |  |
| 152 | +8.009s | checkpoint | login_submit |  |  |  | ok |
| 153 | +8.009s | step_finished | login_submit |  |  |  | ok |
| 154 | +8.009s | subflow_finished |  |  |  |  |  |
| 155 | +8.188s | observed |  |  |  |  |  |
| 156 | +8.189s | checkpoint | sign_on |  |  |  | ok |
| 157 | +8.189s | step_finished | sign_on |  |  |  | ok |
| 158 | +8.189s | step_started | type_member_number_textbox | type |  |  |  |
| 159 | +8.390s | observed |  |  |  |  |  |
| 160 | +8.390s | observation | type_member_number_textbox |  |  |  |  |
| 161 | +8.390s | target_resolved | type_member_number_textbox |  |  |  |  |
| 162 | +8.391s | policy_decision | type_member_number_textbox | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 163 | +8.391s | action | type_member_number_textbox | type |  |  |  |
| 164 | +8.391s | action_attempted |  | type |  |  |  |
| 165 | +8.391s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in replay mode; no risk rule matc… | allow (risk.default) |  |
| 166 | +8.405s | action_result |  | type |  |  | ok |
| 167 | +8.405s | action_result | type_member_number_textbox |  |  |  | ok |
| 168 | +8.405s | step_finished | type_member_number_textbox |  |  |  | ok |
| 169 | +8.405s | step_started | click_search_button | click |  |  |  |
| 170 | +8.788s | observed |  |  |  |  |  |
| 171 | +8.788s | observation | click_search_button |  |  |  |  |
| 172 | +8.788s | target_resolved | click_search_button |  |  |  |  |
| 173 | +8.788s | policy_decision | click_search_button | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 174 | +8.789s | action | click_search_button | click |  |  |  |
| 175 | +8.789s | action_attempted |  | click |  |  |  |
| 176 | +8.789s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in replay mode; no risk rule mat… | allow (risk.default) |  |
| 177 | +8.791s | action_result |  | click |  |  | ok |
| 178 | +8.791s | action_result | click_search_button |  |  |  | ok |
| 179 | +9.525s | observed |  |  |  |  |  |
| 180 | +9.526s | checkpoint | click_search_button |  |  |  | ok |
| 181 | +9.526s | step_finished | click_search_button |  |  |  | ok |
| 182 | +9.526s | step_started | read_savings_balance | extract |  |  |  |
| 183 | +9.724s | observed |  |  |  |  |  |
| 184 | +9.725s | observation | read_savings_balance |  |  |  |  |
| 185 | +9.725s | target_resolved | read_savings_balance |  |  |  |  |
| 186 | +9.725s | output_extracted | read_savings_balance |  |  |  |  |
| 187 | +9.725s | step_finished | read_savings_balance |  |  |  | ok |
| 188 | +9.907s | observed |  |  |  |  |  |
| 189 | +9.907s | checkpoint |  |  |  |  | ok |
| 191 | +9.910s | run_finished |  |  |  |  | success |

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
