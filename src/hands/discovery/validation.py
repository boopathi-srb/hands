"""Validate a PlannerDecision against the live observation and turn it into a surface action.

The model is never trusted: refs must exist on the current screen, required fields must be present,
placeholders must be known, and a literal credential value is refused outright (the model must use
the placeholder). A rejection carries feedback written for the model to read on its next turn.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hands.core.actions import (
    Action,
    ClickAction,
    OpenAction,
    PressAction,
    ScrollAction,
    SelectAction,
    TypeAction,
)
from hands.core.artifact import placeholders_in
from hands.core.observation import Node, Observation
from hands.discovery.credentials import SecretBook, placeholder
from hands.discovery.planner import PLANNER_ACTIONS, PlannerDecision
from hands.discovery.render import EDITABLE_ROLES, node_display_name
from hands.locate import fill_placeholders

OUTPUT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
NODE_ACTIONS = frozenset({"click", "type", "select", "extract"})
ENABLED_REQUIRED_ACTIONS = frozenset({"click", "type", "select"})
DEFAULT_ALLOWED_ACTIONS: frozenset[str] = frozenset(PLANNER_ACTIONS)


class ValidatedDecision(BaseModel):
    """A decision that may be executed. `surface_action` may hold a resolved secret: never store it."""

    model_config = ConfigDict(frozen=True)

    decision: PlannerDecision
    node: Node | None = None
    value_template: str | None = None
    surface_action: Action | None = None


class DecisionRejection(BaseModel):
    feedback: str


ValidationOutcome = ValidatedDecision | DecisionRejection


@dataclass(frozen=True)
class ValidationInputs:
    """What validation needs besides the decision: current screen, params and secrets."""

    observation: Observation
    input_values: Mapping[str, str]
    secrets: SecretBook
    allowed_actions: Collection[str] = DEFAULT_ALLOWED_ACTIONS


def validate_decision(decision: PlannerDecision, inputs: ValidationInputs) -> ValidationOutcome:
    """Check one decision; return the executable form or feedback for the model."""
    if decision.action not in inputs.allowed_actions:
        return _reject(f"action '{decision.action}' is not allowed here")
    node_check = _resolve_node(decision, inputs.observation)
    if isinstance(node_check, DecisionRejection):
        return node_check
    field_problem = _missing_field_problem(decision, node_check)
    if field_problem is not None:
        return _reject(field_problem)
    if decision.action in ("open", "type"):
        return _with_resolved_value(decision, node_check, inputs)
    return ValidatedDecision(
        decision=decision, node=node_check, surface_action=_plain_surface_action(decision)
    )


def normalize_ref(raw_ref: str, observation: Observation) -> Node | None:
    """Find a node by ref, tolerating '[n12]', ' n12 ', and a bare '12' from small models."""
    cleaned = raw_ref.strip().strip("[]").strip()
    for candidate_ref in (cleaned, f"n{cleaned}"):
        node = observation.node_by_ref(candidate_ref)
        if node is not None:
            return node
    return None


def _reject(feedback: str) -> DecisionRejection:
    return DecisionRejection(feedback=feedback)


def _resolve_node(decision: PlannerDecision, observation: Observation) -> Node | None | DecisionRejection:
    if decision.node_ref is None:
        if decision.action in NODE_ACTIONS:
            return _reject(f"action '{decision.action}' needs node_ref from the current SCREEN")
        return None
    node = normalize_ref(decision.node_ref, observation)
    if node is None:
        return _reject(f"node_ref '{decision.node_ref}' is not on the current SCREEN; use a listed ref")
    if decision.action in ENABLED_REQUIRED_ACTIONS and not node.enabled:
        return _reject(f"[{node.ref}] is disabled; choose another element")
    return node


def _missing_field_problem(decision: PlannerDecision, node: Node | None) -> str | None:
    action = decision.action
    if action in ("type", "open") and decision.value is None:
        return f"action '{action}' needs a value"
    if action == "type" and node is not None and node.role.casefold() not in EDITABLE_ROLES:
        return f"[{node.ref}] is a {node.role}, not a text field; type into a textbox"
    if action == "select" and decision.option is None:
        return "action 'select' needs option (the visible option text)"
    if action == "press" and decision.key is None:
        return "action 'press' needs key, e.g. Enter"
    if action == "extract":
        return _extract_problem(decision, node)
    return None


def _extract_problem(decision: PlannerDecision, node: Node | None) -> str | None:
    if decision.output_name is None or not OUTPUT_NAME_PATTERN.match(decision.output_name):
        return "action 'extract' needs output_name in snake_case, e.g. savings_balance"
    if node is not None and not (node_display_name(node) or node.value):
        return f"[{node.ref}] shows no text to extract"
    return None


def _with_resolved_value(
    decision: PlannerDecision, node: Node | None, inputs: ValidationInputs
) -> ValidationOutcome:
    template = decision.value or ""
    if inputs.secrets.contains_secret(template):
        names = ", ".join(inputs.secrets.placeholders)
        return _reject(f"never type credential values; type the placeholder instead ({names})")
    params = {**inputs.input_values, **inputs.secrets.params}
    unknown_names = [name for name in placeholders_in(template) if name not in params]
    if unknown_names:
        known = ", ".join(placeholder(name) for name in params) or "none"
        return _reject(f"unknown placeholder {placeholder(unknown_names[0])}; available: {known}")
    resolved_text = fill_placeholders(template, params).text
    surface_action: Action = (
        OpenAction(entry_point=resolved_text) if decision.action == "open"
        else TypeAction(text=resolved_text)
    )
    return ValidatedDecision(
        decision=decision, node=node, value_template=template, surface_action=surface_action
    )


def _plain_surface_action(decision: PlannerDecision) -> Action | None:
    """Surface action for click/press/select/scroll; None for extract (no surface action)."""
    if decision.action == "click":
        return ClickAction()
    if decision.action == "press":
        return PressAction(key=decision.key or "Enter")
    if decision.action == "select":
        return SelectAction(option=decision.option or "")
    if decision.action == "scroll":
        direction: Literal["up", "down"] = (
            "up" if (decision.value or "").strip().casefold() == "up" else "down"
        )
        return ScrollAction(direction=direction)
    return None
