"""Standard evidence event kinds. `EvidenceSink.event(kind, **data)` accepts any string, but producers should
use these so reviewers, the summary renderer and tooling agree on meaning.

Conventional data keys (all optional) that `summary.md` understands:
step_id, action ({kind, ...}), reason / rationale, verdict / decision, rule, outcome / status / ok, code, error.
"""

from __future__ import annotations

from enum import StrEnum


class EventKind(StrEnum):
    RUN_STARTED = "run_started"
    """A run began. data: mode, capability_id/version or goal, tenant_id, planner/model."""

    OBSERVATION = "observation"
    """The surface was observed. data: step_id, location, fingerprint, node_count, snapshot/screenshot paths."""

    DECISION = "decision"
    """A planner (discovery) or the replay engine chose the next action. data: step_id, action, rationale."""

    POLICY_DECISION = "policy_decision"
    """The policy gate judged an action. data: step_id, action, verdict, risk, rule, reason."""

    ACTION = "action"
    """An action was sent to the surface. data: step_id, action, target description."""

    ACTION_RESULT = "action_result"
    """The surface reported the action's result. data: step_id, ok, error, duration_ms."""

    RECOVERY_APPLIED = "recovery_applied"
    """A declared recovery rule absorbed an interruption. data: step_id, recovery, response, applications."""

    OUTCOME_DETECTED = "outcome_detected"
    """A declared business outcome fired (e.g. MEMBER_NOT_FOUND). data: step_id, code, message."""

    CHECKPOINT = "checkpoint"
    """A checkpoint or postcondition was evaluated. data: step_id, ok, expected, observed."""

    ESCALATION_RAISED = "escalation_raised"
    """An intervention was raised for a human. data: intervention_id, kind, reason, step_id."""

    CONTROL_TRANSFERRED = "control_transferred"
    """The control lease changed hands. data: from, to, holder_id, reason."""

    HUMAN_ACTION = "human_action"
    """An operator input during an intervention (typed text is never recorded, only its length)."""

    RUN_FINISHED = "run_finished"
    """A run ended. data: status (success/business_outcome/escalated/failed), code, duration_ms."""

    ERROR = "error"
    """An unexpected error inside the harness. data: where, error, step_id."""


EVENT_KIND_DESCRIPTIONS: dict[str, str] = {
    EventKind.RUN_STARTED: "run began",
    EventKind.OBSERVATION: "surface observed",
    EventKind.DECISION: "next action chosen",
    EventKind.POLICY_DECISION: "policy gate verdict",
    EventKind.ACTION: "action sent to surface",
    EventKind.ACTION_RESULT: "surface reported result",
    EventKind.RECOVERY_APPLIED: "recovery rule applied",
    EventKind.OUTCOME_DETECTED: "business outcome detected",
    EventKind.CHECKPOINT: "checkpoint evaluated",
    EventKind.ESCALATION_RAISED: "human intervention raised",
    EventKind.CONTROL_TRANSFERRED: "control lease transferred",
    EventKind.HUMAN_ACTION: "operator input",
    EventKind.RUN_FINISHED: "run ended",
    EventKind.ERROR: "harness error",
}

STANDARD_EVENT_KINDS: tuple[str, ...] = tuple(kind.value for kind in EventKind)
