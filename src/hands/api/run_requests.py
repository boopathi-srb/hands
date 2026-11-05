"""Translate validated API bodies into the runtime's ReplayRequest / DiscoverRequest for one run id."""

from __future__ import annotations

from typing import cast

from hands.api.models import DiscoveryStartBody, FaultRequest, ReplayStartBody
from hands.api.settings import ApiSettings
from hands.runtime.assembly import EscalationMode, RunMode, SessionOptions
from hands.runtime.commands import DiscoverRequest, ReplayRequest
from hands.runtime.planners import PlannerChoice
from hands.runtime.shared_console import SharedConsole

DEFAULT_TENANT = "lakeside"


def session_options(
    settings: ApiSettings, mode: RunMode, run_id: str, tenant: str | None, escalation: EscalationMode,
    shared_console: SharedConsole, risky_confirmed: bool = False,
) -> SessionOptions:
    return SessionOptions(
        mode=mode, run_id=run_id, evidence_root=settings.evidence_root, policy_path=settings.policy_path,
        surface=settings.surface, headless=settings.headless, escalation=escalation,
        escalation_timeout_s=settings.escalation_timeout_s, risky_confirmed=risky_confirmed,
        fake_tenant=tenant or DEFAULT_TENANT, fake_base_url=settings.target_url, shared_console=shared_console,
    )


def fault_specs(faults: list[FaultRequest]) -> list[str]:
    """[{"name": "slow", "count": 2}] -> ["slow:2"], the runtime's fault spec format."""
    return [f"{fault.name}:{fault.count}" for fault in faults]


def replay_request(
    body: ReplayStartBody, settings: ApiSettings, run_id: str, shared_console: SharedConsole
) -> ReplayRequest:
    options = session_options(settings, "replay", run_id, body.tenant, body.escalation, shared_console,
                              risky_confirmed=body.risky_confirmed)
    return ReplayRequest(
        capability_id=body.capability_id, version=body.version, inputs=dict(body.inputs), tenant=body.tenant,
        risky_confirmed=body.risky_confirmed, faults=fault_specs(body.faults), target_url=settings.target_url,
        session=options, artifacts_dir=settings.artifacts_dir,
    )


def entry_point_for(settings: ApiSettings, tenant: str) -> str:
    return f"{settings.target_url}/t/{tenant}/login"


def discover_request(  # the planner name was checked by hands.api.validation.check_planner
    body: DiscoveryStartBody, settings: ApiSettings, run_id: str, shared_console: SharedConsole
) -> DiscoverRequest:
    options = session_options(settings, "discovery", run_id, body.tenant, body.escalation, shared_console)
    return DiscoverRequest(
        goal=body.goal, entry_point=entry_point_for(settings, body.tenant), inputs=dict(body.inputs),
        sensitive_inputs=list(body.sensitive_inputs), capability_id=body.capability_id, title=body.title,
        description=body.description, tenant=body.tenant, planner=cast(PlannerChoice, body.planner),
        model=body.model, cassette_path=None, cassette_mode="off", max_steps=body.max_steps, session=options,
        profile_path=settings.profile_path, artifacts_dir=settings.artifacts_dir,
    )
