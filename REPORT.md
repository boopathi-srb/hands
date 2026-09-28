# REPORT

`hands` gives AI agents hands inside legacy bank software. A model discovers a flow once. The flow becomes a
typed, versioned capability. Production invokes the capability by deterministic replay, with no model in the loop.

## 1. Architecture

One Python process, one CLI, three verbs: `discover`, `replay`, `catalog`. No queues or services. The brief rewards
sound abstractions over infrastructure, and every seam below is where a service boundary would go later.

```
 goal ─► DiscoveryAgent ──(Planner port: Ollama | Anthropic | Scripted | Cassette)
              │  observe → decide → validate → policy → act
              ▼
          recorder ──► Capability artifact (+ vendor AppProfile, + tenant overlays) ──► ArtifactStore
                                                                                          │
 agent invocation (id + typed inputs) ─► ReplayEngine ◄─────────────────────────────────┘
              │  wait(pre + target) → monitors → policy → act → wait(post) → extract → checkpoint
              ▼
     GuardedSurface (control lease + policy + evidence)
              ▼
     Surface port ── BrowserSurface (Playwright + CDP a11y) │ MacDesktopSurface (AX API) │ FakeSurface
              ▼
     LiveViewTransport ── CDP screencast │ screen capture + CGEvent  ◄── operator console (FastAPI, same process)
```

Key decisions:
- **Perceive through the accessibility tree, not the DOM.** Every surface returns the same `Observation`: nodes with
  role, name, text, value, label, container path, role-indexed structural path, and bounds. Browsers and desktop OSes
  both expose this tree, so the recorded flow never mentions CSS, XPath, or a toolkit. Screenshots ride along for the
  model and for evidence. Coordinates are the last-resort locator, not the first.
- **Locator logic is pure and lives in the core.** `hands.locate` resolves targets and evaluates conditions as pure
  functions over an `Observation`. Surfaces only observe and act, so resolution behaves identically on every surface
  and is unit-tested without a browser.
- **Guardrails at the seam, not in the prompt.** Every action from the model, the replay engine, or a human passes
  the policy gate and the control lease before it reaches the surface.
- **Built for a weak model.** Development ran against a local 8B vision model (Qwen3-VL via Ollama). The loop owns
  validation, re-prompting, stuck detection, and secret substitution, so a stronger model only makes it faster.
  The production evidence run uses Claude Sonnet 5.
- **Trade-off:** single process means the operator console must share the event loop with the run, because it needs
  the live surface object. Remote operation would put the surface behind a session broker; the transport interface
  is already the right shape for that.

## 2. Artifact schema

Source of truth: `src/hands/core/artifact.py` (Pydantic, exports JSON Schema). Example: `evidence/`.

A `Capability` is a contract first and a step list second:
- **Identity:** `id`, semver `version`, `status` (draft, approved, deprecated), `schema_version`.
- **Contract for the calling agent:** `title`, `description`, typed `inputs` (type, pattern, required, sensitive),
  typed `outputs`. `hands catalog --tools` turns this into a tool definition an agent can call.
- **Credentials** are declared by name and fields, resolved at replay from a credential provider, never passed by the
  caller, and referenced only as `{{teller.password}}`.
- **Steps:** open, click, type, press, select, extract, wait, subflow. Each has an optional precondition and
  postcondition, a timeout, a risk class, and step-scoped recoveries.
- **Targets** are ranked candidate lists: role + accessible name, label, text anchor + spatial relation, container +
  structural path, and a visual anchor offset. Each candidate carries a confidence and a one-line reason a reviewer
  can judge. The recorder only keeps a candidate if it resolves uniquely back to the node the model acted on.
- **Conditions** are one small declarative language (text visible, node present, location matches, dialog open,
  value matches, all/any/not). The checkpoint, pre/postconditions, outcome detectors, and recovery triggers all use it.
- **Runtime knowledge is data:** `outcomes` (business results such as `MEMBER_NOT_FOUND`, with an optional message
  target) and `recoveries` (dismiss, retry, subflow, escalate, each bounded) are declared, so the engine has no
  app-specific code. They come from a per-vendor `AppProfile`, because a happy-path discovery run cannot observe
  "member not found".
- **Provenance and stats:** discovery run id, planner, model, goal; replay counts and fallback-match counts.
- **Validators** reject duplicate step ids, undeclared placeholders, outputs never extracted, unknown recoveries,
  subflows, and outcome scopes.

Why this shape: the calling agent needs a function signature and an error vocabulary; the reviewer needs to see what
will be clicked and why it will still be found next month; the engine needs to know which screens are legitimate
answers and which are interruptions. Transcript details stay in evidence, never in the artifact.

## 3. Determinism & error handling

**Determinism.** Replay never asks a model anything. For every step the engine waits until the precondition
holds and the target resolves, runs the monitors, checks policy, acts, then waits for the postcondition. Waits are
condition polls with per-step timeouts, never sleeps. Target resolution tries candidates in rank order and records
which rank matched. The final checkpoint must hold before the run can succeed. Outputs are coerced to their declared
types, and decimals stay strings (`"1250.00"`) so no float ever touches a balance.

**Error taxonomy.** On every observation, in every wait, the monitors run in a fixed order:

1. **Business outcomes** declared by the capability, such as `MEMBER_NOT_FOUND`, `MEMBER_RESTRICTED`, or
   `INVALID_MEMBER_NUMBER`. They return `business_outcome` with the code and the app's own message. This is an answer
   for the caller, not an error.
2. **Recoveries**, each bounded by `max_applications`: dismiss a known notice or native alert, retry after a
   backoff, run a subflow such as re-sign-on and then retry the step or restart, or escalate to a human. They are
   absorbed into the step trace (`recovered`) and never surface as a status.
3. Anything else that stops progress becomes a **hard failure** with a code (`invalid_input`, `policy_denied`,
   `precondition_timeout`, `target_not_found`, `action_failed`, `postcondition_timeout`, `extraction_failed`,
   `checkpoint_failed`, `recovery_exhausted`, `unexpected_state`, `surface_error`, `run_timeout`). It carries the step,
   what was expected (the condition's own explanation), what was observed (location, dialogs, visible text), and paths
   to a screenshot and an accessibility snapshot. With an operator configured, an unexplained timeout is escalated once
   before it fails.

Inputs are validated against the contract before the surface is touched, so a malformed member number never
reaches the app.

**Drift, secondarily.** A step resolved by a fallback candidate still succeeds, but lands in `drift.fallback_steps`
and the artifact's replay stats. That is the early signal that a tenant or version is diverging.

## 4. Heterogeneity & multi-tenant

**Surface abstraction.** The seam is the `Surface` port: `observe()` returns an accessibility-tree `Observation`,
and `act()` takes a node reference or a point plus a surface-neutral action. Everything above it (locators,
conditions, artifacts, replay, policy, escalation) is surface-agnostic, and a test fails the build if anything
outside the browser package imports Playwright.

- **Modern web and legacy web** share `BrowserSurface`. It reads the accessibility tree per frame over CDP, so
  framesets, nested tables and missing ids are just more nodes with container paths like `frame:content`.
- **Desktop** is `MacDesktopSurface` over the macOS Accessibility API. It produces the same `Observation`, with
  windows and sheets as container paths. Windows UI Automation would be one more adapter of the same shape.
- **Live view** follows the same pattern. The operator console talks to a `LiveViewTransport`; the browser uses a CDP
  screencast and input injection, the desktop uses window capture and synthetic input.

**Multi-tenant reuse.** Three layers, from shared to specific:

1. The **capability** is keyed by vendor product and version, not by tenant, and describes the flow once.
2. The **vendor app profile** holds product runtime knowledge: its business outcomes, recoveries, and sign-on
   subflow. Fixing it once fixes every tenant.
3. A **tenant overlay** may override entry points, targets for named steps, text aliases (Member Number becomes
   Account Number), and outcome conditions. It may never add or remove steps, so the reviewed flow stays in one place.

The overlay declares the base version range it was validated against, and applying it to an incompatible version
is an error. **Drift** is detected two ways: fallback-candidate matches per step, recorded on every run, and
structural fingerprints on every step trace. A tenant that starts matching through fallbacks is a candidate for an
overlay or a re-discovery on that tenant. The demo runs one capability, recorded on `lakeside`, against `prairie`,
whose labels, product names and table column order differ.

## 5. Escalation & handoff

**Detect.** During discovery: the model says it is stuck, it repeats the same action on the same screen three
times, three actions fail in a row, or the step budget runs out. During replay: a recovery rule says `escalate`
(the identity-verification challenge), a wait times out with no rule explaining it, or policy says a risky step
needs a human.

**Route.** The run builds an `InterventionRequest` with the capability or goal, the step, the location, the reason,
and a masked screenshot. It posts it to the intervention board and prints the operator URL.

**Control transfer.** A per-session `LeaseManager` answers "who is in control" with exactly one holder:
automation, human, or nobody. Control always passes through nobody, so there is never overlap. A human can only take
the lease while an intervention is open for that session, and only the holding operator can hand it back. The
guarded surface refuses any automation action while it does not hold the lease, and the console refuses human input
while the human does not hold it.

**Same live session.** The console streams the live page over a CDP screencast and injects the operator's clicks
and keys into the same browser, not a fresh one. Each input is hit-tested against the latest accessibility snapshot,
so the evidence records "clicked textbox Security Answer" in the artifact's own vocabulary. Typed text is stored only
as a length.

**Hand back.** The operator chooses resume, step completed by human, or abort, with a note. On resume the engine
re-observes and re-checks the current step's postcondition. If the human already did the step it is marked `human`,
otherwise the step is retried. Abort returns `escalated` with the note. Every transition and human action is in the
run's evidence.

**Mocked deliberately.** The console is a single local page with no authentication, bound to loopback. A real
deployment needs operator identity, a queue across sessions, and a remote session broker. The transfer model and the
transport interface do not change.

## 6. Safety

- **Allowlist, deny by default.** `policies/coreone.yaml` lists allowed origins and path patterns, blocked paths
  such as the admin API, desktop bundle ids, and action kinds per mode (discovery, replay, human). Unknown keys fail
  to load, so a typo cannot widen access. The gate runs on every action from the model, the replay engine, and the
  human, at the surface seam.
- **Risky actions.** Rules classify controls such as Submit, Transfer, Approve, or anything on a review page as
  risky, and a capability can never declare a step safer than policy thinks it is. Discovery always escalates risky
  steps to a human: the model never commits a change. Replay runs a risky step only if the capability is `approved`
  and the caller passed `--risky-confirmed`, otherwise it is denied. I chose block-or-confirm over flag-only because a
  replay runs unattended.
- **Secrets never reach the model or the artifact.** Credentials are declared, resolved from the environment at the
  last moment, and referenced only as `{{teller.password}}`. The model types placeholders, and a decision that types a
  literal credential value is rejected.
- **Redaction on every write.** Evidence, logs, snapshots, and results go through one redactor. It masks registered
  secrets in every encoding, SSNs, card numbers that pass Luhn, routing numbers that pass the ABA checksum,
  account-like digit runs, emails, phones, and labelled dates of birth. Screenshots are masked over the bounds of
  sensitive nodes before the model or disk sees them.
- **Limits.** Redaction is pattern-based, so it has false positives and negatives. Pixels outside the accessibility
  tree, such as a canvas or an image of text, cannot be masked. Policy is only as good as its rules, and the console
  has no authentication.

## 7. Cuts

- **Operator console** is minimal: one page, no auth, one session at a time, loopback only.
- **Desktop** is implemented and unit-tested against a fake accessibility backend. A real run needs Accessibility
  permission on the host, which I did not grant from automation.
- **Discovery records the happy path only.** Outcomes and recoveries come from the vendor profile, written by a
  person. Next: let an assisted, bounded single-step LLM fallback propose new profile rules for review.
- **No fingerprint baseline in the artifact**, so drift is fallback matches only. Next: store per-step fingerprints
  and compare.
- **Retry is back-off-and-observe.** It cannot re-execute a failed navigation. Next: a reload response.
- **No scaling infrastructure** (queues, workers, multi-tenant store), by design.
- **Next, with more time:** approval workflow with replay-confidence gating, per-tenant drift dashboards from
  `ReplayStats`, and a Windows UI Automation surface.
