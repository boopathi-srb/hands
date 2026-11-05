"""Async implementations of the CLI verbs. The CLI module only parses arguments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from hands.catalog import ArtifactStore, load_for_tenant, merge_profile
from hands.core.artifact import AppRef, Capability, InputSpec
from hands.core.log import get_logger, log_failure
from hands.discovery import DiscoveryAgent, record_capability
from hands.profiles import AppProfile, load_profile
from hands.replay import ReplayEngine
from hands.runtime.assembly import RunSession, SessionOptions, build_session
from hands.runtime.credentials import EnvCredentialProvider
from hands.runtime.planners import CassetteChoice, PlannerChoice, build_planner

logger = get_logger(__name__)

RESULT_EXIT_CODES = {"success": 0, "business_outcome": 3, "escalated": 4, "failed": 1}
_DIGITS_ONLY = re.compile(r"^\d+$")


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
    exit_code: int
    summary: dict[str, Any]


# ---------------------------------------------------------------- discover


async def run_discover(request: DiscoverRequest) -> CommandOutcome:
    profile = _load_profile_or_none(request.profile_path)
    built = await build_session(request.session)
    if built.session is None:
        return _error_outcome("discover", built.error or "session failed")
    session = built.session
    outcome = await _run_discovery_agent(request, session, profile)
    record = _record(request, outcome, profile)
    summary = _discovery_summary(request, session, outcome, record)
    if record.capability is not None:
        _save_artifact(request.artifacts_dir, record.capability, session, summary)
    session.evidence.write_json("discovery_result.json", summary)
    await session.close()
    return CommandOutcome(0 if record.capability is not None else 1, summary)


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
    written = ArtifactStore(artifacts_dir).save(capability)
    summary["artifact_path"] = getattr(written, "path", None)
    session.evidence.write_json("capability", capability)


# ---------------------------------------------------------------- replay


async def run_replay(request: ReplayRequest) -> CommandOutcome:
    store = ArtifactStore(request.artifacts_dir)
    loaded = load_for_tenant(store, request.capability_id, request.tenant, request.version)
    if loaded.capability is None:
        return _error_outcome("replay", loaded.error or "capability not found")
    capability = loaded.capability
    fault_error = await _arm_faults(request.target_url, request.faults, request.tenant)
    if fault_error is not None:
        return _error_outcome("replay", fault_error)
    built = await build_session(_with_status(request.session, capability))
    if built.session is None:
        return _error_outcome("replay", built.error or "session failed")
    result = await _run_engine(request, built.session, capability, loaded)
    store.record_run(capability.id, capability.version, result)
    await built.session.close()
    summary = json.loads(result.model_dump_json())
    return CommandOutcome(RESULT_EXIT_CODES.get(result.status, 1), summary)


def _with_status(options: SessionOptions, capability: Capability) -> SessionOptions:
    from dataclasses import replace

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


async def _arm_faults(target_url: str, faults: list[str], tenant: str | None) -> str | None:
    """Test harness only: arm mock-app faults out of band. The agent itself is blocked from /_admin."""
    for fault_spec in faults:
        fault_name, _, count_text = fault_spec.partition(":")
        payload = {"fault": fault_name, "count": int(count_text or "1"), "tenant": tenant or "*"}
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
    store.save(Capability.model_validate(updated.model_dump()))
    return CommandOutcome(0, {"capability": f"{updated.id}@{updated.version}", "status": status})


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


def _error_outcome(command: str, message: str) -> CommandOutcome:
    log_failure(logger, command, message)
    return CommandOutcome(2, {"status": "error", "command": command, "message": message})
