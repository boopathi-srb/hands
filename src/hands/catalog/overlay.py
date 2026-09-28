"""Apply a TenantOverlay to a base Capability, producing the effective capability for one tenant.

An overlay may change how steps find things (entry points, targets, outcome conditions) and carries text
aliases that the replay engine applies at resolution time. It never adds, removes, or reorders steps.
Every problem (id mismatch, version out of range, unknown step id or outcome code, override on a step that
has no such field) is returned as an error result, never raised.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from hands.catalog.store import ArtifactStore
from hands.catalog.versions import satisfies_range
from hands.core.artifact import (
    Capability,
    OpenStep,
    OutcomeDetector,
    Step,
    TenantOverlay,
    iter_all_steps,
)
from hands.core.log import get_logger, log_failure

_logger = get_logger(__name__)


class OverlayResult(BaseModel):
    """The effective capability plus the aliases the engine must apply, or an error."""

    capability: Capability | None = None
    aliases: dict[str, str] = Field(default_factory=dict)
    tenant_id: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.capability is not None


def apply_overlay(capability: Capability, overlay: TenantOverlay) -> OverlayResult:
    """Validate the overlay against the capability, then apply its overrides."""
    compatibility_error = overlay_compatibility_error(capability, overlay)
    if compatibility_error is not None:
        return _overlay_error("apply_overlay", compatibility_error, capability, overlay)
    reference_error = overlay_reference_error(capability, overlay)
    if reference_error is not None:
        return _overlay_error("apply_overlay", reference_error, capability, overlay)
    effective = _rebuild(capability, overlay)
    if isinstance(effective, str):
        return _overlay_error("apply_overlay", effective, capability, overlay)
    return OverlayResult(capability=effective, aliases=dict(overlay.text_aliases), tenant_id=overlay.tenant_id)


def load_for_tenant(
    store: ArtifactStore, capability_id: str, tenant_id: str | None, version: str | None = None
) -> OverlayResult:
    """Load a capability and, when the tenant has an overlay, apply it. No overlay = the base capability."""
    loaded = store.load(capability_id, version)
    if loaded.capability is None:
        return OverlayResult(tenant_id=tenant_id, error=loaded.error)
    if tenant_id is None:
        return OverlayResult(capability=loaded.capability)
    overlay_load = store.load_overlay(capability_id, tenant_id)
    if overlay_load.status == "absent":
        return OverlayResult(capability=loaded.capability, tenant_id=tenant_id)
    if overlay_load.overlay is None:
        return OverlayResult(tenant_id=tenant_id, error=overlay_load.error)
    return apply_overlay(loaded.capability, overlay_load.overlay)


# ---------------------------------------------------------------- checks


def overlay_compatibility_error(capability: Capability, overlay: TenantOverlay) -> str | None:
    """Does the overlay target this capability id and version?"""
    if overlay.capability_id != capability.id:
        return f"overlay is for capability '{overlay.capability_id}', not '{capability.id}'"
    range_check = satisfies_range(capability.version, overlay.base_version_range)
    if range_check.error is not None:
        return f"overlay base_version_range '{overlay.base_version_range}' is invalid: {range_check.error}"
    if not range_check.satisfied:
        return (
            f"capability version {capability.version} is outside the overlay's "
            f"base_version_range '{overlay.base_version_range}'"
        )
    return None


def overlay_reference_error(capability: Capability, overlay: TenantOverlay) -> str | None:
    """Every overridden step id and outcome code must exist and support the override."""
    steps_by_id = {step.id: step for step in iter_all_steps(capability)}
    for step_id in overlay.entry_point_overrides:
        step = steps_by_id.get(step_id)
        if step is None:
            return f"entry_point_overrides names unknown step id '{step_id}'"
        if not isinstance(step, OpenStep):
            return f"entry_point_overrides names step '{step_id}', which is a '{step.action}' step, not 'open'"
    for step_id in overlay.target_overrides:
        step = steps_by_id.get(step_id)
        if step is None:
            return f"target_overrides names unknown step id '{step_id}'"
        if not hasattr(step, "target"):
            return f"target_overrides names step '{step_id}', which is a '{step.action}' step without a target"
    known_codes = [detector.code for detector in capability.outcomes]
    for code in overlay.outcome_overrides:
        if code not in known_codes:
            return f"outcome_overrides names unknown outcome code '{code}'"
    return None


# ---------------------------------------------------------------- rebuilding


def _rebuild(capability: Capability, overlay: TenantOverlay) -> Capability | str:
    overridden_steps = [_override_step(step, overlay) for step in capability.steps]
    overridden_subflows = {
        name: [_override_step(step, overlay) for step in steps] for name, steps in capability.subflows.items()
    }
    overridden_outcomes = [_override_outcome(detector, overlay) for detector in capability.outcomes]
    updated = capability.model_copy(
        update={"steps": overridden_steps, "subflows": overridden_subflows, "outcomes": overridden_outcomes}
    )
    return _revalidate(updated)


def _override_step(step: Step, overlay: TenantOverlay) -> Step:
    changes: dict[str, object] = {}
    if step.id in overlay.entry_point_overrides:
        changes["entry_point"] = overlay.entry_point_overrides[step.id]
    if step.id in overlay.target_overrides:
        changes["target"] = overlay.target_overrides[step.id]
    return step.model_copy(update=changes) if changes else step


def _override_outcome(detector: OutcomeDetector, overlay: TenantOverlay) -> OutcomeDetector:
    replacement = overlay.outcome_overrides.get(detector.code)
    return detector if replacement is None else detector.model_copy(update={"when": replacement})


def _revalidate(capability: Capability) -> Capability | str:
    """model_copy skips validation; round-trip so an overlay can never yield an invalid capability."""
    try:
        return Capability.model_validate(capability.model_dump(mode="json"))
    except ValidationError as validation_error:
        log_failure(_logger, "apply_overlay", "effective capability is invalid", capability_id=capability.id)
        return f"effective capability failed validation: {validation_error}"


def _overlay_error(
    function_name: str, message: str, capability: Capability, overlay: TenantOverlay
) -> OverlayResult:
    log_failure(
        _logger,
        function_name,
        message,
        capability_id=capability.id,
        capability_version=capability.version,
        tenant_id=overlay.tenant_id,
    )
    return OverlayResult(tenant_id=overlay.tenant_id, error=message)
