"""Run-level flow: the main step sequence, restarts requested by recoveries, then the checkpoint."""

from __future__ import annotations

from hands.replay.checkpoint import verify_checkpoint
from hands.replay.context import RunContext
from hands.replay.failures import describe_observation
from hands.replay.signals import (
    FailureEnd,
    RestartRun,
    RunEnd,
    SequenceCompleted,
    SequenceResult,
    SuccessEnd,
)
from hands.replay.steps import run_sequence


def bind_subflows(ctx: RunContext) -> None:
    """Let monitors and subflow steps run named subflows through the same step executor."""

    async def run_named_subflow(name: str) -> SequenceResult:
        ctx.emit("subflow_started", subflow=name)
        subflow_result = await run_sequence(ctx, ctx.capability.subflows[name])
        ctx.emit("subflow_finished", subflow=name, completed=isinstance(subflow_result, SequenceCompleted))
        return subflow_result

    ctx.subflow_runner = run_named_subflow


async def run_capability(ctx: RunContext, max_restarts: int) -> SuccessEnd | RunEnd:
    while True:
        run_end = await _run_once(ctx)
        if not isinstance(run_end, RestartRun):
            return run_end
        restart_refusal = _begin_restart(ctx, run_end, max_restarts)
        if restart_refusal is not None:
            return restart_refusal


async def _run_once(ctx: RunContext) -> SuccessEnd | RestartRun | RunEnd:
    sequence_result = await run_sequence(ctx, ctx.capability.steps)
    if not isinstance(sequence_result, SequenceCompleted):
        return sequence_result
    return await verify_checkpoint(ctx)


def _begin_restart(ctx: RunContext, restart: RestartRun, max_restarts: int) -> FailureEnd | None:
    ctx.state.restarts += 1
    if ctx.state.restarts > max_restarts:
        return FailureEnd(
            code="recovery_exhausted",
            step_id=None,
            message=f"run restarted {ctx.state.restarts} times; the limit is {max_restarts}",
            expected=f"at most {max_restarts} restart(s)",
            observed=describe_observation(ctx.state.last_observation),
        )
    ctx.state.outputs.clear()
    ctx.emit("run_restarted", reason=restart.reason, restarts=ctx.state.restarts)
    return None
