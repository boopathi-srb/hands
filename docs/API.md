# hands HTTP API (contract)

The web UI talks only to this API. One process (`hands serve`) hosts the API, the CoreOne mock app on
127.0.0.1:8700 (internal only), the operator console routes, and optionally the built UI at `/`.

## Conventions

- Base path `/api`. JSON everywhere. Times are ISO 8601 UTC.
- **Auth:** if env `HANDS_API_TOKEN` is set, every `/api/*` and `/console/*` request needs
  `Authorization: Bearer <token>`; websockets take `?token=<token>`. `GET /api/health` is always public.
  Missing/wrong token → 401 `{"error": "unauthorized"}`.
- **CORS:** allowed origins from env `HANDS_CORS_ORIGINS` (comma-separated), e.g. the Vercel URL.
- **Errors:** `{"error": "<code>", "message": "<human text>"}` with 4xx/5xx. Codes used: `unauthorized` (401),
  `invalid_request` (422: body/query shape, unknown body fields, out-of-range numbers), `unknown_tenant`,
  `unknown_fault`, `unknown_planner`, `planner_unavailable`, `unknown_input` (400), `unknown_capability`,
  `unknown_run`, `file_not_found`, `not_found` (404), `busy` (409).
- **One run at a time** (one Chromium). Starting a run while one is active → 409 `{"error": "busy", "run_id": ...}`.

## Health and reference data

`GET /api/health` → `{"status": "ok", "auth_required": bool, "mock_app": "up"|"down",
  "planners": {"anthropic": bool, "ollama": bool, "scripted": true}, "active_run": run_id|null, "version": str}`

`GET /api/tenants` → `[{"id": "lakeside", "name": "Lakeside Community CU"}, {"id": "prairie", "name": "Prairie Federal CU"}]`

`GET /api/faults` → `[{"name": "session_expired", "description": "..."} , ...]` (the mock app's injectable faults)

## Catalog

`GET /api/capabilities` → `CatalogEntry[]` (as `hands.catalog.CatalogEntry`: id, latest_version, versions, status,
  title, description, inputs, outputs, outcome_codes) plus `stats` (the latest version's `ReplayStats`: runs,
  successes, business_outcomes, failures, fallback_matches). Unknown id or version → 404 `unknown_capability`.

`GET /api/capabilities/{id}?version=` → `{"capability": <Capability JSON>, "overlays": ["prairie", ...],
  "tool": <tool definition from capability_tool_schema>}`

`POST /api/capabilities/{id}/approve` `{"version"?: str}` → `{"id", "version", "status": "approved"}`

## Runs

`POST /api/runs/replay`
```json
{"capability_id": "coreone.member_balance", "version": null, "inputs": {"member_number": "10001"},
 "tenant": "lakeside", "faults": [{"name": "session_expired", "count": 1}], "risky_confirmed": false,
 "escalation": "console"}
```
→ 202 `{"run_id": "replay-ab12cd34ef56"}`. `escalation`: `"console"` (a human resolves interventions in the UI)
or `"none"`. Only `capability_id` is required; defaults: `version` latest, `inputs` {}, `tenant` "lakeside"
(`null` = base capability, no overlay), `faults` [], `risky_confirmed` false, `escalation` "console".
`faults[].count` is 1..1000 (default 1). Unknown body fields → 422. Faults are armed on the mock app before the
run; with `HANDS_SURFACE=fake` they are injected into the in-memory fake instead.

`POST /api/runs/discovery`
```json
{"goal": "Look up member {{member_number}} ...", "inputs": {"member_number": "10001"}, "sensitive_inputs": [],
 "capability_id": "coreone.member_balance", "title": "...", "description": "...", "tenant": "lakeside",
 "planner": "anthropic", "model": null, "max_steps": 25, "escalation": "console"}
```
→ 202 `{"run_id": "disc-..."}`. Planner `"anthropic"` needs `ANTHROPIC_API_KEY` on the server, else 400
`planner_unavailable`; planners are `anthropic`, `ollama`, `scripted`. Only `goal` is required; the other fields
default to the values shown above (planner "anthropic"). The entry point is `<target url>/t/<tenant>/login`.
Every `sensitive_inputs` name must be a key of `inputs` (else 400 `unknown_input`). Discovery saves the artifact
(same id and version overwrite).

`GET /api/runs?limit=50` → newest first:
```json
[{"run_id": "...", "mode": "replay"|"discovery", "state": "running"|"waiting_for_operator"|"finished"|"error",
  "status": "success"|"business_outcome"|"escalated"|"failed"|"completed"|"stuck"|"error"|null,
  "capability_id": "...", "tenant": "...", "started_at": "...", "finished_at": "...",
  "headline": "short human summary, e.g. 'savings_balance 9870.12' or 'MEMBER_NOT_FOUND'"}]
```
Includes runs found on disk under the evidence root (from earlier sessions), not just this process. `limit` is
1..500. `state` is `running` until the run returns, `waiting_for_operator` while an intervention for that run is
open on the shared board, `finished` once a result exists, `error` when the run could not start (e.g. browser
launch failed) or crashed. Discovery `status` is one of `completed`, `stuck`, `escalated_abort`,
`budget_exhausted`, `error`. `headline` formats: success → `"<output> <value>, ..."`, business outcome →
the code, escalated → `"escalated: <operator note or reason>"`, failed → `"failed: <code> at <step>"`,
discovery → `"recorded <id>@<version>"` or `"<status>: <reason>"`, error → `"error: <message>"`, running →
`"replaying <capability>"` / `"discovering <capability>"`, waiting → `"waiting for operator: <reason>"`.

`GET /api/runs/{run_id}` → the list item plus:
`{"result": <RunResult JSON or discovery summary>|null, "intervention": <open InterventionRequest + lease>|null,
  "files": {"screenshots": ["screenshots/005-obs-001.png", ...], "snapshots": [...]}}`
`intervention` is the InterventionRequest JSON (intervention_id, session_id, run_id, mode, kind, reason, step_id,
capability_id, screenshot_path, created_at, ...) with one extra key `"lease"` (the session's current lease, or
null). Replay writes screenshots/snapshots only on failure and escalation, so a successful replay has empty
`files` lists. A crashed run's `result` is `{"status": "error", "message": ...}`. Unknown run → 404 `unknown_run`.

`GET /api/runs/{run_id}/events?after=<seq>` → `{"events": [{"seq", "ts", "kind", "data"}], "last_seq": int,
  "state": ...}` — redacted events from `events.jsonl` with seq > after. The UI polls this every ~1 s while running.

`GET /api/runs/{run_id}/files/{path}` → the file (png or json). Path must stay inside the run dir, else 404
`file_not_found` (also for any other suffix, e.g. summary.md or events.jsonl). `result.json`,
`discovery_result.json` and `capability.json` are servable.

## Operator console (human handoff)

Mounted from `hands.console` under `/console`, sharing one intervention board across all runs:
- `GET /console/api/interventions`, `GET /console/api/interventions/{id}`
- `POST /console/api/interventions/{id}/take {"operator_id"}`
- `POST /console/api/interventions/{id}/handback {"operator_id", "outcome": "resume"|"abort"|"step_completed_by_human", "note"}`
- `WS /console/api/sessions/{session_id}/live?operator_id=...&token=...` — server sends
  `{"type": "frame", "mime", "data"}` (base64) and status messages; client sends
  `{"kind": "pointer", "event": {"type": "click", "x", "y", "button": "left"}}` and
  `{"kind": "key", "event": {"type": "char"|"down"|"up", "key", "text"?}}`. Coordinates are frame pixels.
`session_id` equals the run id. With a token configured, a websocket without a valid `?token=` is refused at the
handshake (HTTP 403 from the server; the ASGI close code is 4401). The operator page at `GET /console/` needs the
bearer header like every other /console route.
