"""Turn artifact steps into surface-neutral actions and act targets."""

from __future__ import annotations

from typing import Any

from hands.core.actions import (
    Action,
    ActTarget,
    ClickAction,
    NodeRef,
    OpenAction,
    PressAction,
    SelectAction,
    TypeAction,
)
from hands.core.artifact import ClickStep, OpenStep, PressStep, SelectStep, Step, TypeStep
from hands.locate import Resolution
from hands.replay.context import RunContext

ActingStep = OpenStep | ClickStep | TypeStep | PressStep | SelectStep
ACTING_STEP_TYPES = (OpenStep, ClickStep, TypeStep, PressStep, SelectStep)


def is_acting_step(step: Step) -> bool:
    return isinstance(step, ACTING_STEP_TYPES)


def action_for_step(ctx: RunContext, step: ActingStep) -> Action:
    """The concrete action for a step with inputs, credentials, and tenant aliases applied."""
    if isinstance(step, OpenStep):
        return OpenAction(entry_point=ctx.data_text(step.entry_point))
    if isinstance(step, TypeStep):
        return TypeAction(text=ctx.data_text(step.value), clear_first=step.clear_first)
    if isinstance(step, PressStep):
        return PressAction(key=step.key)
    if isinstance(step, SelectStep):
        return SelectAction(option=ctx.ui_text(step.option))
    return ClickAction()


def act_target_for(resolution: Resolution | None) -> ActTarget:
    """NodeRef for a matched node; the computed Point for visual anchors or node-less matches."""
    if resolution is None:
        return None
    if resolution.candidate_kind == "visual_anchor" or resolution.node is None:
        return resolution.point
    return NodeRef(ref=resolution.node.ref)


def describe_action(action: Action) -> dict[str, Any]:
    """Action fields for evidence; typed text is reduced to its length so secrets never leave memory."""
    described = action.model_dump(mode="json")
    if isinstance(action, TypeAction):
        described.pop("text", None)
        described["text_length"] = len(action.text)
    return described
