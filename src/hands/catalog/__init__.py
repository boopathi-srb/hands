"""Catalog: where capabilities live, how tenants specialize them, and how agents discover and call them.

- `store`          ArtifactStore: versioned capability JSON, tenant overlays, replay stats
- `overlay`        apply_overlay / load_for_tenant: the effective capability for one tenant
- `invocation`     capability_tool_schema: the JSON-schema tool definition a calling agent uses
- `profile_merge`  merge_profile: add vendor runtime knowledge (outcomes, recoveries, login) to a capability
- `versions`       tiny semver helpers
"""

from hands.catalog.invocation import (
    capability_input_schema,
    capability_result_schema,
    capability_tool_schema,
    tool_name_for,
)
from hands.catalog.overlay import OverlayResult, apply_overlay, load_for_tenant
from hands.catalog.profile_merge import merge_profile
from hands.catalog.store import (
    ArtifactStore,
    CapabilityLoad,
    CatalogEntry,
    FieldSummary,
    OverlayLoad,
    StatsUpdate,
    StoreWrite,
    updated_replay_stats,
)
from hands.catalog.versions import RangeCheck, latest_version, parse_semver, satisfies_range

__all__ = [
    "ArtifactStore",
    "CapabilityLoad",
    "CatalogEntry",
    "FieldSummary",
    "OverlayLoad",
    "OverlayResult",
    "RangeCheck",
    "StatsUpdate",
    "StoreWrite",
    "apply_overlay",
    "capability_input_schema",
    "capability_result_schema",
    "capability_tool_schema",
    "latest_version",
    "load_for_tenant",
    "merge_profile",
    "parse_semver",
    "satisfies_range",
    "tool_name_for",
    "updated_replay_stats",
]
