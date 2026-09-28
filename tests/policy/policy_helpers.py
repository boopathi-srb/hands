"""Builders shared by the policy tests (a uniquely named module, not conftest, to avoid import clashes)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from hands.core.observation import Location, Node
from hands.core.ports import PolicyRequest
from hands.policy import PolicyConfig, policy_from_mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
COREONE_POLICY_PATH = REPO_ROOT / "policies" / "coreone.yaml"
ORIGIN = "http://127.0.0.1:8700"

RequestFactory = Callable[..., PolicyRequest]


def minimal_policy_mapping(**overrides: Any) -> dict[str, Any]:
    """A small valid policy; sections can be replaced through keyword overrides."""
    mapping: dict[str, Any] = {
        "version": 1,
        "name": "test",
        "surfaces": {
            "web": {
                "allowed_origins": [ORIGIN],
                "allowed_path_patterns": ["/t/lakeside/**"],
                "blocked_path_patterns": ["/_admin/**"],
            },
            "desktop": {"allowed_bundle_ids": ["com.apple.calculator"]},
        },
        "actions": {
            "allowed": {
                "discovery": ["open", "click", "type", "press", "select", "scroll"],
                "replay": ["open", "click", "type", "press", "select", "scroll"],
                "human": ["click", "type", "press", "select", "scroll"],
            }
        },
        "risk": {
            "default": "safe",
            "rules": [
                {
                    "name": "irreversible",
                    "description": "commit buttons",
                    "match": {"control_pattern": r"\bsubmit\b", "action_kinds": ["click", "press"]},
                }
            ],
            "handling": {
                "discovery": "escalate",
                "replay": "allow_if_approved_and_confirmed",
                "human": "allow",
            },
        },
    }
    mapping.update(overrides)
    return mapping


def config_from(mapping: dict[str, Any]) -> PolicyConfig:
    result = policy_from_mapping(mapping)
    assert result.ok, getattr(result, "message", "")
    return result.config


def url_location(path: str, origin: str = ORIGIN) -> Location:
    return Location(kind="url", value=f"{origin}{path}")


def button(name: str, text: str = "", label: str | None = None) -> Node:
    return Node(ref="n1", role="button", name=name, text=text, label=label)


def build_request(
    mode: str = "replay",
    action: dict[str, Any] | None = None,
    location: Location | None = None,
    target_node: Node | None = None,
    **extra: Any,
) -> PolicyRequest:
    return PolicyRequest(
        mode=mode,
        action=action or {"kind": "click"},
        location=location or url_location("/t/lakeside/inquiry"),
        target_node=target_node,
        **extra,
    )
