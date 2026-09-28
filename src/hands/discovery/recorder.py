"""record_capability: turn a completed discovery trace into a typed, validated Capability (draft).

Heuristics (see derive.py and recorder_steps.py):
- one capability step per successful acting trace step; targets from `build_target_spec` on the
  observation the step acted on
- typed literals equal to a declared input's run value become `{{input}}`; credential placeholders stay
- location conditions use canonical paths ('/member/10001' -> '/member/:member_number')
- postconditions: location change, else a distinctive new label, else none
- the sign-on block collapses into the profile's login subflow when the profile has one
- extract decisions become ExtractSteps plus typed OutputSpecs
- checkpoint: all_of(final location, node_present for every extract target)
- the profile's credentials, subflows, outcomes and recoveries are merged in
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field, ValidationError

from hands.catalog.profile_merge import merge_profile
from hands.core.artifact import (
    AppRef,
    Capability,
    CredentialSpec,
    InputSpec,
    OutputSpec,
    Provenance,
    Step,
    iter_all_steps,
    placeholders_in,
)
from hands.core.conditions import AllOf, Condition, LocationMatches, NodePresent, TextVisible
from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.discovery.derive import canonical_path, distinctive_new_text, infer_value_type
from hands.discovery.recorder_steps import (
    BuiltSteps,
    StepBuildContext,
    StepIdAllocator,
    build_steps,
)
from hands.discovery.trace import DiscoveryOutcome
from hands.profiles import AppProfile

_logger = get_logger(__name__)

CAPABILITY_VERSION = "1.0.0"


class RecordResult(BaseModel):
    capability: Capability | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.capability is not None


def record_capability(
    outcome: DiscoveryOutcome,
    *,
    capability_id: str,
    title: str,
    description: str,
    app: AppRef,
    inputs: dict[str, InputSpec],
    profile: AppProfile | None,
    planner_name: str,
    model: str | None,
    tenant_id: str | None = None,
    recorded_at: datetime | None = None,
) -> RecordResult:
    """A draft Capability from a completed discovery, or an error result explaining why not."""
    problem = _unrecordable_reason(outcome)
    if problem is not None:
        log_failure(_logger, "record_capability", problem, run_id=outcome.run_id, status=outcome.status)
        return RecordResult(error=problem)
    input_values = _declared_input_values(outcome, inputs)
    context = _step_context(outcome, input_values, profile, tenant_id)
    built = build_steps([step for step in outcome.trace if step.is_recordable], context)
    warnings = [*_trace_warnings(outcome, inputs), *context.warnings]
    if not built.steps:
        return _error_result("no recordable steps in the trace", outcome, warnings)
    checkpoint = derive_checkpoint(_final_observation(outcome), built, input_values, tenant_id, warnings)
    payload = {
        "id": capability_id,
        "version": CAPABILITY_VERSION,
        "status": "draft",
        "title": title,
        "description": description,
        "app": app,
        "inputs": inputs,
        "outputs": derive_outputs(built),
        "credentials": _credentials_for(built.steps, profile),
        "steps": built.steps,
        "checkpoint": checkpoint,
        "subflows": _subflows_for(built, profile),
        "provenance": Provenance(
            discovery_run_id=outcome.run_id, recorded_at=recorded_at or datetime.now(UTC),
            planner=planner_name, model=model, recorded_on_tenant=tenant_id, goal=outcome.goal,
        ),
    }
    return _validated_result(payload, profile, outcome, warnings)


# ---------------------------------------------------------------- preconditions and context


def _unrecordable_reason(outcome: DiscoveryOutcome) -> str | None:
    if not outcome.trace:
        return "the discovery trace is empty"
    if outcome.status != "completed":
        return f"discovery did not complete (status {outcome.status}: {outcome.reason})"
    return None


def _declared_input_values(outcome: DiscoveryOutcome, inputs: Mapping[str, InputSpec]) -> dict[str, str]:
    return {name: outcome.input_values[name] for name in inputs if outcome.input_values.get(name)}


def _step_context(
    outcome: DiscoveryOutcome, input_values: dict[str, str], profile: AppProfile | None, tenant_id: str | None
) -> StepBuildContext:
    login_subflow = profile.login_subflow if profile and profile.login_subflow in profile.subflows else None
    reserved_ids = [step.id for steps in (profile.subflows.values() if profile else []) for step in steps]
    return StepBuildContext(
        input_values=input_values, credential_names=outcome.credential_names, tenant_id=tenant_id,
        login_subflow=login_subflow, ids=StepIdAllocator(taken=reserved_ids),
    )


def _trace_warnings(outcome: DiscoveryOutcome, inputs: Mapping[str, InputSpec]) -> list[str]:
    warnings = [
        f"trace step {step.index}: a human acted ({step.human_summary}); not captured as steps, review"
        for step in outcome.trace if step.action == "human"
    ]
    warnings += [f"declared input '{name}' had no value in the discovery run"
                 for name in inputs if not outcome.input_values.get(name)]
    return warnings


def _final_observation(outcome: DiscoveryOutcome) -> Observation | None:
    if outcome.final_observation is not None:
        return outcome.final_observation
    return next((step.observation_after for step in reversed(outcome.trace) if step.observation_after), None)


# ---------------------------------------------------------------- outputs, checkpoint, credentials


def derive_outputs(built: BuiltSteps) -> dict[str, OutputSpec]:
    outputs: dict[str, OutputSpec] = {}
    for extract_step, trace_step in built.extract_steps:
        sample = trace_step.extracted_value or ""
        outputs[extract_step.output] = OutputSpec(
            type=infer_value_type(sample),
            description=f"Read from {extract_step.target.description} during discovery.",
        )
    return outputs


def derive_checkpoint(
    final_observation: Observation | None,
    built: BuiltSteps,
    input_values: Mapping[str, str],
    tenant_id: str | None,
    warnings: list[str],
) -> Condition:
    conditions: list[Condition] = []
    final_path = canonical_path(final_observation.location, input_values, tenant_id) if final_observation else None
    if final_path:
        conditions.append(LocationMatches(pattern=final_path))
    conditions += [NodePresent(target=extract_step.target) for extract_step, _trace in built.extract_steps]
    if conditions:
        return AllOf(conditions=conditions)
    return _fallback_checkpoint(final_observation, input_values, warnings)


def _fallback_checkpoint(
    final_observation: Observation | None, input_values: Mapping[str, str], warnings: list[str]
) -> Condition:
    label = None
    if final_observation is not None:
        empty_screen = final_observation.model_copy(update={"nodes": [], "dialogs": []})
        label = distinctive_new_text(empty_screen, final_observation, input_values)
    if label:
        return AllOf(conditions=[TextVisible(pattern=label)])
    warnings.append("no checkpoint could be derived; using a trivially met location check, review")
    return AllOf(conditions=[LocationMatches()])


def _credentials_for(steps: Sequence[Step], profile: AppProfile | None) -> dict[str, CredentialSpec]:
    """Profile credentials, plus any credential the steps use that the profile does not declare."""
    credentials = dict(profile.credentials) if profile else {}
    used_fields: dict[str, list[str]] = {}
    for step in steps:
        for name in placeholders_in(step.model_dump_json()):
            if "." in name:
                credential, field_name = name.split(".", 1)
                fields = used_fields.setdefault(credential, [])
                if field_name not in fields:
                    fields.append(field_name)
    for credential, fields in used_fields.items():
        if credential not in credentials:
            credentials[credential] = CredentialSpec(
                description=f"Credential '{credential}' used during discovery.", fields=fields
            )
    return credentials


def _subflows_for(built: BuiltSteps, profile: AppProfile | None) -> dict[str, list[Step]]:
    if built.used_subflow is None or profile is None:
        return {}
    return {built.used_subflow: list(profile.subflows[built.used_subflow])}


# ---------------------------------------------------------------- validation and merge


def _validated_result(
    payload: dict[str, object], profile: AppProfile | None, outcome: DiscoveryOutcome, warnings: list[str]
) -> RecordResult:
    try:
        capability = Capability.model_validate(payload)
    except ValidationError as validation_error:
        return _error_result(f"recorded capability is invalid: {validation_error}", outcome, warnings)
    if profile is not None:
        capability = merge_profile(capability, profile)
    warnings += _unused_input_warnings(capability)
    return RecordResult(capability=capability, warnings=warnings)


def _unused_input_warnings(capability: Capability) -> list[str]:
    serialized = " ".join(step.model_dump_json() for step in iter_all_steps(capability))
    used_names = set(placeholders_in(serialized))
    return [f"declared input '{name}' is never used by a step" for name in capability.inputs
            if name not in used_names]


def _error_result(message: str, outcome: DiscoveryOutcome, warnings: list[str]) -> RecordResult:
    log_failure(_logger, "record_capability", message, run_id=outcome.run_id)
    return RecordResult(error=message, warnings=warnings)

