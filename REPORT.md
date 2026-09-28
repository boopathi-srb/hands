# REPORT

`hands` lets an AI agent operate legacy bank software that has no API. A model discovers a flow once. The flow
becomes a typed, versioned capability. Production invokes it by deterministic replay, with no model in the loop.

## 1. Architecture

One Python process and one CLI with three verbs: `discover`, `replay`, `catalog`. There are no queues or services;
each seam below is where a service boundary would go later.

```
goal ─► DiscoveryAgent ─(Planner port: Ollama | Anthropic | Scripted | Cassette)
            │ observe → decide → validate → policy → act
            ▼
        recorder ─► Capability (+ vendor AppProfile, + tenant overlay) ─► ArtifactStore
                                                                              │
agent call (id + typed inputs) ─► ReplayEngine ◄─────────────────────────────┘
            │ wait(pre + target) → monitors → policy → act → wait(post) → extract → checkpoint
            ▼
     GuardedSurface (control lease + policy + evidence)
            ▼
     Surface port ── BrowserSurface (Playwright/CDP) │ MacDesktopSurface (AX API) │ FakeSurface
            ▼
     LiveViewTransport ── CDP screencast │ window capture + CGEvent  ◄── operator console
```

- **Perceive through the accessibility tree, not the DOM.** Every surface returns the same `Observation`. Each node
  has a role, name, text, value, label, container path, role-indexed structural path, and bounds. Browsers and
  desktop OSes both expose this tree, so a recorded flow never contains CSS, XPath, or a toolkit name. Screenshots go
  to the model and to evidence; coordinates are the last-resort locator.
- **Locator logic is pure.** `hands.locate` resolves targets and evaluates conditions as functions over an
  `Observation`. Surfaces only observe and act, so resolution behaves the same everywhere and is tested without a
  browser.
- **Guardrails sit at the seam, not in the prompt.** Every action from the model, the engine, or a human passes the
  policy gate and the control lease before it reaches the surface.
- **Built against a weak model.** All discovery development used a local 8B vision model (Qwen3-VL via Ollama). It
  completed the goal on the live app with zero invalid decisions. The loop owns validation, re-prompting, stuck
  detection, and secret substitution, so a stronger model only helps. Claude Sonnet 5 is wired in for the production
  run.
- **Trade-off.** Because it is a single process, the operator console shares the run's event loop: it needs the live
  surface object. Remote operators would need a session broker. The transport interface already has that shape.

## 2. Artifact schema

Source: `src/hands/core/artifact.py` (Pydantic, exports JSON Schema). Example:
`evidence/artifact/coreone.member_balance-1.0.0.json`. A `Capability` is a contract first and a step list second.

- **Identity:** `id`, semver `version`, `status` (draft, approved, deprecated), `schema_version`.
- **Contract for the caller:** `title`, `description`, typed `inputs` (type, pattern, required, sensitive), and
  typed `outputs`. `hands catalog tools` renders this as a tool definition an agent can call.
- **Credentials** are declared by name and field. They are resolved at replay from a credential provider and
  referenced only as `{{teller.password}}`. The caller never passes them.
- **Steps:** open, click, type, press, select, extract, wait, subflow. Each step has an optional precondition and
  postcondition, a timeout, a risk class, and step-scoped recoveries.
- **Targets** are ranked candidate lists: role and name, label, text anchor with a spatial relation, container and
  structural path, then a visual offset. Each candidate carries a confidence and a one-line reason for the reviewer.
  The recorder keeps a candidate only if it resolves uniquely back to the node the model acted on.
- **Conditions** are one small declarative language: text visible, node present, location matches, dialog open
  (native or in-page), value matches, and all/any/not. The checkpoint, pre- and postconditions, outcome detectors,
  and recovery triggers all use it.
- **Runtime knowledge is data.** `outcomes` are business results such as `MEMBER_NOT_FOUND`, each with a message
  target. `recoveries` are dismiss, retry, subflow, or escalate, each bounded. The engine has no app-specific code.
  Both come from a per-vendor `AppProfile`, because a happy-path discovery run cannot observe "member not found".
- **Provenance and stats:** discovery run, planner, model, and goal; replay counts and fallback-match counts.
- **Validators** reject duplicate step ids, undeclared placeholders, outputs that are never extracted, unknown
  recoveries or subflows, and outcome scopes that name missing steps.

The caller needs a function signature and an error vocabulary. The reviewer needs to see what will be clicked and
why it will still be found next month. The engine needs to know which screens are answers and which are
interruptions. Transcript details stay in evidence.

## 3. Determinism & error handling

**Determinism.** For every step the engine waits until the precondition holds and the target resolves, runs the
monitors, checks policy, acts, and waits for the postcondition. Waits poll conditions under per-step timeouts; there
are no fixed sleeps. Candidates are tried in rank order and the matched rank is recorded. A run succeeds only if the
final checkpoint holds. Outputs are coerced to their declared types, and decimals stay strings (`"1250.00"`).

**Error taxonomy.** Inputs are validated against the contract before the app is touched. After that, on every
observation in every wait, monitors run in a fixed order:

1. **Business outcomes** return `business_outcome` with the code and the app's own message. This is an answer, not
   an error.
2. **Recoveries** are absorbed into the step trace and never become a status. Each is bounded by
   `max_applications`:
   - a known notice or native alert is dismissed;
   - a session expiry triggers a re-sign-on subflow, then a restart;
   - an app error page triggers one restart, because waiting alone cannot clear it;
   - an identity challenge is escalated to a human.
3. **Anything else** that blocks progress is a hard failure with a code, for example `target_not_found`,
   `postcondition_timeout`, `recovery_exhausted`, or `policy_denied`. It carries the step, the expected condition's
   own explanation, what was observed (location, dialogs, visible text), and paths to a screenshot and an
   accessibility snapshot. With an operator configured, an unexplained timeout is escalated once before failing.

`evidence/README.md` shows all 14 cases on the live app. They cover success, two business outcomes, invalid input,
five recoveries, two hard failures, the tenant variant, and handoff abort and resume.

**Drift.** A step resolved by a fallback candidate still succeeds, but it is listed in `drift.fallback_steps` and
counted in the artifact's stats. That is the early warning that a tenant or version is diverging.

## 4. Heterogeneity & multi-tenant

**Surface abstraction.** The seam is the `Surface` port. `observe()` returns an accessibility `Observation`;
`act()` takes a node reference or a point plus a surface-neutral action. Everything above it is surface-agnostic. A
test fails the build if anything outside the browser package imports Playwright, or anything outside the desktop
package imports pyobjc.

- **Modern and legacy web** share `BrowserSurface`. It reads the tree per frame over CDP, so framesets and layout
  tables are just nodes with container paths like `frame:content`. It waits for child-frame navigations to settle.
- **Desktop** is `MacDesktopSurface` over the macOS Accessibility API. It produces the same `Observation`, with
  windows and sheets as container paths. Windows UI Automation would be one more adapter of the same shape.
- **Live view** follows the same pattern: a CDP screencast for the browser, window capture plus synthetic input for
  the desktop.

**Multi-tenant reuse** has three layers, from shared to specific:

1. The **capability**, keyed by vendor product and version, describes the flow once.
2. The **vendor profile** holds the product's outcomes, recoveries, and sign-on subflow. Fix it once and every
   tenant benefits.
3. A **tenant overlay** may override entry points, targets for named steps, text aliases, and outcome conditions. It
   may not add or remove steps. It declares the base version range it was validated against.

The demo replays the lakeside capability on `prairie`. Prairie renames Member Number to Account Number and Search to
Find, renames the savings product, and reorders the shares table. The overlay is three aliases, one entry point, and
one target override: "the second cell in the Share Savings row", with a structural fallback. **Drift detection**
uses fallback-candidate matches per step and structural fingerprints on each step trace. A tenant that starts
matching through fallbacks needs an overlay or a re-discovery on that tenant.

## 5. Escalation & handoff

**Detect.** In discovery, a run escalates when the model declares itself stuck, repeats the same action on the same
screen three times, fails three actions in a row, or runs out of steps. In replay, it escalates when a recovery rule
says so, a wait times out with no rule explaining it, or policy requires a human for a risky step.

**Route.** An `InterventionRequest` carries the goal or capability, the step, the location, the reason, and a
masked screenshot. It is posted to the intervention board, and the run prints the operator URL.

**Transfer.** A per-session `LeaseManager` has exactly one holder: automation, human, or nobody. Control always
passes through nobody, so holders never overlap. A human can take the lease only while an intervention is open, and
only the holding operator can hand it back. The guarded surface refuses automation actions without the lease, and
the console refuses human input without it.

**Same live session.** The console streams the page over a CDP screencast and injects the operator's input into the
same browser. Each input is hit-tested against the latest accessibility snapshot, so evidence reads "click button
Verify" in the artifact's own vocabulary. Typed text is kept only as a length.

**Hand back.** The operator chooses resume, step completed by human, or abort, and can add a note. On resume the
engine re-observes and re-checks the current step. A step the human already finished is marked `human`; otherwise it
is retried. Abort returns `escalated` with the note. In the evidence run the operator answered the identity challenge
and the same run finished with the balance.

**Mocked deliberately.** The console is one local page with no authentication and one session at a time. A real
deployment needs operator identity, a queue, and a remote session broker. The lease model and transport interface
would not change.

## 6. Safety

- **Deny-by-default allowlist.** `policies/coreone.yaml` lists origins, path patterns, blocked paths (the admin
  API), desktop bundle ids, and allowed action kinds per mode. Unknown keys fail to load, so a typo cannot widen
  access.
- **Risky actions.** Rules mark controls such as Submit, Transfer, or Approve, and anything on a review page, as
  risky. A capability cannot declare a step safer than policy does.
  - In discovery, risky steps always escalate, so the model never commits a change.
  - In replay, a risky step runs only if the capability is `approved` and the caller passed `--risky-confirmed`;
    otherwise it is denied. I chose block-or-confirm over flag-only because replay runs unattended.
- **Secrets never reach the model or the artifact.** Credentials are resolved at the last moment and appear only as
  placeholders. A decision that types a literal credential value is rejected.
- **Redaction on every write.** Evidence, logs, snapshots, and results pass through one redactor. It masks
  registered secrets in every encoding, plus SSNs, card numbers that pass Luhn, routing numbers that pass the ABA
  checksum, account-like digit runs, emails, phones, and labelled dates of birth. Screenshots are blacked out over
  sensitive nodes before the model or the disk sees them.
- **A limit found in practice.** A secret scan of the evidence found the demo password inside Playwright trace
  archives, which record typed input outside the redactor. Traces are now opt-in (`--trace`) and local-only. The
  lesson: any new evidence channel must go through the redactor or not be persisted.
- **Other limits.** Pattern-based redaction has false positives and negatives. Pixels outside the accessibility tree,
  such as a canvas, cannot be masked. The console has no authentication.

## 7. Cuts

- **Claude Sonnet 5 production run:** implemented and unit-tested with a mocked client, but not run, because no API
  key was available. It is one command in the README.
- **Desktop:** implemented and tested against a fake AX backend. A real observation needs Accessibility permission
  for the terminal, which is a manual security setting.
- **Operator console:** minimal. It has one page, no authentication, and one session.
- **Discovery records the happy path.** Outcomes and recoveries come from the hand-written vendor profile. Next: a
  bounded, policy-checked single-step LLM fallback on replay failure that proposes profile rules for review.
- **Drift baseline:** there is no per-step fingerprint baseline in the artifact, so drift means fallback matches
  only. Next: store baselines and compare.
- **No scaling infrastructure** (queues, workers, multi-tenant store), by design.
- **Next, with more time:** confidence scoring and approval gating from `ReplayStats`, per-tenant drift reports,
  and a Windows UI Automation surface.
