"""Semantic checks on run requests, each returning a typed ApiError instead of raising."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hands.api.models import DiscoveryStartBody, FaultRequest, ReplayStartBody
from hands.catalog import ArtifactStore
from hands.runtime.planners import PlannerChoice
from target_app.faults import FaultName
from target_app.tenants import TENANTS

PLANNER_NAMES: tuple[PlannerChoice, ...] = ("anthropic", "ollama", "scripted")


@dataclass(frozen=True)
class ApiError:
    status_code: int
    code: str
    message: str
    extra: dict[str, object] = field(default_factory=dict)


def check_tenant(tenant: str | None) -> ApiError | None:
    if tenant is None or tenant in TENANTS:
        return None
    return ApiError(400, "unknown_tenant", f"unknown tenant '{tenant}'; known: {sorted(TENANTS)}")


def check_faults(faults: list[FaultRequest]) -> ApiError | None:
    known_faults = {fault.value for fault in FaultName}
    unknown = [fault.name for fault in faults if fault.name not in known_faults]
    if not unknown:
        return None
    return ApiError(400, "unknown_fault", f"unknown fault(s) {unknown}; known: {sorted(known_faults)}")


def check_capability(artifacts_dir: Path, capability_id: str, version: str | None) -> ApiError | None:
    loaded = ArtifactStore(artifacts_dir).load(capability_id, version)
    if loaded.capability is not None:
        return None
    return ApiError(404, "unknown_capability", loaded.error or f"unknown capability '{capability_id}'")


def check_planner(planner: str, anthropic_key_present: bool) -> ApiError | None:
    if planner not in PLANNER_NAMES:
        return ApiError(400, "unknown_planner", f"unknown planner '{planner}'; known: {list(PLANNER_NAMES)}")
    if planner == "anthropic" and not anthropic_key_present:
        return ApiError(400, "planner_unavailable", "planner 'anthropic' needs ANTHROPIC_API_KEY on the server")
    return None


def check_sensitive_inputs(body: DiscoveryStartBody) -> ApiError | None:
    undeclared = [name for name in body.sensitive_inputs if name not in body.inputs]
    if not undeclared:
        return None
    return ApiError(400, "unknown_input", f"sensitive_inputs {undeclared} are not in inputs")


def validate_replay(body: ReplayStartBody, artifacts_dir: Path) -> ApiError | None:
    """First problem with a replay request, or None."""
    return (check_tenant(body.tenant) or check_faults(body.faults)
            or check_capability(artifacts_dir, body.capability_id, body.version))


def validate_discovery(body: DiscoveryStartBody, anthropic_key_present: bool) -> ApiError | None:
    """First problem with a discovery request, or None."""
    return (check_tenant(body.tenant) or check_planner(body.planner, anthropic_key_present)
            or check_sensitive_inputs(body))
