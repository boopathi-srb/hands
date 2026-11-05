"""Reference data for the UI: tenants, injectable faults, and the capability catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hands.api.validation import ApiError
from hands.catalog import ArtifactStore, capability_tool_schema
from hands.catalog.store import OVERLAYS_DIR
from hands.runtime.commands import catalog_list, catalog_set_status
from target_app.faults import FaultName
from target_app.tenants import TENANTS

FAULT_DESCRIPTIONS: dict[FaultName, str] = {
    FaultName.SESSION_EXPIRED: "Next page load shows 'Your session has expired'; replay signs on again.",
    FaultName.SLOW: "Next page loads are delayed (4 s by default); replay waits on conditions, not sleeps.",
    FaultName.MAINTENANCE_NOTICE: "An in-page 'System Notice' modal covers the content; replay acknowledges it.",
    FaultName.NATIVE_ALERT: "A native JS alert('Printer queue offline') on load; replay accepts it.",
    FaultName.IDENTITY_CHECK: "A 'Verify Member Identity' modal with no automated answer; a human must decide.",
    FaultName.APP_ERROR: "An 'Internal Error. Reference ID ERR-5521.' page; replay restarts the flow once.",
}


def tenant_list() -> list[dict[str, str]]:
    return [{"id": tenant.slug, "name": tenant.brand} for tenant in TENANTS.values()]


def fault_list() -> list[dict[str, str]]:
    return [{"name": fault.value, "description": FAULT_DESCRIPTIONS.get(fault, fault.value)} for fault in FaultName]


def capability_list(artifacts_dir: Path) -> list[dict[str, Any]]:
    """CatalogEntry JSON for every capability, plus its latest version's replay stats."""
    store = ArtifactStore(artifacts_dir)
    entries = catalog_list(artifacts_dir)
    for entry in entries:
        loaded = store.load(entry["id"], entry["latest_version"])
        entry["stats"] = None if loaded.capability is None else loaded.capability.stats.model_dump(mode="json")
    return entries


def overlay_tenants(artifacts_dir: Path, capability_id: str) -> list[str]:
    overlays_dir = artifacts_dir / capability_id / OVERLAYS_DIR
    if not overlays_dir.is_dir():
        return []
    return sorted(path.stem for path in overlays_dir.glob("*.json"))


def capability_detail(artifacts_dir: Path, capability_id: str, version: str | None) -> dict[str, Any] | ApiError:
    loaded = ArtifactStore(artifacts_dir).load(capability_id, version)
    if loaded.capability is None:
        return ApiError(404, "unknown_capability", loaded.error or f"unknown capability '{capability_id}'")
    capability = loaded.capability
    return {
        "capability": json.loads(capability.model_dump_json()),
        "overlays": overlay_tenants(artifacts_dir, capability.id),
        "tool": capability_tool_schema(capability),
    }


def approve_capability(artifacts_dir: Path, capability_id: str, version: str | None) -> dict[str, Any] | ApiError:
    outcome = catalog_set_status(artifacts_dir, capability_id, version, "approved")
    if outcome.exit_code != 0:
        return ApiError(404, "unknown_capability", str(outcome.summary.get("message") or capability_id))
    return {"id": outcome.summary["id"], "version": outcome.summary["version"], "status": "approved"}
