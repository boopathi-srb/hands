# Build plan

The model discovers. The artifact becomes a reusable capability. Deterministic replay is how an agent invokes it.

## Ground rules for every contributor (human or agent)

- `src/hands/core/` is the contract. Do not edit it. If a contract change is truly needed, stop and report it.
- Only `src/hands/surfaces/browser/` may import `playwright`. Only `src/hands/surfaces/desktop_macos/` may import `pyobjc` modules (`ApplicationServices`, `Quartz`, `AppKit`).
- Do not edit `pyproject.toml` or `uv.lock`, and never run `uv sync` / `uv add` / `pip install`. Every dependency is already installed. Run things with `uv run ...`.
- Do not run `git` commands that change state. The lead commits after each phase.
- Code standards (from the owner's global rules):
  - Log every error with context (function name, inputs, what failed) via `hands.core.log.log_failure`. Never swallow.
  - Handle errors explicitly. Prefer returning typed results over raising; use try/except only at true I/O boundaries.
  - Small, named, composable functions. Readable variable names. DRY. SOLID.
  - Every public function has at least one unit test. Test edge cases explicitly: empty input, None, boundaries.
  - Integration tests cover the happy path and at least one failure path. Mock all external dependencies.
- Python 3.11, Pydantic v2, async where I/O is involved. Type hints everywhere.
- Never write real PII or secrets anywhere. Demo password comes from env `HANDS_DEMO_PASSWORD` (default `demo-only-password` documented in `.env.example`).

## Package map

| Package | Owner | Purpose |
|---|---|---|
| `hands.core` | lead (done) | Pydantic contracts and ports: observation, actions, targets, conditions, artifact, results, control, ports |
| `target_app` | agent A | Mock credit union core ("CoreOne") with legacy markup, faults, two tenants |
| `hands.locate` | agent B | Pure functions over Observation: resolve targets, evaluate conditions, generate candidates, templating |
| `hands.surfaces.fake`, `hands.surfaces.browser` | agent C | FakeSurface state machine; Playwright surface with a11y extraction across frames; CDP live view |
| `hands.surfaces.desktop_macos` | agent D | macOS AX API surface + screen-capture live view |
| `hands.policy`, `hands.redact`, `hands.evidence` | agent E | Allowlist + risk gate, redaction, evidence recorder |
| `hands.session`, `hands.console` | agent F | Control lease, guarded surface, escalator, operator console |
| `hands.replay`, `hands.catalog` | agent G (phase 3) | Deterministic replay engine, artifact store, tenant overlays |
| `hands.discovery` | agent H (phase 3) | Planner port, scripted/Ollama/Anthropic planners, cassettes, agent loop, recorder |
| `hands.cli`, docs, evidence | lead (phase 4) | Integration, end-to-end runs, README, REPORT |

## Phases

- [x] Phase 1: contracts in `hands.core`, repo skeleton, this plan
- [ ] Phase 2 (parallel): A target app, B locate, C surfaces, D desktop, E policy/evidence, F session/console
- [ ] Phase 3 (parallel): G replay + catalog, H discovery
- [ ] Phase 4: CLI, dev discovery on local Qwen3-VL, prod discovery on Claude Sonnet 5, replay evidence incl. failures and escalation, tenant variant, desktop observation evidence, README, REPORT

## Mock target: CoreOne Member Services

Fictional vendor "Northwind Core Systems", product "CoreOne", version "7.4". Server-rendered FastAPI + Jinja.
Deliberately hostile: framesets, table layout, `<font>` tags, no ids, no test ids, no `<label for>` on most fields
(labels are adjacent `<td>` cells), inline `onclick` handlers, one native JS `alert()`.

Tenants share the code and differ by config (stand-in for two institutions running the same vendor product):

| Thing | `lakeside` (base) | `prairie` (variant) |
|---|---|---|
| Brand | Lakeside Community CU | Prairie Federal CU |
| Member number label | Member Number | Account Number |
| Search button | Search | Find |
| Savings product name | Regular Savings | Share Savings |
| Share table column order | Share ID, Description, Balance, Available | Share ID, Balance, Description, Available |

Routes (all under `/t/{tenant}`):
1. `/login` table layout, fields "User ID" and "Password", submit "Sign On". User `teller1`, password from env.
2. `/main` frameset: `top` frame (brand, "Signed on as teller1", "Sign Off"), `nav` frame (links "Member Inquiry",
   "Open Share Account", "Reports"), `content` frame.
3. `/inquiry` in content frame: member number field and search button.
4. `/member/{member_number}` detail: name, status, "Shares" table.
   - `10001` Avery Quinn, Active: Regular Savings 1,250.00, Checking 310.45, Holiday Club 85.00.
   - `10002` Jordan Lee, Active: Regular Savings 9,870.12, Checking 0.00.
   - `40300` restricted: page shows "ACCESS DENIED: Member record is restricted (code 403-R)".
   - Any other number: "No member found for number {n}." in red.
   - Non-numeric input: validation error "Member number must be numeric." stays on inquiry page.
5. `/member/{n}/open-share` form: select "Share Type" (Regular Savings, Money Market, Share Certificate),
   "Initial Deposit", "Nickname"; button "Continue" goes to `/review` page "Confirm New Share" with
   buttons "Submit" (irreversible) and "Cancel". Submit shows "Share 0007 opened for member {n}."

Faults, armed via `POST /_admin/faults` `{"fault": name, "count": n, "tenant": t}` or env `COREONE_FAULTS`:
- `session_expired` next content request shows "Your session has expired. Please sign on again." with "Sign On" link.
- `slow` delays the next responses by `delay_ms` (default 4000).
- `maintenance_notice` in-page modal table "System Notice" with "Acknowledge" button over the content.
- `native_alert` a JS `alert("Printer queue offline")` on load.
- `identity_check` unknown modal "Verify Member Identity" with a security question; no automated answer exists.
- `app_error` "Internal Error. Reference ID ERR-5521." page.
`GET /_admin/faults` lists armed faults, `DELETE /_admin/faults` clears.

## Artifact schema decisions (see `src/hands/core/artifact.py`)

- Business outcomes may carry a message (`message_target`), returned to the caller.
- Recovery rules are declared globally and may be scoped to steps (`scope`, `Step.recoveries`).
- Outcome detectors and recovery rules for a vendor product live in an app profile (`profiles/coreone.yaml`),
  written once per vendor product, merged into artifacts by the recorder. A happy-path discovery run cannot
  observe "member not found", so the profile is where that knowledge comes from.
- Credentials are declared, never supplied by the caller, resolved from a CredentialProvider.
- Tenant overlays are separate files that can override targets, entry points, text aliases, outcome conditions,
  never the step list.
