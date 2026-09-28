"""ArtifactStore: capabilities and tenant overlays as reviewable JSON files on disk.

Layout
    <root>/<capability_id>/<version>.json              one file per capability version
    <root>/<capability_id>/overlays/<tenant_id>.json   one file per tenant overlay

Every public method returns a typed result. File-system and validation errors are caught here (the I/O
boundary), logged with `log_failure`, and reported in the result's `error`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError

from hands.catalog.versions import latest_version, sort_versions
from hands.core.artifact import (
    SEMVER_PATTERN,
    SLUG_PATTERN,
    Capability,
    InputSpec,
    OutputSpec,
    ReplayStats,
    TenantOverlay,
)
from hands.core.log import get_logger, log_failure
from hands.core.results import RunResult

_logger = get_logger(__name__)

OVERLAYS_DIR = "overlays"
_SLUG = re.compile(SLUG_PATTERN)
_SEMVER = re.compile(SEMVER_PATTERN)
ModelT = TypeVar("ModelT", bound=BaseModel)


# ---------------------------------------------------------------- result types


class StoreWrite(BaseModel):
    ok: bool
    path: str | None = None
    error: str | None = None


class CapabilityLoad(BaseModel):
    capability: Capability | None = None
    error: str | None = None


class OverlayLoad(BaseModel):
    """`absent` is a normal answer (the tenant uses the base capability as is), not an error."""

    status: Literal["found", "absent", "invalid"]
    overlay: TenantOverlay | None = None
    error: str | None = None


class StatsUpdate(BaseModel):
    stats: ReplayStats | None = None
    error: str | None = None


class FieldSummary(BaseModel):
    """What a calling agent needs to know about one input or output."""

    type: str
    description: str
    required: bool | None = None
    sensitive: bool = False
    pattern: str | None = None


class CatalogEntry(BaseModel):
    """One discoverable capability: its latest version plus its input/output contract."""

    id: str
    latest_version: str
    versions: list[str]
    status: str
    title: str
    description: str
    inputs: dict[str, FieldSummary] = Field(default_factory=dict)
    outputs: dict[str, FieldSummary] = Field(default_factory=dict)
    outcome_codes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- the store


class ArtifactStore:
    """File-backed catalog of capability versions and their tenant overlays."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------ capabilities

    def save(self, capability: Capability) -> StoreWrite:
        """Write (or overwrite) `<root>/<id>/<version>.json`."""
        path = self._capability_path(capability.id, capability.version)
        return _write_text(path, capability.model_dump_json(indent=2), "ArtifactStore.save")

    def list_versions(self, capability_id: str) -> list[str]:
        """Stored versions of one capability, ascending. Empty for unknown or invalid ids."""
        if not _is_slug(capability_id):
            return []
        capability_dir = self._root / capability_id
        if not capability_dir.is_dir():
            return []
        return sort_versions(path.stem for path in capability_dir.glob("*.json"))

    def load(self, capability_id: str, version: str | None = None) -> CapabilityLoad:
        """Load one version, or the latest by semver when `version` is None."""
        name_error = _name_error(capability_id, version)
        if name_error is not None:
            log_failure(_logger, "ArtifactStore.load", name_error, capability_id=capability_id, version=version)
            return CapabilityLoad(error=name_error)
        chosen_version = version or latest_version(self.list_versions(capability_id))
        if chosen_version is None:
            log_failure(_logger, "ArtifactStore.load", "no versions stored", capability_id=capability_id)
            return CapabilityLoad(error=f"capability '{capability_id}' has no stored versions")
        path = self._capability_path(capability_id, chosen_version)
        loaded = _read_model(path, Capability, "ArtifactStore.load")
        if isinstance(loaded, str):
            return CapabilityLoad(error=loaded)
        return CapabilityLoad(capability=loaded)

    def list_capabilities(self) -> list[CatalogEntry]:
        """Every stored capability at its latest version, sorted by id: what a calling agent discovers."""
        if not self._root.is_dir():
            return []
        entries: list[CatalogEntry] = []
        for capability_dir in sorted(path for path in self._root.iterdir() if path.is_dir()):
            loaded = self.load(capability_dir.name)
            if loaded.capability is not None:
                entries.append(_catalog_entry(loaded.capability, self.list_versions(capability_dir.name)))
        return entries

    # ------------------------------------------------------------ overlays

    def save_overlay(self, overlay: TenantOverlay) -> StoreWrite:
        path = self._overlay_path(overlay.capability_id, overlay.tenant_id)
        return _write_text(path, overlay.model_dump_json(indent=2), "ArtifactStore.save_overlay")

    def load_overlay(self, capability_id: str, tenant_id: str) -> OverlayLoad:
        if not (_is_slug(capability_id) and _is_slug(tenant_id)):
            message = f"invalid capability id '{capability_id}' or tenant id '{tenant_id}'"
            log_failure(_logger, "ArtifactStore.load_overlay", message)
            return OverlayLoad(status="invalid", error=message)
        path = self._overlay_path(capability_id, tenant_id)
        if not path.is_file():
            return OverlayLoad(status="absent")
        loaded = _read_model(path, TenantOverlay, "ArtifactStore.load_overlay")
        if isinstance(loaded, str):
            return OverlayLoad(status="invalid", error=loaded)
        return OverlayLoad(status="found", overlay=loaded)

    # ------------------------------------------------------------ stats

    def record_run(self, capability_id: str, version: str, result: RunResult) -> StatsUpdate:
        """Fold one run result into the stored version's ReplayStats and save it."""
        loaded = self.load(capability_id, version)
        if loaded.capability is None:
            return StatsUpdate(error=loaded.error)
        updated_stats = updated_replay_stats(loaded.capability.stats, result)
        written = self.save(loaded.capability.model_copy(update={"stats": updated_stats}))
        if not written.ok:
            return StatsUpdate(error=written.error)
        return StatsUpdate(stats=updated_stats)

    # ------------------------------------------------------------ paths

    def _capability_path(self, capability_id: str, version: str) -> Path:
        return self._root / capability_id / f"{version}.json"

    def _overlay_path(self, capability_id: str, tenant_id: str) -> Path:
        return self._root / capability_id / OVERLAYS_DIR / f"{tenant_id}.json"


# ---------------------------------------------------------------- pure helpers


def updated_replay_stats(stats: ReplayStats, result: RunResult) -> ReplayStats:
    """ReplayStats after counting one more run. Escalated runs count as runs but not as failures."""
    return ReplayStats(
        runs=stats.runs + 1,
        successes=stats.successes + (1 if result.status == "success" else 0),
        business_outcomes=stats.business_outcomes + (1 if result.status == "business_outcome" else 0),
        failures=stats.failures + (1 if result.status == "failed" else 0),
        fallback_matches=stats.fallback_matches + len(result.drift.fallback_steps),
    )


def summarize_input(spec: InputSpec) -> FieldSummary:
    return FieldSummary(
        type=spec.type,
        description=spec.description,
        required=spec.required,
        sensitive=spec.sensitive,
        pattern=spec.pattern,
    )


def summarize_output(spec: OutputSpec) -> FieldSummary:
    return FieldSummary(type=spec.type, description=spec.description, sensitive=spec.sensitive)


def _catalog_entry(capability: Capability, versions: list[str]) -> CatalogEntry:
    return CatalogEntry(
        id=capability.id,
        latest_version=capability.version,
        versions=versions,
        status=capability.status,
        title=capability.title,
        description=capability.description,
        inputs={name: summarize_input(spec) for name, spec in capability.inputs.items()},
        outputs={name: summarize_output(spec) for name, spec in capability.outputs.items()},
        outcome_codes=[detector.code for detector in capability.outcomes],
    )


def _is_slug(value: str) -> bool:
    return bool(value) and _SLUG.fullmatch(value) is not None


def _name_error(capability_id: str, version: str | None) -> str | None:
    if not _is_slug(capability_id):
        return f"invalid capability id '{capability_id}'"
    if version is not None and _SEMVER.fullmatch(version) is None:
        return f"invalid version '{version}' (expected x.y.z)"
    return None


def _write_text(path: Path, content: str, function_name: str) -> StoreWrite:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
    except OSError as write_error:
        log_failure(_logger, function_name, f"write failed: {write_error}", path=str(path))
        return StoreWrite(ok=False, path=str(path), error=f"could not write {path}: {write_error}")
    return StoreWrite(ok=True, path=str(path))


def _read_model(path: Path, model: type[ModelT], function_name: str) -> ModelT | str:
    """The validated model, or an error message (already logged)."""
    raw_document = _read_json(path, function_name)
    if isinstance(raw_document, str):
        return raw_document
    try:
        return model.model_validate(raw_document)
    except ValidationError as validation_error:
        log_failure(_logger, function_name, "validation failed", path=str(path), errors=validation_error.error_count())
        return f"{path} failed validation: {validation_error}"


def _read_json(path: Path, function_name: str) -> dict[str, Any] | str:
    if not path.is_file():
        log_failure(_logger, function_name, "file not found", path=str(path))
        return f"not found: {path}"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as read_error:
        log_failure(_logger, function_name, f"read failed: {read_error}", path=str(path))
        return f"could not read {path}: {read_error}"
    if not isinstance(document, dict):
        log_failure(_logger, function_name, "document is not a JSON object", path=str(path))
        return f"{path} is not a JSON object"
    return document
