"""Trace steps -> capability steps, including collapsing the sign-on block into the profile's subflow."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from hands.core.artifact import (
    ClickStep,
    ExtractStep,
    OpenStep,
    PressStep,
    Risk,
    SelectStep,
    Step,
    SubflowStep,
    TypeStep,
)
from hands.core.observation import Node
from hands.core.targets import TargetSpec
from hands.discovery.derive import (
    derive_postcondition,
    is_stable_label,
    parameterize_text,
    uses_any_placeholder,
)
from hands.discovery.render import EDITABLE_ROLES, node_display_name
from hands.discovery.trace import TraceStep
from hands.locate import build_target_spec

MAX_SLUG_CHARS = 40
LOGIN_STEP_BASE_ID = "sign_on"
_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


@dataclass
class StepIdAllocator:
    """Unique slug ids; ids already used elsewhere (e.g. profile subflows) are reserved."""

    taken: list[str] = field(default_factory=list)

    def allocate(self, base_text: str) -> str:
        base = _slug(base_text)
        candidate, suffix = base, 2
        while candidate in self.taken:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self.taken.append(candidate)
        return candidate


def _slug(text: str) -> str:
    slug = _SLUG_UNSAFE.sub("_", text.casefold()).strip("_")[:MAX_SLUG_CHARS].strip("_")
    return slug if slug[:1].isalpha() else f"step_{slug}".rstrip("_")


@dataclass
class StepBuildContext:
    input_values: Mapping[str, str]
    credential_names: Sequence[str]
    tenant_id: str | None
    login_subflow: str | None
    ids: StepIdAllocator
    warnings: list[str] = field(default_factory=list)


@dataclass
class BuiltSteps:
    steps: list[Step]
    extract_steps: list[tuple[ExtractStep, TraceStep]]
    used_subflow: str | None


def build_steps(recordable: list[TraceStep], context: StepBuildContext) -> BuiltSteps:
    login_block = find_login_block(recordable, context.credential_names) if context.login_subflow else None
    steps: list[Step] = []
    extract_steps: list[tuple[ExtractStep, TraceStep]] = []
    index = 0
    while index < len(recordable):
        if login_block is not None and index == login_block[0]:
            steps.append(_login_subflow_step(recordable[login_block[0]: login_block[1] + 1], context))
            index = login_block[1] + 1
            continue
        converted = convert_step(recordable[index], context)
        if converted is not None:
            steps.append(converted)
            if isinstance(converted, ExtractStep):
                extract_steps.append((converted, recordable[index]))
        index += 1
    return BuiltSteps(steps, extract_steps, context.login_subflow if login_block else None)


# ---------------------------------------------------------------- login block


def find_login_block(steps: Sequence[TraceStep], credential_names: Sequence[str]) -> tuple[int, int] | None:
    """(start, end) of: [open] credential typing (+ focus clicks) then the submit click/press."""
    credential_indexes = [
        index for index, step in enumerate(steps) if _types_credential(step, credential_names)
    ]
    if not credential_indexes:
        return None
    start, end = credential_indexes[0], credential_indexes[-1]
    block_is_contiguous = all(
        _types_credential(step, credential_names) or _is_focus_click(step) for step in steps[start: end + 1]
    )
    if not block_is_contiguous:
        return None
    if end + 1 < len(steps) and steps[end + 1].action in ("click", "press"):
        end += 1
    while start > 0 and _is_focus_click(steps[start - 1]):
        start -= 1
    if start > 0 and steps[start - 1].action == "open":
        start -= 1
    return start, end


def _types_credential(step: TraceStep, credential_names: Sequence[str]) -> bool:
    return step.action == "type" and uses_any_placeholder(step.value_template, credential_names)


def _is_focus_click(step: TraceStep) -> bool:
    node = step.node_before
    return step.action == "click" and node is not None and node.role.casefold() in EDITABLE_ROLES


def _login_subflow_step(block: Sequence[TraceStep], context: StepBuildContext) -> SubflowStep:
    subflow_name = context.login_subflow or ""
    return SubflowStep(
        id=context.ids.allocate(LOGIN_STEP_BASE_ID),
        description=f"Sign on with the '{subflow_name}' subflow from the app profile.",
        subflow=subflow_name,
        risk=_highest_risk(block),
        postcondition=derive_postcondition(
            block[0].observation_before, block[-1].observation_after, context.input_values, context.tenant_id
        ),
    )


def _highest_risk(steps: Sequence[TraceStep]) -> Risk:
    return "risky" if any(step.risk == "risky" for step in steps) else "safe"


# ---------------------------------------------------------------- single steps


def convert_step(step: TraceStep, context: StepBuildContext) -> Step | None:
    """One recordable trace step as a capability step; None (with a warning) when it cannot be."""
    if step.action == "open":
        return _open_step(step, context)
    if step.action == "scroll":
        context.warnings.append(f"trace step {step.index}: scroll is not a capability step; skipped")
        return None
    node = step.node_before
    if node is None and step.action != "press":
        context.warnings.append(f"trace step {step.index}: {step.action} without a target node; skipped")
        return None
    return _node_step(step, node, context)


def _common_fields(step: TraceStep, base_id: str, description: str, context: StepBuildContext) -> dict[str, object]:
    postcondition = None
    if step.action != "extract":
        postcondition = derive_postcondition(
            step.observation_before, step.observation_after, context.input_values, context.tenant_id
        )
    return {
        "id": context.ids.allocate(base_id),
        "description": description,
        "risk": step.risk,
        "postcondition": postcondition,
    }


def _open_step(step: TraceStep, context: StepBuildContext) -> OpenStep:
    entry_point = parameterize_text(step.value_template or "", context.input_values)
    fields = _common_fields(step, "open_entry_point", f"Open {entry_point}.", context)
    return OpenStep.model_validate({**fields, "entry_point": entry_point})


def _node_step(step: TraceStep, node: Node | None, context: StepBuildContext) -> Step | None:
    target = _target_for(step, node, context) if node is not None else None
    label = target.description if target is not None else "the focused element"
    decision = step.decision
    if step.action == "click" and target is not None:
        fields = _common_fields(step, f"click_{label}", f"Click {label}.", context)
        return ClickStep.model_validate({**fields, "target": target})
    if step.action == "type" and target is not None:
        value = parameterize_text(step.value_template or "", context.input_values)
        fields = _common_fields(step, f"type_{label}", f"Enter {value} into {label}.", context)
        return TypeStep.model_validate({**fields, "target": target, "value": value})
    if step.action == "select" and target is not None and decision and decision.option:
        option = parameterize_text(decision.option, context.input_values)
        fields = _common_fields(step, f"select_{label}", f"Choose {option} in {label}.", context)
        return SelectStep.model_validate({**fields, "target": target, "option": option})
    if step.action == "press" and decision and decision.key:
        fields = _common_fields(step, f"press_{decision.key}", f"Press {decision.key}.", context)
        return PressStep.model_validate({**fields, "key": decision.key, "target": target})
    if step.action == "extract" and target is not None and step.output_name:
        fields = _common_fields(step, f"read_{step.output_name}", f"Read {step.output_name}.", context)
        return ExtractStep.model_validate({**fields, "target": target, "output": step.output_name})
    context.warnings.append(f"trace step {step.index}: {step.action} is missing required details; skipped")
    return None


def _target_for(step: TraceStep, node: Node, context: StepBuildContext) -> TargetSpec:
    return build_target_spec(node, step.observation_before, target_description(step, node, context))


def target_description(step: TraceStep, node: Node, context: StepBuildContext) -> str:
    """'Member Number textbox', 'Search button'; data-like names fall back to the output or role."""
    name = node_display_name(node)
    if is_stable_label(name, context.input_values):
        return f"{name} {node.role}"
    if step.output_name:
        return f"{step.output_name.replace('_', ' ')} value"
    return node.role
