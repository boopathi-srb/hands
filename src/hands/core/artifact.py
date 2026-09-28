"""The Capability artifact: a typed, versioned, reviewable, agent-invocable description of a UI flow.

Design rules
- Decoupled from the model transcript: no prompts, no rationales beyond per-candidate `reason`.
- Surface-agnostic: steps reference TargetSpecs and Conditions, never selectors or coordinates alone.
- No sensitive literal ever appears: sensitive inputs and credentials are only referenced as `{{name}}`.
- Runtime conditions are declared, not coded: business outcomes and recoveries are data the replay
  engine interprets, so the engine has no app-specific logic.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from hands.core.conditions import Condition
from hands.core.targets import TargetSpec

SCHEMA_VERSION = "1.0"
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
SLUG_PATTERN = r"^[a-z][a-z0-9_.-]*$"
SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"

ValueType = Literal["string", "integer", "decimal", "boolean", "date"]
Risk = Literal["safe", "risky"]


# ---------------------------------------------------------------- contract: inputs, outputs, credentials


class InputSpec(BaseModel):
    type: ValueType
    description: str
    required: bool = True
    sensitive: bool = Field(default=False, description="Masked in evidence; never stored as a literal.")
    pattern: str | None = Field(default=None, description="Regex the value must match before replay starts.")
    example: str | None = Field(default=None, description="Synthetic example for docs; never real data.")


class OutputSpec(BaseModel):
    type: ValueType
    description: str
    sensitive: bool = False


class CredentialSpec(BaseModel):
    """Resolved at replay from a CredentialProvider (vault/env), never supplied by the calling agent."""

    description: str
    fields: list[str] = Field(default_factory=lambda: ["username", "password"])


# ---------------------------------------------------------------- steps


class _StepBase(BaseModel):
    id: str = Field(pattern=SLUG_PATTERN)
    description: str
    risk: Risk = "safe"
    precondition: Condition | None = Field(default=None, description="Must hold before acting; waited for.")
    postcondition: Condition | None = Field(default=None, description="Proves the action worked; waited for.")
    timeout_ms: int = Field(default=10_000, ge=100, le=120_000)
    recoveries: list[str] = Field(default_factory=list, description="Step-local recovery rule names.")


class OpenStep(_StepBase):
    action: Literal["open"] = "open"
    entry_point: str = Field(description="URL template for web; bundle id for desktop.")


class ClickStep(_StepBase):
    action: Literal["click"] = "click"
    target: TargetSpec


class TypeStep(_StepBase):
    action: Literal["type"] = "type"
    target: TargetSpec
    value: str = Field(description="Literal or {{param}} template.")
    clear_first: bool = True


class PressStep(_StepBase):
    action: Literal["press"] = "press"
    key: str
    target: TargetSpec | None = None


class SelectStep(_StepBase):
    action: Literal["select"] = "select"
    target: TargetSpec
    option: str


class ExtractStep(_StepBase):
    action: Literal["extract"] = "extract"
    target: TargetSpec
    output: str = Field(description="Name of the declared output this step fills.")
    pattern: str | None = Field(default=None, description="Regex with one group applied to the node text.")


class WaitStep(_StepBase):
    action: Literal["wait"] = "wait"
    until: Condition


class SubflowStep(_StepBase):
    action: Literal["subflow"] = "subflow"
    subflow: str


Step = Annotated[
    OpenStep | ClickStep | TypeStep | PressStep | SelectStep | ExtractStep | WaitStep | SubflowStep,
    Field(discriminator="action"),
]


# ---------------------------------------------------------------- runtime conditions: outcomes and recoveries


class OutcomeDetector(BaseModel):
    """A legitimate business result, e.g. MEMBER_NOT_FOUND. Returned to the caller, not raised."""

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    description: str
    when: Condition
    message_target: TargetSpec | None = Field(
        default=None, description="Node whose text is returned as the outcome message."
    )
    scope: list[str] | None = Field(default=None, description="Step ids where this applies; None = all.")


class DismissResponse(BaseModel):
    kind: Literal["dismiss"] = "dismiss"
    target: TargetSpec | None = Field(default=None, description="Control to click; None = press Escape.")


class RetryResponse(BaseModel):
    kind: Literal["retry"] = "retry"
    backoff_ms: int = Field(default=1_000, ge=0, le=30_000)


class SubflowResponse(BaseModel):
    kind: Literal["subflow"] = "subflow"
    subflow: str
    then: Literal["retry_step", "restart"] = "retry_step"


class EscalateResponse(BaseModel):
    kind: Literal["escalate"] = "escalate"
    reason: str


RecoveryResponse = Annotated[
    DismissResponse | RetryResponse | SubflowResponse | EscalateResponse,
    Field(discriminator="kind"),
]


class RecoveryRule(BaseModel):
    """A known, recoverable interruption. Bounded by max_applications per run."""

    name: str = Field(pattern=SLUG_PATTERN)
    description: str
    when: Condition
    response: RecoveryResponse
    max_applications: int = Field(default=2, ge=1, le=10)
    scope: Literal["global", "step"] = "global"


# ---------------------------------------------------------------- identity and provenance


class AppRef(BaseModel):
    """What the capability was recorded against. Base capabilities key on vendor + product, not tenant."""

    vendor: str
    product: str
    product_version: str
    surface: Literal["web", "desktop"]


class Provenance(BaseModel):
    discovery_run_id: str
    recorded_at: datetime
    planner: str = Field(description="e.g. 'anthropic', 'ollama', 'scripted'")
    model: str | None = None
    recorded_on_tenant: str | None = None
    goal: str


class ReplayStats(BaseModel):
    runs: int = 0
    successes: int = 0
    business_outcomes: int = 0
    failures: int = 0
    fallback_matches: int = Field(default=0, description="Steps resolved by a non-primary candidate.")


# ---------------------------------------------------------------- the capability


class Capability(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str = Field(pattern=SLUG_PATTERN, description="Stable name the calling agent invokes.")
    version: str = Field(pattern=SEMVER_PATTERN)
    status: Literal["draft", "approved", "deprecated"] = "draft"
    title: str
    description: str = Field(description="What it does, for humans and calling agents.")
    app: AppRef
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    outputs: dict[str, OutputSpec] = Field(default_factory=dict)
    credentials: dict[str, CredentialSpec] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=1)
    checkpoint: Condition = Field(description="Success condition asserted after the last step.")
    outcomes: list[OutcomeDetector] = Field(default_factory=list)
    recoveries: list[RecoveryRule] = Field(default_factory=list)
    subflows: dict[str, list[Step]] = Field(default_factory=dict)
    provenance: Provenance
    stats: ReplayStats = Field(default_factory=ReplayStats)

    @model_validator(mode="after")
    def _validate_references(self) -> Capability:
        _check_unique_step_ids(self)
        _check_placeholders_declared(self)
        _check_outputs_filled(self)
        _check_recovery_and_subflow_names(self)
        return self


def iter_all_steps(capability: Capability) -> list[Step]:
    """Main steps followed by every subflow step."""
    subflow_steps = [step for steps in capability.subflows.values() for step in steps]
    return [*capability.steps, *subflow_steps]


def placeholders_in(text: str) -> list[str]:
    return PLACEHOLDER_PATTERN.findall(text)


def _check_unique_step_ids(capability: Capability) -> None:
    seen_ids: list[str] = []
    for step in iter_all_steps(capability):
        if step.id in seen_ids:
            raise ValueError(f"duplicate step id '{step.id}'")
        seen_ids.append(step.id)


def _check_placeholders_declared(capability: Capability) -> None:
    declared_names = set(capability.inputs) | {
        f"{credential}.{field}" for credential, spec in capability.credentials.items() for field in spec.fields
    }
    serialized_parts = [step.model_dump_json() for step in iter_all_steps(capability)]
    serialized_parts += [capability.checkpoint.model_dump_json() if hasattr(capability.checkpoint, "model_dump_json") else ""]
    serialized_parts += [detector.model_dump_json() for detector in capability.outcomes]
    serialized_parts += [rule.model_dump_json() for rule in capability.recoveries]
    for serialized in serialized_parts:
        for name in PLACEHOLDER_PATTERN.findall(serialized):
            if name not in declared_names:
                raise ValueError(f"placeholder '{{{{{name}}}}}' is not a declared input or credential field")


def _check_outputs_filled(capability: Capability) -> None:
    extracted_outputs = [step.output for step in iter_all_steps(capability) if isinstance(step, ExtractStep)]
    for output_name in extracted_outputs:
        if output_name not in capability.outputs:
            raise ValueError(f"extract step fills undeclared output '{output_name}'")
    for output_name in capability.outputs:
        if output_name not in extracted_outputs:
            raise ValueError(f"declared output '{output_name}' is never extracted")


def _check_recovery_and_subflow_names(capability: Capability) -> None:
    recovery_names = [rule.name for rule in capability.recoveries]
    for step in iter_all_steps(capability):
        for name in step.recoveries:
            if name not in recovery_names:
                raise ValueError(f"step '{step.id}' references unknown recovery '{name}'")
        if isinstance(step, SubflowStep) and step.subflow not in capability.subflows:
            raise ValueError(f"step '{step.id}' references unknown subflow '{step.subflow}'")
    for rule in capability.recoveries:
        if isinstance(rule.response, SubflowResponse) and rule.response.subflow not in capability.subflows:
            raise ValueError(f"recovery '{rule.name}' references unknown subflow '{rule.response.subflow}'")


# ---------------------------------------------------------------- tenant overlay (stored as a separate file)


class TenantOverlay(BaseModel):
    """Per-tenant specialization of a base capability. May override how steps find things,
    never which steps exist, so the base flow stays reviewable in one place."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    tenant_id: str = Field(pattern=SLUG_PATTERN)
    capability_id: str = Field(pattern=SLUG_PATTERN)
    base_version_range: str = Field(description="e.g. '>=1.0.0,<2.0.0'")
    entry_point_overrides: dict[str, str] = Field(default_factory=dict, description="step id -> entry point")
    target_overrides: dict[str, TargetSpec] = Field(default_factory=dict, description="step id -> target")
    text_aliases: dict[str, str] = Field(
        default_factory=dict, description="Base UI text -> tenant UI text, applied to all candidates/conditions."
    )
    outcome_overrides: dict[str, Condition] = Field(default_factory=dict, description="outcome code -> when")
    notes: str = ""
