"""Turn the internal end of a run into the public RunResult, and record it as evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from hands.core.ports import EvidenceSink
from hands.core.results import (
    BusinessOutcomeResult,
    DriftReport,
    EscalatedResult,
    FailedResult,
    FailureDetail,
    RunResult,
    StepTrace,
    SuccessResult,
)
from hands.replay.context import RunContext
from hands.replay.failures import capture_failure_evidence
from hands.replay.inputs import InputRejected
from hands.replay.signals import EscalatedEnd, FailureEnd, OutcomeEnd, RunEnd, SuccessEnd

RESULT_DOCUMENT = "result"


def build_run_result(ctx: RunContext, end: SuccessEnd | RunEnd) -> RunResult:
    base = _base_fields(ctx)
    if isinstance(end, SuccessEnd):
        return SuccessResult(**base, outputs=dict(ctx.state.outputs))
    if isinstance(end, OutcomeEnd):
        return BusinessOutcomeResult(**base, code=end.code, message=end.message, at_step=end.step_id)
    if isinstance(end, EscalatedEnd):
        return EscalatedResult(
            **base, intervention_id=end.intervention_id, reason=end.reason, operator_note=end.operator_note
        )
    return FailedResult(**base, failure=_failure_detail(ctx, end))


def rejected_input_result(
    rejection: InputRejected,
    *,
    run_id: str,
    capability_id: str,
    capability_version: str,
    tenant_id: str | None,
    started_at: datetime,
    finished_at: datetime,
    evidence_dir: str,
) -> FailedResult:
    """Invalid input or a missing credential: nothing was touched, so there is no screen evidence."""
    return FailedResult(
        run_id=run_id,
        capability_id=capability_id,
        capability_version=capability_version,
        tenant_id=tenant_id,
        started_at=started_at,
        finished_at=finished_at,
        evidence_dir=evidence_dir,
        failure=FailureDetail(
            code="invalid_input",
            step_id=None,
            message=rejection.message,
            expected=rejection.expected,
            observed=rejection.observed,
        ),
    )


def record_result(evidence: EvidenceSink, result: RunResult) -> None:
    evidence.write_json(RESULT_DOCUMENT, result)
    evidence.event("run_finished", run_id=result.run_id, **_finish_summary(result))


def _finish_summary(result: RunResult) -> dict[str, Any]:
    summary: dict[str, Any] = {"status": result.status, "steps": len(result.steps)}
    if isinstance(result, FailedResult):
        summary.update(code=result.failure.code, step_id=result.failure.step_id, error=result.failure.message)
    if isinstance(result, BusinessOutcomeResult):
        summary.update(code=result.code, step_id=result.at_step)
    if isinstance(result, EscalatedResult):
        summary.update(intervention_id=result.intervention_id, reason=result.reason)
    return summary


def _failure_detail(ctx: RunContext, failure: FailureEnd) -> FailureDetail:
    return FailureDetail(
        code=failure.code,
        step_id=failure.step_id,
        message=failure.message,
        expected=failure.expected,
        observed=failure.observed,
        evidence=capture_failure_evidence(ctx, failure),
    )


def _base_fields(ctx: RunContext) -> dict[str, Any]:
    invocation = ctx.invocation
    steps: list[StepTrace] = list(ctx.state.traces)
    return {
        "run_id": invocation.run_id,
        "capability_id": invocation.capability.id,
        "capability_version": invocation.capability.version,
        "tenant_id": invocation.tenant_id,
        "started_at": invocation.started_at,
        "finished_at": ctx.timing.now(),
        "steps": steps,
        "interventions": list(ctx.state.interventions),
        "drift": DriftReport(fallback_steps=list(ctx.state.fallback_steps)),
        "evidence_dir": ctx.ports.evidence.run_dir,
    }
