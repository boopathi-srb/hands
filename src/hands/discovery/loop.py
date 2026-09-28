"""DiscoveryAgent: drive a live surface toward a natural-language goal with a planner, once.

The loop owns every hard part so a weak model is enough:
- compact, secret-free observations (render.py) and a short history, not a transcript
- strict schema validation plus validation against the live screen, with bounded re-prompts
- credentials substituted at the seam; the model only ever handles placeholders
- policy enforced on every surface action (mode 'discovery'); risky actions go to a human
- stuck detection: planner says stuck, the same action on the same screen 3 times, 3 failed actions in
  a row, or the step budget running out; each escalates as 'stuck' when an escalator is configured
- evidence for everything: observation, decision (rationale, latency, tokens), policy, action, result

Algorithm per turn: observe -> render -> planner.decide -> validate -> (extract | policy -> act) ->
record a TraceStep whose after-observation is filled by the next observe.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from hands.core.actions import Action, NodeRef, OpenAction
from hands.core.control import HumanAction, InterventionRequest, InterventionResolution
from hands.core.log import get_logger
from hands.core.observation import Observation
from hands.core.ports import (
    CredentialProvider,
    Escalator,
    EvidenceSink,
    PolicyDecision,
    PolicyGate,
    PolicyRequest,
    Surface,
)
from hands.discovery.credentials import SecretBook, SecretRegistrar
from hands.discovery.planner import (
    HistoryEntry,
    InputHint,
    Planner,
    PlannerContext,
    PlannerDecision,
    PlannerResponse,
)
from hands.discovery.render import (
    DEFAULT_MAX_NODES,
    mask_screenshot,
    node_display_name,
    render_observation,
    scrub_observation,
)
from hands.discovery.trace import DiscoveryOutcome, DiscoveryStatus, TraceStep, compact_trace
from hands.discovery.validation import (
    DEFAULT_ALLOWED_ACTIONS,
    DecisionRejection,
    ValidatedDecision,
    ValidationInputs,
    validate_decision,
)
from hands.locate import fill_placeholders

_logger = get_logger(__name__)

InterventionKind = Literal["stuck", "risky_action"]

REPEAT_LIMIT = 3
FAILED_ACTION_LIMIT = 3
HISTORY_LIMIT = 10
DEFAULT_MAX_ESCALATIONS = 3
DEFAULT_RESUME_STEP_GRANT = 5
MAX_RAW_TEXT_IN_EVIDENCE = 500

EVENT_RUN_STARTED = "run_started"
EVENT_OBSERVATION = "observation"
EVENT_DECISION = "decision"
EVENT_POLICY = "policy_decision"
EVENT_ACTION = "action"
EVENT_ACTION_RESULT = "action_result"
EVENT_ESCALATION = "escalation_raised"
EVENT_RUN_FINISHED = "run_finished"


@dataclass(frozen=True)
class DiscoveryLimits:
    max_steps: int = 25
    max_invalid_decisions: int = 3
    max_escalations: int = DEFAULT_MAX_ESCALATIONS
    resume_step_grant: int = DEFAULT_RESUME_STEP_GRANT
    max_rendered_nodes: int = DEFAULT_MAX_NODES
    screenshot_scale: float = 1.0


@dataclass(frozen=True)
class _Terminal:
    status: DiscoveryStatus
    reason: str


@dataclass
class _RunState:
    run_id: str
    goal: str
    entry_point: str
    input_values: dict[str, str]
    secrets: SecretBook
    step_budget: int
    started_at: datetime
    trace: list[TraceStep] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    extracted: dict[str, str] = field(default_factory=dict)
    feedback: str | None = None
    planner_calls: int = 0
    invalid_streak: int = 0
    invalid_total: int = 0
    failed_streak: int = 0
    repeat_counts: dict[str, int] = field(default_factory=dict)
    escalations: int = 0
    interventions: list[str] = field(default_factory=list)
    pending_step: int | None = None
    last_observation: Observation | None = None
    observation_count: int = 0

    def remaining_steps(self) -> int:
        return max(0, self.step_budget - self.planner_calls)


class DiscoveryAgent:
    """Runs one discovery. Depends only on core ports plus a Planner."""

    def __init__(
        self,
        surface: Surface,
        planner: Planner,
        policy: PolicyGate,
        evidence: EvidenceSink,
        credentials: CredentialProvider,
        escalator: Escalator | None = None,
        secret_registrar: SecretRegistrar | None = None,
        max_steps: int = 25,
        max_invalid_decisions: int = 3,
        run_id: str | None = None,
        *,
        limits: DiscoveryLimits | None = None,
        session_id: str = "discovery",
        allowed_actions: Sequence[str] = tuple(DEFAULT_ALLOWED_ACTIONS),
    ) -> None:
        self._surface = surface
        self._planner = planner
        self._policy = policy
        self._evidence = evidence
        self._credentials = credentials
        self._escalator = escalator
        self._secret_registrar = secret_registrar
        self._limits = limits or DiscoveryLimits(
            max_steps=max_steps, max_invalid_decisions=max_invalid_decisions
        )
        self._run_id = run_id or f"discovery-{uuid.uuid4().hex[:12]}"
        self._session_id = session_id
        self._allowed_actions = frozenset(allowed_actions)

    # ------------------------------------------------------------ public

    async def run(
        self,
        goal: str,
        entry_point: str,
        inputs: Mapping[str, str],
        credential_names: Sequence[str],
    ) -> DiscoveryOutcome:
        state = self._new_state(goal, entry_point, inputs, credential_names)
        self._event(EVENT_RUN_STARTED, mode="discovery", goal=goal, entry_point=entry_point,
                    inputs=sorted(state.input_values), credentials=state.secrets.placeholders,
                    planner=getattr(self._planner, "name", type(self._planner).__name__),
                    model=getattr(self._planner, "model", None), max_steps=self._limits.max_steps)
        terminal = await self._open_entry_point(state)
        if terminal is None:
            terminal = await self._loop(state)
        return await self._finish(state, terminal)

    # ------------------------------------------------------------ setup and teardown

    def _new_state(
        self, goal: str, entry_point: str, inputs: Mapping[str, str], credential_names: Sequence[str]
    ) -> _RunState:
        secrets = SecretBook.resolve(self._credentials, credential_names, self._secret_registrar)
        return _RunState(
            run_id=self._run_id, goal=goal, entry_point=entry_point, input_values=dict(inputs),
            secrets=secrets, step_budget=self._limits.max_steps, started_at=_now(),
        )

    async def _open_entry_point(self, state: _RunState) -> _Terminal | None:
        before = await self._observe(state)
        resolved_entry_point = fill_placeholders(state.entry_point, state.input_values).text
        action = OpenAction(entry_point=resolved_entry_point)
        verdict = self._check_policy(action, before, None, step_index=0)
        if verdict.verdict != "allow":
            return _Terminal("error", f"policy {verdict.verdict} for entry point: {verdict.reason}")
        self._event(EVENT_ACTION, step=0, action={"kind": "open", "entry_point": state.entry_point})
        result = await self._surface.act(None, action)
        self._event(EVENT_ACTION_RESULT, step=0, ok=result.ok, error=state.secrets.mask_optional(result.error))
        self._append_step(state, TraceStep(
            index=0, action="open", value_template=state.entry_point, observation_before=before,
            result="ok" if result.ok else "failed", error=result.error, policy_rule=verdict.rule,
        ))
        if not result.ok:
            return _Terminal("error", f"could not open entry point: {result.error}")
        return None

    async def _finish(self, state: _RunState, terminal: _Terminal) -> DiscoveryOutcome:
        if state.pending_step is not None or state.last_observation is None:
            await self._observe(state)
        outcome = DiscoveryOutcome(
            run_id=state.run_id, goal=state.goal, entry_point=state.entry_point,
            status=terminal.status, reason=state.secrets.mask(terminal.reason), trace=state.trace,
            extracted=dict(state.extracted), final_observation=state.last_observation,
            input_values=dict(state.input_values), credential_names=state.secrets.names,
            planner_calls=state.planner_calls, invalid_decisions=state.invalid_total,
            interventions=list(state.interventions), started_at=state.started_at, finished_at=_now(),
        )
        self._event(EVENT_RUN_FINISHED, status=outcome.status, reason=outcome.reason,
                    planner_calls=outcome.planner_calls, extracted=sorted(outcome.extracted))
        self._evidence.write_json("discovery_trace", compact_trace(outcome))
        return outcome

    # ------------------------------------------------------------ the loop

    async def _loop(self, state: _RunState) -> _Terminal:
        while True:
            if state.remaining_steps() <= 0:
                terminal = await self._on_stuck(state, "step budget exhausted", "budget_exhausted")
            else:
                terminal = await self._turn(state)
            if terminal is not None:
                return terminal

    async def _turn(self, state: _RunState) -> _Terminal | None:
        observation = await self._observe(state)
        response = await self._ask_planner(state, observation)
        if response.decision is None:
            return self._on_invalid(state, response.error or "no decision returned")
        decision = response.decision
        if decision.action == "done":
            return _Terminal("completed", decision.rationale)
        if decision.action == "stuck":
            return await self._on_stuck(state, f"planner is stuck: {decision.rationale}", "stuck")
        checked = validate_decision(decision, ValidationInputs(
            observation=observation, input_values=state.input_values, secrets=state.secrets,
            allowed_actions=self._allowed_actions,
        ))
        if isinstance(checked, DecisionRejection):
            return self._on_invalid(state, checked.feedback)
        state.invalid_streak = 0
        if self._is_repeating(state, observation, checked):
            return await self._on_stuck(state, "the same action on the same screen repeated", "stuck")
        if decision.action == "extract":
            self._extract(state, observation, checked)
            return None
        return await self._act(state, observation, checked)

    # ------------------------------------------------------------ observation

    async def _observe(self, state: _RunState) -> Observation:
        raw_observation = await self._surface.observe(include_screenshot=True)
        secret_values = state.secrets.values
        masked_png = mask_screenshot(raw_observation.screenshot_png, raw_observation, secret_values,
                                     self._limits.screenshot_scale)
        observation = scrub_observation(raw_observation, secret_values).model_copy(
            update={"screenshot_png": masked_png}
        )
        self._complete_pending_step(state, observation)
        state.last_observation = observation
        state.observation_count += 1
        self._record_observation(state, observation)
        return observation

    def _record_observation(self, state: _RunState, observation: Observation) -> None:
        name = f"obs-{state.observation_count:03d}"
        snapshot_path = self._evidence.snapshot(name, observation)
        screenshot_path = (
            self._evidence.screenshot(name, observation.screenshot_png)
            if observation.screenshot_png else None
        )
        self._event(EVENT_OBSERVATION, location=observation.location.value,
                    fingerprint=observation.fingerprint, node_count=len(observation.nodes),
                    snapshot=snapshot_path, screenshot=screenshot_path)

    def _complete_pending_step(self, state: _RunState, observation: Observation) -> None:
        if state.pending_step is None:
            return
        step = state.trace[state.pending_step]
        state.trace[state.pending_step] = step.model_copy(update={"observation_after": observation})
        state.pending_step = None

    # ------------------------------------------------------------ planner

    async def _ask_planner(self, state: _RunState, observation: Observation) -> PlannerResponse:
        rendered = render_observation(observation, secret_values=state.secrets.values,
                                      max_nodes=self._limits.max_rendered_nodes)
        context = PlannerContext(
            goal=state.goal,
            inputs=[InputHint(name=name, example=value) for name, value in state.input_values.items()],
            credential_placeholders=state.secrets.placeholders,
            observation_text=rendered.text,
            screenshot_png=observation.screenshot_png,
            history=state.history[-HISTORY_LIMIT:],
            extracted=dict(state.extracted),
            steps_remaining=state.remaining_steps(),
            feedback=state.feedback,
        )
        state.planner_calls += 1
        state.feedback = None
        response = await self._planner.decide(context)
        self._record_decision(state, response)
        return response

    def _record_decision(self, state: _RunState, response: PlannerResponse) -> None:
        decision = response.decision
        self._event(
            EVENT_DECISION, step=state.planner_calls,
            action=_decision_summary(decision, state.secrets) if decision else None,
            rationale=state.secrets.mask(decision.rationale) if decision else None,
            expected_result=state.secrets.mask_optional(decision.expected_result) if decision else None,
            error=state.secrets.mask_optional(response.error),
            raw_text=state.secrets.mask(response.raw_text[:MAX_RAW_TEXT_IN_EVIDENCE]),
            latency_ms=response.latency_ms, input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=response.usage.cache_read_input_tokens,
        )

    def _on_invalid(self, state: _RunState, problem: str) -> _Terminal | None:
        state.invalid_streak += 1
        state.invalid_total += 1
        masked_problem = state.secrets.mask(problem)
        state.feedback = f"Your last answer was rejected: {masked_problem}"
        self._event(EVENT_DECISION, step=state.planner_calls, rejected=True, reason=masked_problem)
        if state.invalid_streak >= self._limits.max_invalid_decisions:
            return _Terminal(
                "error", f"{state.invalid_streak} invalid decisions in a row; last: {masked_problem}"
            )
        return None

    # ------------------------------------------------------------ stuck detection

    def _is_repeating(self, state: _RunState, observation: Observation, checked: ValidatedDecision) -> bool:
        decision = checked.decision
        signature = "|".join((
            observation.fingerprint, decision.action, checked.node.ref if checked.node else "",
            decision.value or "", decision.key or "", decision.option or "",
        ))
        state.repeat_counts[signature] = state.repeat_counts.get(signature, 0) + 1
        return state.repeat_counts[signature] >= REPEAT_LIMIT

    async def _on_stuck(
        self, state: _RunState, reason: str, unhandled_status: DiscoveryStatus
    ) -> _Terminal | None:
        escalator = self._escalator
        if escalator is None or state.escalations >= self._limits.max_escalations:
            return _Terminal(unhandled_status, reason)
        resolution = await self._escalate(escalator, state, "stuck", reason)
        if resolution.outcome == "abort":
            return _Terminal("escalated_abort", f"{reason}; operator aborted: {resolution.note}")
        self._after_human_help(state, resolution)
        if state.remaining_steps() <= 0:
            state.step_budget = state.planner_calls + self._limits.resume_step_grant
        return None

    def _after_human_help(self, state: _RunState, resolution: InterventionResolution) -> None:
        summary = summarize_human_actions(resolution)
        state.feedback = f"A human operator acted: {summary}"
        state.repeat_counts.clear()
        state.failed_streak = 0
        state.invalid_streak = 0
        if resolution.human_actions or resolution.outcome == "step_completed_by_human":
            self._record_human_step(state, summary)

    def _record_human_step(self, state: _RunState, summary: str) -> None:
        before = state.last_observation
        if before is None:
            return
        self._append_step(state, TraceStep(
            index=len(state.trace), action="human", observation_before=before, result="human",
            human_summary=summary,
        ))
        state.history.append(HistoryEntry(step=len(state.trace), action="human", result=summary))

    async def _escalate(
        self, escalator: Escalator, state: _RunState, kind: InterventionKind, reason: str
    ) -> InterventionResolution:
        state.escalations += 1
        intervention_id = f"{state.run_id}-int-{state.escalations}"
        observation = state.last_observation
        screenshot_path = (
            self._evidence.screenshot(f"intervention-{state.escalations}", observation.screenshot_png)
            if observation is not None and observation.screenshot_png else None
        )
        masked_reason = state.secrets.mask(reason)
        request = InterventionRequest(
            intervention_id=intervention_id, session_id=self._session_id, run_id=state.run_id,
            mode="discovery", kind=kind, reason=masked_reason, goal=state.goal,
            location=observation.location.value if observation else None,
            screenshot_path=screenshot_path or None, created_at=_now(),
        )
        state.interventions.append(intervention_id)
        self._event(EVENT_ESCALATION, intervention_id=intervention_id, intervention_kind=kind,
                    reason=masked_reason)
        return await escalator.escalate(request)

    # ------------------------------------------------------------ extract

    def _extract(self, state: _RunState, observation: Observation, checked: ValidatedDecision) -> None:
        node = checked.node
        output_name = checked.decision.output_name or ""
        value = (node_display_name(node) or node.value or "") if node else ""
        state.extracted[output_name] = value
        self._append_step(state, TraceStep(
            index=len(state.trace), action="extract", decision=_masked_decision(checked.decision, state),
            node_before=node, observation_before=observation, observation_after=observation,
            result="ok", output_name=output_name, extracted_value=value,
        ))
        state.history.append(HistoryEntry(
            step=len(state.trace), action="extract", node_ref=node.ref if node else None,
            target=_node_label(node), result=f"extracted {output_name} = {value}",
        ))

    # ------------------------------------------------------------ act

    async def _act(self, state: _RunState, observation: Observation, checked: ValidatedDecision) -> _Terminal | None:
        assert checked.surface_action is not None  # every non-extract decision has one
        verdict = self._check_policy(checked.surface_action, observation, checked, len(state.trace))
        if verdict.verdict == "deny":
            self._record_refused(state, observation, checked, verdict)
            return None
        if verdict.verdict == "escalate":
            return await self._act_after_approval(state, observation, checked, verdict)
        return await self._perform(state, observation, checked, verdict)

    async def _act_after_approval(
        self, state: _RunState, observation: Observation, checked: ValidatedDecision, verdict: PolicyDecision
    ) -> _Terminal | None:
        escalator = self._escalator
        if escalator is None:
            reason = f"needs human approval, none available. {verdict.reason}"
            self._record_refused(state, observation, checked, verdict.model_copy(update={"reason": reason}))
            return None
        resolution = await self._escalate(escalator, state, "risky_action", verdict.reason)
        if resolution.outcome == "abort":
            return _Terminal("escalated_abort", f"risky action declined by operator: {resolution.note}")
        if resolution.outcome == "step_completed_by_human":
            self._after_human_help(state, resolution)
            return None
        return await self._perform(state, observation, checked, verdict)

    async def _perform(
        self, state: _RunState, observation: Observation, checked: ValidatedDecision, verdict: PolicyDecision
    ) -> _Terminal | None:
        assert checked.surface_action is not None
        step_index = len(state.trace)
        target = NodeRef(ref=checked.node.ref) if checked.node else None
        self._event(EVENT_ACTION, step=step_index,
                    action=_decision_summary(checked.decision, state.secrets))
        result = await self._surface.act(target, checked.surface_action)
        error = state.secrets.mask_optional(result.error)
        self._event(EVENT_ACTION_RESULT, step=step_index, ok=result.ok, error=error)
        self._append_step(state, TraceStep(
            index=step_index, action=checked.decision.action,  # type: ignore[arg-type]
            decision=_masked_decision(checked.decision, state), value_template=checked.value_template,
            node_before=checked.node, observation_before=observation,
            result="ok" if result.ok else "failed", error=error, risk=verdict.risk,
            policy_rule=verdict.rule,
        ))
        state.history.append(_history_entry(state, checked, "ok" if result.ok else f"failed: {error}"))
        return await self._track_failures(state, result.ok, error)

    async def _track_failures(self, state: _RunState, ok: bool, error: str | None) -> _Terminal | None:
        if ok:
            state.failed_streak = 0
            return None
        state.failed_streak += 1
        state.feedback = f"The action failed: {error}"
        if state.failed_streak >= FAILED_ACTION_LIMIT:
            return await self._on_stuck(state, f"{state.failed_streak} actions failed in a row", "stuck")
        return None

    def _record_refused(
        self, state: _RunState, observation: Observation, checked: ValidatedDecision, verdict: PolicyDecision
    ) -> None:
        self._append_step(state, TraceStep(
            index=len(state.trace), action=checked.decision.action,  # type: ignore[arg-type]
            decision=_masked_decision(checked.decision, state), value_template=checked.value_template,
            node_before=checked.node, observation_before=observation, observation_after=observation,
            result="denied", error=verdict.reason, risk=verdict.risk, policy_rule=verdict.rule,
        ))
        state.feedback = f"Policy refused that action: {verdict.reason} Choose a different action."
        state.history.append(_history_entry(state, checked, "refused by policy"))

    def _check_policy(
        self, action: Action, observation: Observation, checked: ValidatedDecision | None, step_index: int
    ) -> PolicyDecision:
        request = PolicyRequest(
            mode="discovery", action=action, location=observation.location,
            target_node=checked.node if checked else None,
        )
        verdict = self._policy.check(request)
        self._event(EVENT_POLICY, step=step_index, action={"kind": action.kind}, verdict=verdict.verdict,
                    risk=verdict.risk, rule=verdict.rule, reason=verdict.reason)
        return verdict

    # ------------------------------------------------------------ bookkeeping

    def _append_step(self, state: _RunState, step: TraceStep) -> None:
        state.trace.append(step)
        if step.observation_after is None:
            state.pending_step = len(state.trace) - 1

    def _event(self, kind: str, **data: Any) -> None:
        self._evidence.event(kind, run_id=self._run_id, **data)


# ---------------------------------------------------------------- helpers


def summarize_human_actions(resolution: InterventionResolution) -> str:
    """Operator inputs in artifact vocabulary; typed text only as a length."""
    described = [_describe_human_action(action) for action in resolution.human_actions]
    parts = described or ["no recorded inputs"]
    if resolution.note:
        parts.append(f"note: {resolution.note}")
    return "; ".join(parts)


def _describe_human_action(action: HumanAction) -> str:
    if action.kind == "type":
        return f"typed {action.text_length or 0} characters"
    if action.kind == "press":
        return f"pressed {action.key or 'a key'}"
    if action.node_role or action.node_name:
        return f"{action.kind} on {action.node_role or 'element'} '{action.node_name or ''}'"
    return action.kind


def _masked_decision(decision: PlannerDecision, state: _RunState) -> PlannerDecision:
    return decision.model_copy(update={
        "rationale": state.secrets.mask(decision.rationale),
        "expected_result": state.secrets.mask_optional(decision.expected_result),
        "value": state.secrets.mask_optional(decision.value),
    })


def _decision_summary(decision: PlannerDecision, secrets: SecretBook) -> dict[str, Any]:
    return {
        "kind": decision.action,
        "node_ref": decision.node_ref,
        "value": secrets.mask_optional(decision.value),
        "key": decision.key,
        "option": decision.option,
        "output_name": decision.output_name,
    }


def _node_label(node: Any) -> str:
    if node is None:
        return ""
    return f'{node.role} "{node_display_name(node)}"'


def _history_entry(state: _RunState, checked: ValidatedDecision, result: str) -> HistoryEntry:
    decision = checked.decision
    shown_value = checked.value_template or decision.option or decision.key
    return HistoryEntry(
        step=len(state.trace), action=decision.action,
        node_ref=checked.node.ref if checked.node else None, target=_node_label(checked.node),
        value=state.secrets.mask_optional(shown_value), result=result,
    )


def _now() -> datetime:
    return datetime.now(UTC)

