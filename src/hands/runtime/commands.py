"""Async implementations of the CLI verbs. The CLI module only parses arguments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from hands.catalog import ArtifactStore, latest_version, load_for_tenant, merge_profile
from hands.catalog.versions import next_minor
from hands.core.artifact import AppRef, Capability, InputSpec
from hands.core.log import get_logger, log_failure
from hands.core.results import RunResult
from hands.discovery import DiscoveryAgent, record_capability
from hands.discovery.trace import DiscoveryOutcome
from hands.profiles import AppProfile, load_profile
from hands.replay import ReplayEngine
from hands.runtime.assembly import RunSession, SessionOptions, build_session
from hands.runtime.credentials import EnvCredentialProvider
from hands.runtime.planners import CassetteChoice, PlannerChoice, build_planner
from hands.surfaces.fake import FakeSurface
from target_app.faults import MAX_FAULT_COUNT, FaultName

logger = get_logger(__name__)

RESULT_EXIT_CODES = {"success": 0, "business_outcome": 3, "escalated": 4, "failed": 1}
_DIGITS_ONLY = re.compile(r"^\d+$")
SLOW_FAULT = FaultName.SLOW.value
# On the fake surface, `slow` returns the loading screen for this many observations per armed count.
FAKE_SLOW_OBSERVATIONS_PER_COUNT = 2


@dataclass(frozen=True)
class DiscoverRequest:
    goal: str
    entry_point: str
    inputs: dict[str, str]
    sensitive_inputs: list[str]
    capability_id: str
    title: str
    description: str
    tenant: str
    planner: PlannerChoice
    model: str | None
    cassette_path: Path | None
    cassette_mode: CassetteChoice
    max_steps: int
    session: SessionOptions
    profile_path: Path
    artifacts_dir: Path


@dataclass(frozen=True)
class ReplayRequest:
    capability_id: str
    version: str | None
    inputs: dict[str, str]
    tenant: str | None
    risky_confirmed: bool
    faults: list[str]
    target_url: str
    session: SessionOptions
    artifacts_dir: Path


@dataclass(frozen=True)
class CommandOutcome:
    """`summary` is the JSON the CLI prints. `result` is the typed object behind it: the RunResult of a
    replay or the DiscoveryOutcome of a discovery; None when the command failed before running."""

    exit_code: int
    summary: dict[str, Any]
    result: RunResult | DiscoveryOutcome | None = None


@dataclass(frozen=True)
class FaultSpec:
    name: str
    count: int


# ---------------------------------------------------------------- discover


async def run_discover(request: DiscoverRequest) -> CommandOutcome:
    started_at = _utc_now_iso()
    profile = _load_profile_or_none(request.profile_path)
    built = await build_session(request.session)
    if built.session is None:
        return _error_outcome("discover", built.error or "session failed")
    try:
        return await _discover_in_session(request, built.session, profile, started_at)
    finally:  # the browser and console registration must not outlive a crashed run
        await built.session.close()


async def _discover_in_session(
    request: DiscoverRequest, session: RunSession, profile: AppProfile | None, started_at: str
) -> CommandOutcome:
    outcome = await _run_discovery_agent(request, session, profile)
    record = _record(request, outcome, profile)
    summary = _discovery_summary(request, session, outcome, record)
    summary.update(started_at=started_at, finished_at=_utc_now_iso())
    if record.capability is not None:
        _save_artifact(request.artifacts_dir, record.capability, session, summary)
    session.evidence.write_json("discovery_result.json", summary)
    return CommandOutcome(0 if record.capability is not None else 1, summary, outcome)


async def _run_discovery_agent(request: DiscoverRequest, session: RunSession, profile: AppProfile | None) -> Any:
    planner = build_planner(request.planner, request.model, request.tenant,
                            request.cassette_path, request.cassette_mode)
    agent = DiscoveryAgent(
        session.surface, planner, session.policy, session.evidence, EnvCredentialProvider(),
        escalator=session.escalator, secret_registrar=session.redactor.register_secret,
        max_steps=request.max_steps, run_id=session.options.run_id, session_id=session.session_id,
    )
    for name in request.sensitive_inputs:
        session.redactor.register_secret(request.inputs.get(name), f"input:{name}")
    return await agent.run(request.goal, request.entry_point, request.inputs, _credential_names(profile))


def _credential_names(profile: AppProfile | None) -> list[str]:
    if profile is None:
        return []
    return [f"{name}.{field}" for name, spec in profile.credentials.items() for field in spec.fields]


def _record(request: DiscoverRequest, outcome: Any, profile: AppProfile | None) -> Any:
    app = _app_ref(profile)
    return record_capability(
        outcome, capability_id=request.capability_id, title=request.title, description=request.description,
        app=app, inputs=_input_specs(request), profile=profile, planner_name=request.planner,
        model=request.model or _default_model(request.planner), tenant_id=request.tenant,
    )


def _app_ref(profile: AppProfile | None) -> AppRef:
    if profile is None:
        return AppRef(vendor="unknown", product="unknown", product_version="unknown", surface="web")
    surface = "desktop" if profile.surface == "desktop" else "web"
    return AppRef(vendor=profile.vendor, product=profile.product,
                  product_version=profile.product_versions[-1], surface=surface)


def _input_specs(request: DiscoverRequest) -> dict[str, InputSpec]:
    return {name: _infer_input_spec(name, value, name in request.sensitive_inputs)
            for name, value in request.inputs.items()}


def _infer_input_spec(name: str, value: str, sensitive: bool) -> InputSpec:
    """Digit strings are identifiers, not numbers: keep them strings with a digits pattern."""
    pattern = r"^\d+$" if _DIGITS_ONLY.match(value) else None
    example = None if sensitive else value
    readable_name = name.replace("_", " ")
    return InputSpec(type="string", description=f"The {readable_name} to use.", pattern=pattern,
                     sensitive=sensitive, example=example)


def _default_model(planner: PlannerChoice) -> str | None:
    from hands.discovery.planners.anthropic import DEFAULT_ANTHROPIC_MODEL
    from hands.discovery.planners.ollama import DEFAULT_OLLAMA_MODEL

    return {"ollama": DEFAULT_OLLAMA_MODEL, "anthropic": DEFAULT_ANTHROPIC_MODEL, "scripted": None}[planner]


def _discovery_summary(request: DiscoverRequest, session: RunSession, outcome: Any, record: Any) -> dict[str, Any]:
    capability = record.capability
    return {
        "mode": "discovery",
        "run_id": session.options.run_id,
        "capability_id": request.capability_id,
        "tenant": request.tenant,
        "planner": request.planner,
        "model": request.model or _default_model(request.planner),
        "status": outcome.status,
        "reason": outcome.reason,
        "steps": len(outcome.trace),
        "planner_calls": outcome.planner_calls,
        "invalid_decisions": outcome.invalid_decisions,
        "extracted": outcome.extracted,
        "capability": f"{capability.id}@{capability.version}" if capability else None,
        "record_error": record.error,
        "record_warnings": record.warnings,
        "evidence_dir": session.evidence.run_dir,
    }


def _save_artifact(artifacts_dir: Path, capability: Capability, session: RunSession, summary: dict[str, Any]) -> None:
    store = ArtifactStore(artifacts_dir)
    capability = _unused_version(store, capability)
    written = store.save(capability)
    summary["capability"] = f"{capability.id}@{capability.version}"
    summary["artifact_path"] = getattr(written, "path", None)
    session.evidence.write_json("capability", capability)


def _unused_version(store: ArtifactStore, capability: Capability) -> Capability:
    """Never overwrite a recorded capability: a re-discovery becomes the next minor version, as a draft."""
    existing_versions = store.list_versions(capability.id)
    if capability.version not in existing_versions:
        return capability
    newest = latest_version(existing_versions) or capability.version
    bumped = next_minor(newest)
    if bumped is None:
        log_failure(logger, "_unused_version", "cannot bump version", capability_id=capability.id, version=newest)
        return capability
    return capability.model_copy(update={"version": bumped})


# ---------------------------------------------------------------- replay


async def run_replay(request: ReplayRequest) -> CommandOutcome:
    store = ArtifactStore(request.artifacts_dir)
    loaded = load_for_tenant(store, request.capability_id, request.tenant, request.version)
    if loaded.capability is None:
        return _error_outcome("replay", loaded.error or "capability not found")
    capability = loaded.capability
    fault_specs = parse_fault_specs(request.faults)
    if isinstance(fault_specs, str):
        return _error_outcome("replay", fault_specs)
    built = await _build_replay_session(request, capability, fault_specs)
    if isinstance(built, str):
        return _error_outcome("replay", built)
    try:
        result = await _run_engine(request, built, capability, loaded)
    finally:  # the browser and console registration must not outlive a crashed run
        await built.close()
    store.record_run(capability.id, capability.version, result)
    summary = json.loads(result.model_dump_json())
    return CommandOutcome(RESULT_EXIT_CODES.get(result.status, 1), summary, result)


async def _build_replay_session(
    request: ReplayRequest, capability: Capability, fault_specs: list[FaultSpec]
) -> RunSession | str:
    """Arm faults (mock app before the session, fake surface after it) and build the session."""
    on_fake_surface = request.session.surface == "fake"
    if not on_fake_surface:
        fault_error = await _arm_faults(request.target_url, fault_specs, request.tenant)
        if fault_error is not None:
            return fault_error
    built = await build_session(_with_status(request.session, capability))
    if built.session is None:
        return built.error or "session failed"
    fake_fault_error = arm_fake_faults(built.session.raw_surface, fault_specs) if on_fake_surface else None
    if fake_fault_error is not None:
        await built.session.close()
        return fake_fault_error
    return built.session


def _with_status(options: SessionOptions, capability: Capability) -> SessionOptions:
    return replace(options, capability_status=capability.status)


async def _run_engine(request: ReplayRequest, session: RunSession, capability: Capability, loaded: Any) -> Any:
    engine = ReplayEngine(
        session.surface, session.policy, session.evidence, EnvCredentialProvider(),
        escalator=session.escalator, secret_registrar=session.redactor.register_secret,
    )
    session.evidence.write_json("capability", capability)
    return await engine.run(
        capability, request.inputs, tenant_id=request.tenant, aliases=getattr(loaded, "aliases", None),
        risky_confirmed=request.risky_confirmed, session_id=session.session_id, run_id=session.options.run_id,
    )


def parse_fault_specs(faults: list[str]) -> list[FaultSpec] | str:
    """`["session_expired", "slow:2"]` -> FaultSpecs; an error message (logged) for a bad entry."""
    known_faults = {fault.value for fault in FaultName}
    parsed: list[FaultSpec] = []
    for fault_spec in faults:
        fault_name, _, count_text = fault_spec.partition(":")
        count_text = count_text or "1"
        valid_count = count_text.isascii() and count_text.isdigit() and 1 <= int(count_text) <= MAX_FAULT_COUNT
        if fault_name not in known_faults or not valid_count:
            log_failure(logger, "parse_fault_specs", "invalid fault spec", fault_spec=fault_spec)
            return f"invalid fault '{fault_spec}': expected one of {sorted(known_faults)} with count 1..{MAX_FAULT_COUNT}"
        parsed.append(FaultSpec(name=fault_name, count=int(count_text)))
    return parsed


def arm_fake_faults(surface: object, faults: list[FaultSpec]) -> str | None:
    """Test harness on the fake surface: queue fault screens in-process instead of arming the mock app.

    Page faults appear right after the next successful act, the way the mock app shows them on the next load.
    """
    if not faults:
        return None
    if not isinstance(surface, FakeSurface):
        log_failure(logger, "arm_fake_faults", "surface is not a FakeSurface", surface=type(surface).__name__)
        return "faults can only be injected into the fake surface"
    for fault in faults:
        error = _inject_fake_fault(surface, fault)
        if error is not None:
            return error
    return None


def _inject_fake_fault(surface: FakeSurface, fault: FaultSpec) -> str | None:
    if fault.name == SLOW_FAULT:
        surface.delay_observations(fault.count * FAKE_SLOW_OBSERVATIONS_PER_COUNT)
        return None
    if fault.name not in surface.screen_names:
        log_failure(logger, "_inject_fake_fault", "fake surface has no screen for fault", fault=fault.name)
        return f"the fake surface cannot show fault '{fault.name}'"
    for _ in range(fault.count):
        surface.inject_next(fault.name, trigger="act")
    return None


async def _arm_faults(target_url: str, faults: list[FaultSpec], tenant: str | None) -> str | None:
    """Test harness only: arm mock-app faults out of band. The agent itself is blocked from /_admin."""
    for fault in faults:
        payload = {"fault": fault.name, "count": fault.count, "tenant": tenant or "*"}
        error = await _post_fault(target_url, payload)
        if error is not None:
            return error
    return None


async def _post_fault(target_url: str, payload: dict[str, Any]) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(f"{target_url}/_admin/faults", json=payload)
    except httpx.HTTPError as http_error:
        log_failure(logger, "_post_fault", str(http_error), target_url=target_url, payload=payload)
        return f"cannot arm fault {payload['fault']}: {http_error}"
    if response.status_code >= 300:
        return f"cannot arm fault {payload['fault']}: HTTP {response.status_code} {response.text[:200]}"
    return None


# ---------------------------------------------------------------- catalog


def catalog_list(artifacts_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(entry.model_dump_json()) for entry in ArtifactStore(artifacts_dir).list_capabilities()]


def catalog_tools(artifacts_dir: Path) -> list[dict[str, Any]]:
    from hands.catalog import capability_tool_schema

    store = ArtifactStore(artifacts_dir)
    tools = []
    for entry in store.list_capabilities():
        loaded = store.load(entry.id)
        if loaded.capability is not None:
            tools.append(capability_tool_schema(loaded.capability))
    return tools


def catalog_set_status(artifacts_dir: Path, capability_id: str, version: str | None, status: str) -> CommandOutcome:
    store = ArtifactStore(artifacts_dir)
    loaded = store.load(capability_id, version)
    if loaded.capability is None:
        return _error_outcome("catalog", loaded.error or "not found")
    updated = loaded.capability.model_copy(update={"status": status})
    written = store.save(Capability.model_validate(updated.model_dump()))
    if not written.ok:
        return _error_outcome("catalog", written.error or "could not save capability")
    summary = {"capability": f"{updated.id}@{updated.version}", "id": updated.id,
               "version": updated.version, "status": status}
    return CommandOutcome(0, summary)


def catalog_merge_profile(artifacts_dir: Path, capability_id: str, profile_path: Path) -> CommandOutcome:
    """Re-apply the vendor profile to a saved capability (after the profile learned a new condition)."""
    profile = _load_profile_or_none(profile_path)
    store = ArtifactStore(artifacts_dir)
    loaded = store.load(capability_id)
    if profile is None or loaded.capability is None:
        return _error_outcome("catalog", "profile or capability not found")
    store.save(merge_profile(loaded.capability, profile))
    return CommandOutcome(0, {"capability": capability_id, "merged_profile": str(profile_path)})


# ---------------------------------------------------------------- helpers


def _load_profile_or_none(profile_path: Path) -> AppProfile | None:
    loaded = load_profile(profile_path)
    if loaded.profile is None:
        log_failure(logger, "_load_profile_or_none", loaded.error or "unknown", path=str(profile_path))
    return loaded.profile


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _error_outcome(command: str, message: str) -> CommandOutcome:
    log_failure(logger, command, message)
    return CommandOutcome(2, {"status": "error", "command": command, "message": message})
