"""The single wait loop behind preconditions, target resolution, postconditions, and the checkpoint.

Each iteration: observe -> run-timeout check -> monitors (outcomes, recoveries) -> readiness check ->
deadline check -> sleep poll_interval. A recovery that handled an interruption in place (dismiss, retry,
resume) re-observes immediately and restarts the wait window, so the step's timeout is spent waiting for
the app, not on the interruption. Recoveries are bounded per run, so the loop always ends.
"""

from __future__ import annotations

from collections.abc import Callable

from hands.core.conditions import Condition
from hands.core.observation import Observation
from hands.locate import evaluate
from hands.replay.context import RunContext
from hands.replay.failures import run_timeout_failure
from hands.replay.monitors import MonitorScope, run_monitors
from hands.replay.signals import (
    Continue,
    FailureEnd,
    Readiness,
    Ready,
    TimedOut,
    WaitPhase,
    WaitResult,
)
from hands.replay.surface_io import observe

ReadinessCheck = Callable[[Observation], Readiness]


async def wait_until_ready(
    ctx: RunContext, scope: MonitorScope, check: ReadinessCheck, timeout_ms: int
) -> WaitResult:
    deadline = ctx.deadline_after(timeout_ms)
    while True:
        observation = await observe(ctx, scope.step_id)
        if isinstance(observation, FailureEnd):
            return observation
        if ctx.run_timed_out():
            return run_timeout_failure(ctx, scope.step_id)
        monitor_result = await run_monitors(ctx, scope, observation)
        if isinstance(monitor_result, Continue):
            deadline = ctx.deadline_after(timeout_ms)
            continue
        if monitor_result is not None:
            return monitor_result
        readiness = check(observation)
        if readiness.ready:
            return Ready(observation=observation, resolution=readiness.resolution)
        if ctx.timing.monotonic() >= deadline:
            return _timed_out(ctx, scope, observation, readiness)
        await ctx.timing.sleep(ctx.timing.poll_interval_ms / 1000)


def condition_check(ctx: RunContext, condition: Condition, phase: WaitPhase) -> ReadinessCheck:
    """Readiness = the (templated, aliased) condition holds."""
    templated = ctx.condition(condition)

    def check(observation: Observation) -> Readiness:
        result = evaluate(templated, observation)
        return Readiness(ready=result.met, phase=phase, detail=result.detail)

    return check


def _timed_out(ctx: RunContext, scope: MonitorScope, observation: Observation, readiness: Readiness) -> WaitResult:
    if ctx.run_timed_out():
        return run_timeout_failure(ctx, scope.step_id)
    return TimedOut(observation=observation, readiness=readiness)
