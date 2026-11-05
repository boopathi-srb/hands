# Evidence

Everything here came from real runs against the CoreOne mock app (`uv run python -m target_app --port 8700`)
in headless Chromium, on 2026-09-28. Each run directory under `runs/` holds:

- `events.jsonl`: every event in order, redacted
- `summary.md`: a readable timeline
- `screenshots/`: masked
- `snapshots/`: accessibility observations, redacted, no pixels
- `result.json` (replay) or `discovery_result.json` and `discovery_trace.json` (discovery)
- `capability.json`: the artifact used or produced by that run

## 1. Discovery: a real LLM-driven run

`runs/disc-1458ec924f36/` shows **local Qwen3-VL 8B via Ollama** completing the goal on the live app. It took
7 model decisions, 0 invalid, about 2 minutes on an M4 laptop.

> Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance.

- The model signed on by typing `{{teller.username}}` and `{{teller.password}}`. It never saw the values.
- It found the member-number field inside the `content` frame and searched.
- It extracted `1,250.00` from the Regular Savings row.
- Its rationale for each step is in `summary.md` and `events.jsonl`.
- The model responses are recorded in `../cassettes/dev-qwen-web.jsonl`, so the run can be re-executed offline
  with `--cassette-mode replay`.
- An earlier development run on the in-memory fake is in `../cassettes/dev-ollama-fake.jsonl`.

`runs/disc-dd983ef8fe94/` is the **production run on Claude Sonnet 5.5** (`claude-sonnet-5-5`) against the same
live app. It took 7 decisions, 0 invalid, 27 seconds, and about 10,500 input and 1,500 output tokens, with prompt
caching active from the first call. Its responses are in `../cassettes/prod-sonnet-5-5-web.jsonl`.

The two models recorded **the same capability**. Apart from provenance, the artifact from Sonnet 5.5
(`artifact/coreone.member_balance-1.0.0-from-sonnet-5-5.json`) is identical to the one from Qwen, field for field:
steps, targets, conditions, checkpoint, outcomes, and recoveries. The prairie overlay written for one applies to the
other. The Sonnet artifact also replays correctly: success, member not found, session-expiry recovery, and prairie.

## 2. The artifact

`artifact/coreone.member_balance-1.0.0.json` is the capability that run produced. The recorder:

- collapsed the sign-on into the vendor profile's `login` subflow;
- parameterized `10001` as the `member_number` input with a digits pattern;
- ranked target candidates with reasons;
- derived postconditions and the checkpoint from what changed on screen;
- merged the CoreOne profile's outcomes and recoveries.

Also in `artifact/`:

- `overlay-prairie.json` is the tenant overlay for the second institution.
- `tool_definitions.json` is what a calling agent sees.

## 3. Replay: no model, every result class

Summarized in `replays.jsonl`. Regenerate with `../scripts/replay_evidence.sh`.

| Case | Result | Output or code | Recoveries on the trace | Run |
|---|---|---|---|---|
| Another member | success | savings_balance 9870.12 | | `replay-0b683ecc08a5` |
| Unknown member | business_outcome | MEMBER_NOT_FOUND | | `replay-6c8720c5f346` |
| Restricted member | business_outcome | MEMBER_RESTRICTED | | `replay-ed61e8789a0b` |
| Member number `abc` | failed | invalid_input, before touching the app | | `replay-b8778fce0c2d` |
| Session expired | success | 1250.00 | session_expired: re-sign-on, restart | `replay-ca4e14e44bbb` |
| Maintenance notice | success | 1250.00 | maintenance_notice: acknowledged | `replay-27f4c86ba1c9` |
| Native JS alert | success | 1250.00 | native_alert: accepted | `replay-b88ec552cd42` |
| Slow load, 4 s | success | 1250.00 | none needed; waits are condition-based | `replay-4ece1ded80fc` |
| App error once | success | 1250.00 | transient_app_error: re-sign-on, restart | `replay-6fba65bdc25b` |
| App error twice | failed | recovery_exhausted, with snapshot and screenshot | transient_app_error | `replay-336aef34b540` |
| Identity check, no operator | failed | unexpected_state: a human is required | identity_verification | `replay-8d4d1fc2fde9` |
| Tenant `prairie` | success | 9870.12 via the overlay | | `replay-579e2748d78c` |
| Identity check, operator aborts | escalated | operator note returned | | `replay-d6c721fe95a6` |
| Identity check, operator resumes | success | 1250.00; sign-on step marked `human` | identity_verification | `replay-b8fd4634c051` |

## 4. Human handoff on the live session

`runs/replay-b8fd4634c051/` records the full handoff:

1. The replay hit the identity challenge, raised an intervention, and released the lease to nobody.
2. An operator took control through the console. The lease moved to human `ops-demo`.
3. Over the live-view websocket, the operator clicked the Security Answer field, typed the override, and clicked
   Verify. The input was injected into the same Chromium session, and the app logged "identity check overridden by
   supervisor".
4. The operator handed back with `resume`. The lease returned to automation, the engine re-checked the step, marked
   it `human`, and finished with the balance.

The human actions in the evidence read "click textbox Security Answer, type (19 chars), click button Verify". The
typed text itself is never stored. The operator here was `scripts/operator_handoff.py`, which speaks the console's
real HTTP and websocket protocol, the same one `console/static/operator.html` uses in a browser. I also drove the
console page by hand in a browser during development.

## Not included, and why

- **macOS desktop observation.** The terminal was not granted Accessibility permission, and granting it is a manual
  security setting. The desktop surface is unit-tested against a fake AX backend.
- **Playwright traces.** A secret scan of the evidence found that trace archives record typed input verbatim,
  outside the redactor. Traces are now opt-in (`--trace`) and for local debugging only, and none are committed.
