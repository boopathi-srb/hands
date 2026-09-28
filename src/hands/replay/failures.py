"""Hard-failure detail: readable expected/observed text and the evidence written for every failure."""

from __future__ import annotations

from hands.core.observation import Observation
from hands.core.results import FailureCode
from hands.core.targets import (
    Candidate,
    LabelCandidate,
    RoleNameCandidate,
    StructuralCandidate,
    TargetSpec,
    TextAnchorCandidate,
)
from hands.replay.context import RunContext
from hands.replay.signals import FailureEnd, TimedOut, WaitPhase

MAX_OBSERVED_TEXTS = 8
MAX_TEXT_CHARS = 60
_TEXT_ROLES = ("heading", "text", "alert", "status", "dialog", "statictext", "paragraph")
_TIMEOUT_CODES: dict[WaitPhase, FailureCode] = {
    "precondition": "precondition_timeout",
    "target": "target_not_found",
    "postcondition": "postcondition_timeout",
    "until": "postcondition_timeout",
    "checkpoint": "checkpoint_failed",
}


def describe_observation(observation: Observation | None) -> str:
    """Location, title, open dialogs and a short list of visible headings/texts."""
    if observation is None:
        return "nothing observed yet"
    location = observation.location
    parts = [f"location {location.value!r}", f"title {location.title!r}"]
    if observation.dialogs:
        dialog_texts = [_shorten(dialog.title or dialog.text) for dialog in observation.dialogs]
        parts.append(f"dialogs {dialog_texts}")
    parts.append(f"visible text {visible_texts(observation)}")
    return "; ".join(parts)


def visible_texts(observation: Observation) -> list[str]:
    texts: list[str] = []
    for node in observation.nodes:
        text = _shorten(node.text or node.name)
        if node.role in _TEXT_ROLES and text and text not in texts:
            texts.append(text)
        if len(texts) >= MAX_OBSERVED_TEXTS:
            break
    return texts


def describe_candidate(candidate: Candidate) -> str:
    if isinstance(candidate, RoleNameCandidate):
        return f"role_name({candidate.role} {candidate.name!r})"
    if isinstance(candidate, LabelCandidate):
        return f"label({candidate.label!r})"
    if isinstance(candidate, TextAnchorCandidate):
        return f"text_anchor({candidate.relation} {candidate.anchor_text!r} #{candidate.ordinal})"
    if isinstance(candidate, StructuralCandidate):
        return f"structural({'/'.join(candidate.container_path)} {candidate.structural_path})"
    return f"visual_anchor({candidate.anchor_text!r} {candidate.dx:+.0f},{candidate.dy:+.0f})"


def describe_target(spec: TargetSpec) -> str:
    tried = ", ".join(describe_candidate(candidate) for candidate in spec.candidates)
    return f"{spec.description!r} via one of {len(spec.candidates)} candidates: {tried}"


def timeout_failure(step_id: str | None, timed_out: TimedOut, timeout_ms: int) -> FailureEnd:
    """Map a wait timeout to its failure code with expected (the condition detail) and observed."""
    readiness = timed_out.readiness
    code = _TIMEOUT_CODES[readiness.phase]
    subject = f"step '{step_id}'" if step_id else "the checkpoint"
    return FailureEnd(
        code=code,
        step_id=step_id,
        message=f"{readiness.phase} not met for {subject} within {timeout_ms} ms",
        expected=readiness.detail,
        observed=describe_observation(timed_out.observation),
    )


def run_timeout_failure(ctx: RunContext, step_id: str | None) -> FailureEnd:
    return FailureEnd(
        code="run_timeout",
        step_id=step_id,
        message=f"run exceeded run_timeout_ms={ctx.invocation.run_timeout_ms}",
        expected=f"run completes within {ctx.invocation.run_timeout_ms} ms",
        observed=describe_observation(ctx.state.last_observation),
    )


def capture_failure_evidence(ctx: RunContext, failure: FailureEnd) -> list[str]:
    """Screenshot + a11y snapshot of the latest observation. Nothing to capture before the first observe."""
    observation = ctx.state.last_observation
    if observation is None:
        return []
    name = f"failure-{failure.step_id or 'run'}"
    evidence_paths = [ctx.ports.evidence.snapshot(name, observation)]
    if observation.screenshot_png:
        evidence_paths.append(ctx.ports.evidence.screenshot(name, observation.screenshot_png))
    return evidence_paths


def _shorten(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= MAX_TEXT_CHARS:
        return collapsed
    return collapsed[: MAX_TEXT_CHARS - 3] + "..."
