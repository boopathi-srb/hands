"""The surface I/O boundary. Surfaces must not raise for UI errors, but infrastructure can still fail
(a crashed browser, a lost AX connection); those exceptions stop here and become typed failures."""

from __future__ import annotations

from hands.core.actions import Action, ActResult, ActTarget
from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.replay.context import RunContext
from hands.replay.signals import FailureEnd

_logger = get_logger(__name__)


async def observe(ctx: RunContext, step_id: str | None) -> Observation | FailureEnd:
    """Observe the surface and remember the observation for failure evidence."""
    try:
        observation = await ctx.ports.surface.observe(include_screenshot=True)
    except Exception as surface_error:  # noqa: BLE001 - adapter boundary, converted to a typed failure
        log_failure(_logger, "replay.observe", f"surface observe raised: {surface_error!r}", step_id=step_id)
        return FailureEnd(
            code="surface_error",
            step_id=step_id,
            message=f"surface observe failed: {surface_error!r}",
            expected="the surface returns an observation",
            observed=type(surface_error).__name__,
        )
    ctx.state.last_observation = observation
    return observation


async def act(ctx: RunContext, step_id: str | None, target: ActTarget, action: Action) -> ActResult | FailureEnd:
    """Perform one action; an exception from the adapter is a surface_error, not an action_failed."""
    try:
        return await ctx.ports.surface.act(target, action)
    except Exception as surface_error:  # noqa: BLE001 - adapter boundary, converted to a typed failure
        log_failure(
            _logger, "replay.act", f"surface act raised: {surface_error!r}",
            step_id=step_id, action_kind=action.kind,
        )
        return FailureEnd(
            code="surface_error",
            step_id=step_id,
            message=f"surface act failed: {surface_error!r}",
            expected=f"the surface performs {action.kind}",
            observed=type(surface_error).__name__,
        )
