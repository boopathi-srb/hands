# Run disc-dd983ef8fe94

- Started: 2026-11-05T02:13:36.077289+00:00
- Last event: 2026-11-05T02:14:00.382319+00:00
- Events: 62 (control_transferred 1, run_started 1, observed 8, observation 8, policy_decision 12, action 6, action_attempted 6, action_result 12, decision 7, run_finished 1)
- Files: snapshot 8, screenshot 8, json 3

## Timeline

| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |
|---:|---:|---|---|---|---|---|---|
| 1 | +0.000s | control_transferred |  |  | discovery run started |  |  |
| 2 | +0.334s | run_started |  |  |  |  |  |
| 3 | +0.661s | observed |  |  |  |  |  |
| 6 | +0.663s | observation |  |  |  |  |  |
| 7 | +0.663s | policy_decision | 0 | open | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 8 | +0.663s | action | 0 | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 9 | +0.664s | action_attempted |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  |  |
| 10 | +0.664s | policy_decision |  | open 'http://127.0.0.1:8700/t/lakeside/login' | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'open' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 11 | +0.672s | action_result |  | open 'http://127.0.0.1:8700/t/lakeside/login' |  |  | ok |
| 12 | +0.673s | action_result | 0 |  |  |  | ok |
| 13 | +1.349s | observed |  |  |  |  |  |
| 16 | +1.379s | observation |  |  |  |  |  |
| 17 | +5.146s | decision | 1 | type | Enter username to sign in. |  |  |
| 18 | +5.146s | policy_decision | 1 | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 19 | +5.146s | action | 1 | type |  |  |  |
| 20 | +5.147s | action_attempted |  | type |  |  |  |
| 21 | +5.147s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 22 | +5.180s | action_result |  | type |  |  | ok |
| 23 | +5.180s | action_result | 1 |  |  |  | ok |
| 24 | +5.497s | observed |  |  |  |  |  |
| 27 | +5.515s | observation |  |  |  |  |  |
| 28 | +9.028s | decision | 2 | type | Enter password next. |  |  |
| 29 | +9.028s | policy_decision | 2 | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 30 | +9.028s | action | 2 | type |  |  |  |
| 31 | +9.028s | action_attempted |  | type |  |  |  |
| 32 | +9.028s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'type' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 33 | +9.048s | action_result |  | type |  |  | ok |
| 34 | +9.049s | action_result | 2 |  |  |  | ok |
| 35 | +9.362s | observed |  |  |  |  |  |
| 38 | +9.378s | observation |  |  |  |  |  |
| 39 | +12.330s | decision | 3 | click | Credentials entered; submit sign on. |  |  |
| 40 | +12.331s | policy_decision | 3 | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in discovery mode; no risk rule… | allow (risk.default) |  |
| 41 | +12.331s | action | 3 | click |  |  |  |
| 42 | +12.331s | action_attempted |  | click |  |  |  |
| 43 | +12.332s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/login allowed by '/t/lakeside/**'; 'click' is allowed in discovery mode; no risk rule… | allow (risk.default) |  |
| 44 | +12.336s | action_result |  | click |  |  | ok |
| 45 | +12.336s | action_result | 3 |  |  |  | ok |
| 46 | +13.048s | observed |  |  |  |  |  |
| 49 | +13.059s | observation |  |  |  |  |  |
| 50 | +15.311s | decision | 4 | type | Enter member number in search field. |  |  |
| 51 | +15.311s | policy_decision | 4 | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in discovery mode; no risk rule m… | allow (risk.default) |  |
| 52 | +15.312s | action | 4 | type |  |  |  |
| 53 | +15.312s | action_attempted |  | type |  |  |  |
| 54 | +15.312s | policy_decision |  | type | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'type' is allowed in discovery mode; no risk rule m… | allow (risk.default) |  |
| 55 | +15.329s | action_result |  | type |  |  | ok |
| 56 | +15.330s | action_result | 4 |  |  |  | ok |
| 57 | +15.695s | observed |  |  |  |  |  |
| 60 | +15.703s | observation |  |  |  |  |  |
| 61 | +18.382s | decision | 5 | click | Submit member search. |  |  |
| 62 | +18.382s | policy_decision | 5 | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 63 | +18.383s | action | 5 | click |  |  |  |
| 64 | +18.383s | action_attempted |  | click |  |  |  |
| 65 | +18.383s | policy_decision |  | click | safe action allowed: http://127.0.0.1:8700/t/lakeside/main allowed by '/t/lakeside/**'; 'click' is allowed in discovery mode; no risk rule … | allow (risk.default) |  |
| 66 | +18.388s | action_result |  | click |  |  | ok |
| 67 | +18.389s | action_result | 5 |  |  |  | ok |
| 68 | +19.064s | observed |  |  |  |  |  |
| 71 | +19.075s | observation |  |  |  |  |  |
| 72 | +21.837s | decision | 6 | extract | Regular Savings share balance is shown; extract it. |  |  |
| 73 | +22.032s | observed |  |  |  |  |  |
| 76 | +22.044s | observation |  |  |  |  |  |
| 77 | +24.305s | decision | 7 | done | Savings balance already extracted. |  |  |
| 78 | +24.305s | run_finished |  |  | Savings balance already extracted. |  | completed |

## Files

- `snapshots/004-obs-001.json` (snapshot, seq 4)
- `screenshots/005-obs-001.png` (screenshot, seq 5)
- `snapshots/014-obs-002.json` (snapshot, seq 14)
- `screenshots/015-obs-002.png` (screenshot, seq 15)
- `snapshots/025-obs-003.json` (snapshot, seq 25)
- `screenshots/026-obs-003.png` (screenshot, seq 26)
- `snapshots/036-obs-004.json` (snapshot, seq 36)
- `screenshots/037-obs-004.png` (screenshot, seq 37)
- `snapshots/047-obs-005.json` (snapshot, seq 47)
- `screenshots/048-obs-005.png` (screenshot, seq 48)
- `snapshots/058-obs-006.json` (snapshot, seq 58)
- `screenshots/059-obs-006.png` (screenshot, seq 59)
- `snapshots/069-obs-007.json` (snapshot, seq 69)
- `screenshots/070-obs-007.png` (screenshot, seq 70)
- `snapshots/074-obs-008.json` (snapshot, seq 74)
- `screenshots/075-obs-008.png` (screenshot, seq 75)
- `discovery_trace.json` (json, seq 79)
- `capability.json` (json, seq 80)
- `discovery_result.json` (json, seq 81)

## Event kinds

- `control_transferred`: control lease transferred
- `run_started`: run began
- `observed`: custom event kind
- `observation`: surface observed
- `policy_decision`: policy gate verdict
- `action`: action sent to surface
- `action_attempted`: custom event kind
- `action_result`: surface reported result
- `decision`: next action chosen
- `run_finished`: run ended
