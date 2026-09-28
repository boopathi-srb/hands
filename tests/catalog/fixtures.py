"""A CoreOne-shaped capability used by the catalog tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hands.core.artifact import Capability, TenantOverlay

LAKESIDE_LOGIN = "http://127.0.0.1:8700/t/lakeside/login"
PRAIRIE_LOGIN = "http://127.0.0.1:8700/t/prairie/login"


def candidate(kind: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, "confidence": 0.8, "reason": "test", **fields}


def target(description: str, *candidates: dict[str, Any]) -> dict[str, Any]:
    return {"description": description, "candidates": list(candidates)}


BALANCE_TARGET = target(
    "Regular Savings balance",
    candidate("text_anchor", anchor_text="Regular Savings", relation="right_of", role="cell"),
    candidate("structural", container_path=["frame:content"], structural_path="table[2]/row[2]/cell[3]"),
)


def balance_capability_data(version: str = "1.2.0") -> dict[str, Any]:
    return {
        "id": "coreone.member_balance",
        "version": version,
        "status": "approved",
        "title": "Member savings balance",
        "description": "Look up a member and return the savings balance.",
        "app": {"vendor": "Northwind Core Systems", "product": "CoreOne", "product_version": "7.4",
                "surface": "web"},
        "inputs": {"member_number": {"type": "string", "description": "Member number", "pattern": r"^\d+$",
                                     "example": "10001"}},
        "outputs": {"balance": {"type": "decimal", "description": "Savings balance"}},
        "credentials": {"teller": {"description": "Teller sign-on"}},
        "steps": [
            {"id": "sign_in", "action": "subflow", "description": "Sign on", "subflow": "login"},
            {"id": "type_member", "action": "type", "description": "Member", "value": "{{member_number}}",
             "target": target("Member number", candidate("label", label="Member Number", role="textbox"))},
            {"id": "search", "action": "click", "description": "Search",
             "target": target("Search", candidate("role_name", role="button", name="Search"))},
            {"id": "read_balance", "action": "extract", "description": "Balance", "output": "balance",
             "target": BALANCE_TARGET},
        ],
        "subflows": {"login": [
            {"id": "login_open", "action": "open", "description": "Open", "entry_point": LAKESIDE_LOGIN},
            {"id": "login_user", "action": "type", "description": "User", "value": "{{teller.username}}",
             "target": target("User ID", candidate("label", label="User ID", role="textbox"))},
        ]},
        "checkpoint": {"kind": "text_visible", "pattern": "Member Detail"},
        "outcomes": [{"code": "MEMBER_NOT_FOUND", "description": "No such member",
                      "when": {"kind": "text_visible", "pattern": "No member found"}}],
        "provenance": {"discovery_run_id": "disc-1", "recorded_at": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
                       "planner": "scripted", "goal": "read a balance", "recorded_on_tenant": "lakeside"},
    }


def balance_capability(version: str = "1.2.0", **overrides: Any) -> Capability:
    data = balance_capability_data(version)
    data.update(overrides)
    return Capability.model_validate(data)


PRAIRIE_BALANCE_TARGET = target(
    "Share Savings balance (prairie column order)",
    candidate("text_anchor", anchor_text="Share Savings", relation="same_row", role="cell", ordinal=1),
    candidate("structural", container_path=["frame:content"], structural_path="table[2]/row[2]/cell[2]"),
)


def prairie_overlay(**overrides: Any) -> TenantOverlay:
    data: dict[str, Any] = {
        "tenant_id": "prairie",
        "capability_id": "coreone.member_balance",
        "base_version_range": ">=1.0.0,<2.0.0",
        "entry_point_overrides": {"login_open": PRAIRIE_LOGIN},
        "target_overrides": {"read_balance": PRAIRIE_BALANCE_TARGET},
        "text_aliases": {"Member Number": "Account Number", "Search": "Find", "Regular Savings": "Share Savings"},
        "outcome_overrides": {"MEMBER_NOT_FOUND": {"kind": "text_visible", "pattern": "No account found"}},
    }
    data.update(overrides)
    return TenantOverlay.model_validate(data)
