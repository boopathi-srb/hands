# hands

A computer-use automation system for legacy back-office software. A model works out how to do a task once.
The run becomes a typed, versioned **capability**. Production invokes the capability by **deterministic replay**,
with no model in the loop, and gets back a typed result: success with outputs, a business outcome such as
"member not found", an escalation, or a hard failure with step, expected, observed, and evidence.

- Design write-up: [REPORT.md](REPORT.md)
- Evidence of real runs: [evidence/](evidence/README.md)
- Build plan and phase history: [PLAN.md](PLAN.md)

## Setup

Requirements: macOS or Linux, Python 3.11, [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run playwright install chromium
cp .env.example .env   # optional; defaults work for the local demo
```

Optional, only for the planners you use:

| Planner | Needs |
|---|---|
| `scripted` | nothing; offline and deterministic |
| `ollama` (development) | [Ollama](https://ollama.com) running, then `ollama pull qwen3-vl:8b` |
| `anthropic` (production run) | `ANTHROPIC_API_KEY` in the environment |

The macOS desktop surface also needs `uv sync --extra dev --extra desktop` and Accessibility permission for your
terminal (System Settings, Privacy & Security, Accessibility).

## Run the target app

The proxy target is **CoreOne**, a mock credit-union core with framesets, table layouts, no ids or test ids,
injectable faults, and two tenants. Start it in its own terminal:

```bash
uv run python -m target_app --port 8700
```

Open http://127.0.0.1:8700/t/lakeside/login and sign on as `teller1` / `demo-only-password` to look around.
Members: `10001` and `10002` exist, `40300` is restricted, anything else is not found.

## Demo path

1. Discover a capability with a model (pick one planner):

```bash
uv run hands discover "Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance." -i member_number=10001 --planner ollama
```

Use `--planner anthropic` for Claude Sonnet 5, or `--planner scripted` to run offline. Add `--headed` to watch.
The artifact is saved to `artifacts/coreone.member_balance/1.0.0.json` and evidence to `runs/<run_id>/`.

2. Replay it with different inputs, no model involved:

```bash
uv run hands replay coreone.member_balance -i member_number=10002
```

3. See how runtime conditions come back as typed results:

```bash
uv run hands replay coreone.member_balance -i member_number=99999
```

```bash
uv run hands replay coreone.member_balance -i member_number=40300
```

```bash
uv run hands replay coreone.member_balance -i member_number=abc
```

```bash
uv run hands replay coreone.member_balance -i member_number=10001 --fault session_expired:1 --fault maintenance_notice:1
```

The first three return `MEMBER_NOT_FOUND`, `MEMBER_RESTRICTED`, and `invalid_input` before touching the app.
The last one re-signs-on and acknowledges the notice, then succeeds, with both recoveries on the step trace.
`--fault` is a test-harness flag that arms the mock app out of band; the agent itself is blocked from `/_admin`.

4. Human handoff on the same live session:

```bash
uv run hands replay coreone.member_balance -i member_number=10001 --fault identity_check:1 --headed
```

The run pauses and logs an operator URL (http://127.0.0.1:8765). Open it, take control, answer the security
question with `supervisor-override`, and hand back with "resume". The run continues on the same browser session
and the human's actions are recorded in the evidence (typed text as length only).

5. Tenant variant: the same capability on a second institution running the same product:

```bash
uv run hands replay coreone.member_balance -i member_number=10001 --tenant prairie
```

The prairie overlay in `artifacts/coreone.member_balance/overlays/prairie.json` renames labels and re-targets the
reordered shares table; the step list is unchanged.

6. The agent-facing catalog:

```bash
uv run hands catalog list
```

```bash
uv run hands catalog tools
```

## Running without live services

- `--planner scripted` needs no model. `--cassette cassettes/<file>.jsonl --cassette-mode replay` re-serves a
  recorded model run with no network, so a discovery run can be re-executed offline exactly.
- `--surface fake` runs discovery and replay on an in-memory CoreOne with no browser and no server.

```bash
uv run hands discover "Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance." -i member_number=10001 --planner scripted --surface fake --escalation none
```

```bash
uv run hands replay coreone.member_balance -i member_number=99999 --surface fake --escalation none
```

## Tests

```bash
uv run pytest -q -m "not browser and not desktop"
```

```bash
uv run pytest -q -m browser
```

Every external dependency (model APIs, Ollama, browser, OS accessibility) is faked in unit tests. Browser tests
launch headless Chromium against local fixture pages. The desktop test runs only when Accessibility is granted.

## Layout

| Path | What |
|---|---|
| `src/hands/core` | Contracts: observation, actions, targets, conditions, artifact, results, control, ports |
| `src/hands/locate` | Pure target resolution, condition evaluation, candidate generation |
| `src/hands/surfaces` | `browser` (Playwright + CDP), `desktop_macos` (AX API), `fake` |
| `src/hands/discovery` | Planner port, Ollama/Anthropic/scripted/cassette planners, agent loop, recorder |
| `src/hands/replay` | Deterministic replay engine |
| `src/hands/catalog` | Artifact store, tenant overlays, tool schemas, profile merge |
| `src/hands/policy`, `redact`, `evidence` | Guardrails, redaction, run evidence |
| `src/hands/session`, `console` | Control lease, guarded surface, escalation, operator console |
| `src/hands/profiles`, `profiles/` | Vendor app profiles: known outcomes and recoveries per product |
| `src/target_app` | The CoreOne mock target |
