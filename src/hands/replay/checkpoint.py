"""After the last step: wait (with monitors) for the capability's checkpoint, the proof of success."""

from __future__ import annotations

from hands.replay.context import RunContext
from hands.replay.failures import timeout_failure
from hands.replay.monitors import MonitorScope
from hands.replay.signals import (
    Continue,
    HumanCompleted,
    Ready,
    RestartRun,
    RetryStep,
    RunEnd,
    SuccessEnd,
    TimedOut,
    WaitResult,
)
from hands.replay.waits import condition_check, wait_until_ready

CHECKPOINT_TRACE_ID = "checkpoint"


async def verify_checkpoint(ctx: RunContext) -> SuccessEnd | RestartRun | RunEnd:
    tracker = ctx.start_tracker(CHECKPOINT_TRACE_ID)
    scope = MonitorScope(step=None, tracker=tracker)
    check = condition_check(ctx, ctx.capability.checkpoint, "checkpoint")
    timeout_ms = ctx.timing.checkpoint_timeout_ms
    waited: WaitResult = RetryStep(reason="first check")
    while isinstance(waited, RetryStep | Continue):
        waited = await wait_until_ready(ctx, scope, check, timeout_ms)
    if tracker.recoveries_applied:
        ctx.finish_tracker(tracker, "recovered")
    if isinstance(waited, Ready | HumanCompleted):
        ctx.emit("checkpoint", step_id=None, check="checkpoint", ok=True)
        return SuccessEnd()
    if isinstance(waited, TimedOut):
        failure = timeout_failure(None, waited, timeout_ms)
        ctx.emit("checkpoint", step_id=None, check="checkpoint", ok=False, expected=failure.expected)
        return failure
    return waited
