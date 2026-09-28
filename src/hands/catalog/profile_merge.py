"""Merge a vendor AppProfile's runtime knowledge into a capability. Pure; the capability always wins.

Adds the profile's credentials, subflows, outcome detectors and recovery rules that the capability does not
already declare (by name / code). Anything that would make the capability invalid is skipped and logged:
a subflow whose step ids collide with existing steps, or a recovery rule whose subflow is not available.
"""

from __future__ import annotations

from pydantic import ValidationError

from hands.core.artifact import (
    Capability,
    CredentialSpec,
    OutcomeDetector,
    RecoveryRule,
    Step,
    SubflowResponse,
    iter_all_steps,
)
from hands.core.log import get_logger, log_failure
from hands.profiles import AppProfile

_logger = get_logger(__name__)


def merge_profile(capability: Capability, profile: AppProfile) -> Capability:
    """The capability plus everything from the profile it does not already declare."""
    if not _same_product(capability, profile):
        log_failure(
            _logger,
            "merge_profile",
            "profile is for a different vendor/product; capability returned unchanged",
            capability_id=capability.id,
            profile_product=f"{profile.vendor}/{profile.product}",
        )
        return capability
    merged_subflows = merged_subflows_for(capability, profile)
    merged = capability.model_copy(
        update={
            "credentials": merged_credentials(capability.credentials, profile.credentials),
            "subflows": merged_subflows,
            "outcomes": merged_outcomes(capability.outcomes, profile.outcomes),
            "recoveries": merged_recoveries(capability.recoveries, profile.recoveries, merged_subflows),
        }
    )
    return _validated_or_original(merged, capability)


def merged_credentials(
    own: dict[str, CredentialSpec], from_profile: dict[str, CredentialSpec]
) -> dict[str, CredentialSpec]:
    return {**from_profile, **own}


def merged_subflows_for(capability: Capability, profile: AppProfile) -> dict[str, list[Step]]:
    merged = dict(capability.subflows)
    taken_step_ids = [step.id for step in iter_all_steps(capability)]
    for name, steps in profile.subflows.items():
        if name in merged:
            continue
        colliding_ids = [step.id for step in steps if step.id in taken_step_ids]
        if colliding_ids:
            log_failure(
                _logger, "merge_profile", "profile subflow skipped: step ids collide",
                subflow=name, step_ids=colliding_ids,
            )
            continue
        merged[name] = list(steps)
        taken_step_ids.extend(step.id for step in steps)
    return merged


def merged_outcomes(
    own: list[OutcomeDetector], from_profile: list[OutcomeDetector]
) -> list[OutcomeDetector]:
    own_codes = [detector.code for detector in own]
    return [*own, *(detector for detector in from_profile if detector.code not in own_codes)]


def merged_recoveries(
    own: list[RecoveryRule], from_profile: list[RecoveryRule], subflows: dict[str, list[Step]]
) -> list[RecoveryRule]:
    own_names = [rule.name for rule in own]
    added: list[RecoveryRule] = []
    for rule in from_profile:
        if rule.name in own_names:
            continue
        if isinstance(rule.response, SubflowResponse) and rule.response.subflow not in subflows:
            log_failure(
                _logger, "merge_profile", "profile recovery skipped: its subflow is unavailable",
                recovery=rule.name, subflow=rule.response.subflow,
            )
            continue
        added.append(rule)
    return [*own, *added]


def _same_product(capability: Capability, profile: AppProfile) -> bool:
    return (
        capability.app.vendor.casefold() == profile.vendor.casefold()
        and capability.app.product.casefold() == profile.product.casefold()
    )


def _validated_or_original(merged: Capability, original: Capability) -> Capability:
    try:
        return Capability.model_validate(merged.model_dump(mode="json"))
    except ValidationError as validation_error:
        log_failure(
            _logger, "merge_profile", f"merged capability is invalid; returned unchanged: {validation_error}",
            capability_id=original.id,
        )
        return original
