from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from policy_helpers import COREONE_POLICY_PATH, minimal_policy_mapping

from hands.policy import (
    PolicyConfig,
    PolicyLoaded,
    PolicyLoadFailed,
    load_policy,
    parse_policy,
    policy_from_mapping,
)


def _with(path: list[str], value: Any) -> dict[str, Any]:
    """A minimal mapping with one nested key replaced."""
    mapping = copy.deepcopy(minimal_policy_mapping())
    cursor = mapping
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return mapping


# ---------------------------------------------------------------- load_policy


def test_load_policy_reads_the_coreone_policy() -> None:
    result = load_policy(COREONE_POLICY_PATH)
    assert isinstance(result, PolicyLoaded)
    assert result.config.name == "coreone"
    assert result.source == str(COREONE_POLICY_PATH)


def test_load_policy_missing_file(tmp_path: Path) -> None:
    result = load_policy(tmp_path / "absent.yaml")
    assert isinstance(result, PolicyLoadFailed)
    assert result.code == "file_not_found"
    assert result.ok is False


def test_load_policy_directory_is_not_a_file(tmp_path: Path) -> None:
    result = load_policy(tmp_path)
    assert isinstance(result, PolicyLoadFailed) and result.code == "file_not_found"


def test_load_policy_unreadable_bytes(tmp_path: Path) -> None:
    policy_path = tmp_path / "binary.yaml"
    policy_path.write_bytes(b"\xff\xfe\x00bad")
    result = load_policy(policy_path)
    assert isinstance(result, PolicyLoadFailed) and result.code == "unreadable"


def test_load_policy_bad_yaml(tmp_path: Path) -> None:
    policy_path = tmp_path / "bad.yaml"
    policy_path.write_text("name: [unclosed\n  - x: : :", encoding="utf-8")
    result = load_policy(policy_path)
    assert isinstance(result, PolicyLoadFailed) and result.code == "invalid_yaml"


def test_load_policy_invalid_schema(tmp_path: Path) -> None:
    policy_path = tmp_path / "schema.yaml"
    policy_path.write_text("version: 1\nname: x\n", encoding="utf-8")
    result = load_policy(policy_path)
    assert isinstance(result, PolicyLoadFailed) and result.code == "invalid_schema"
    assert "risk" in result.message


def test_load_policy_logs_failures(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    load_policy(tmp_path / "absent.yaml")
    assert "load_policy failed" in caplog.text


# ---------------------------------------------------------------- parse_policy


@pytest.mark.parametrize("text", ["", "   \n", "- a\n- b\n", "just a string"])
def test_parse_policy_rejects_non_mapping_documents(text: str) -> None:
    result = parse_policy(text)
    assert isinstance(result, PolicyLoadFailed) and result.code == "invalid_schema"


def test_parse_policy_accepts_valid_yaml() -> None:
    result = parse_policy(COREONE_POLICY_PATH.read_text(encoding="utf-8"), source="inline")
    assert isinstance(result, PolicyLoaded) and result.source == "inline"


# ---------------------------------------------------------------- schema validation


def test_minimal_policy_is_valid() -> None:
    assert isinstance(policy_from_mapping(minimal_policy_mapping()), PolicyLoaded)


@pytest.mark.parametrize(
    ("path", "value", "message_fragment"),
    [
        (["unknown_key"], True, "unknown_key"),
        (["version"], 2, "version"),
        (["name"], "", "name"),
        (
            ["surfaces", "web", "allowed_origins"],
            ["http://127.0.0.1:8700/path"],
            "bare http(s) origin",
        ),
        (["surfaces", "web", "allowed_origins"], ["127.0.0.1"], "bare http(s) origin"),
        (["surfaces", "web", "allowed_path_patterns"], ["t/lakeside"], "must start with '/'"),
        (["surfaces", "web", "blocked_path_patterns"], ["/x**"], "whole segment"),
        (["surfaces", "web", "allow_all"], True, "allow_all"),
        (["actions", "allowed", "replay"], ["open", "teleport"], "replay"),
        (["actions", "allowed", "robot"], ["click"], "robot"),
        (["risk", "handling", "replay"], "maybe", "replay"),
        (["risk", "default"], "medium", "default"),
    ],
)
def test_invalid_schema_is_reported(path: list[str], value: Any, message_fragment: str) -> None:
    result = policy_from_mapping(_with(path, value))
    assert isinstance(result, PolicyLoadFailed)
    assert result.code == "invalid_schema"
    assert message_fragment in result.message


def test_handling_must_state_every_mode() -> None:
    mapping = _with(["risk", "handling"], {"discovery": "escalate", "replay": "deny"})
    result = policy_from_mapping(mapping)
    assert isinstance(result, PolicyLoadFailed) and "human" in result.message


def test_risk_rule_requires_a_criterion() -> None:
    rules = [{"name": "empty", "description": "matches nothing", "match": {}}]
    result = policy_from_mapping(_with(["risk", "rules"], rules))
    assert isinstance(result, PolicyLoadFailed) and "at least one criterion" in result.message


def test_risk_rule_regex_must_compile() -> None:
    rules = [{"name": "broken", "description": "x", "match": {"control_pattern": "(unclosed"}}]
    result = policy_from_mapping(_with(["risk", "rules"], rules))
    assert isinstance(result, PolicyLoadFailed) and "invalid regex" in result.message


def test_risk_rule_path_patterns_are_validated() -> None:
    rules = [{"name": "paths", "description": "x", "match": {"path_patterns": ["no-slash"]}}]
    result = policy_from_mapping(_with(["risk", "rules"], rules))
    assert isinstance(result, PolicyLoadFailed) and "must start with '/'" in result.message


def test_risk_rule_names_are_unique_slugs() -> None:
    rule = {"name": "dup", "description": "x", "match": {"action_kinds": ["click"]}}
    duplicate = policy_from_mapping(_with(["risk", "rules"], [rule, rule]))
    assert (
        isinstance(duplicate, PolicyLoadFailed) and "duplicate risk rule name" in duplicate.message
    )
    bad_name = policy_from_mapping(_with(["risk", "rules"], [{**rule, "name": "Not A Slug"}]))
    assert isinstance(bad_name, PolicyLoadFailed)


# ---------------------------------------------------------------- defaults and helpers


def test_omitted_sections_are_deny_by_default() -> None:
    mapping = {
        "name": "bare",
        "risk": {"handling": {"discovery": "deny", "replay": "deny", "human": "deny"}},
    }
    result = policy_from_mapping(mapping)
    assert isinstance(result, PolicyLoaded)
    config = result.config
    assert config.surfaces.web.allowed_origins == []
    assert config.surfaces.desktop.allowed_bundle_ids == []
    assert config.surfaces.start_locations == ["about:blank"]
    assert config.actions.allowed.for_mode("replay") == []
    assert config.risk.default == "safe"


def test_origins_are_normalized_on_load() -> None:
    result = policy_from_mapping(
        _with(["surfaces", "web", "allowed_origins"], ["HTTP://LocalHost:8700/"])
    )
    assert isinstance(result, PolicyLoaded)
    assert result.config.surfaces.web.allowed_origins == ["http://localhost:8700"]


def test_for_mode_helpers(coreone_config: PolicyConfig) -> None:
    assert "open" not in coreone_config.actions.allowed.for_mode("human")
    assert coreone_config.risk.handling.for_mode("discovery") == "escalate"
    assert coreone_config.risk.handling.for_mode("replay") == "allow_if_approved_and_confirmed"
    assert coreone_config.risk.handling.for_mode("human") == "allow"


def test_config_is_immutable(coreone_config: PolicyConfig) -> None:
    with pytest.raises(Exception):  # noqa: B017 - pydantic raises ValidationError for frozen models
        coreone_config.name = "changed"  # type: ignore[misc]


def test_coreone_policy_contents(coreone_config: PolicyConfig) -> None:
    web = coreone_config.surfaces.web
    assert web.allowed_origins == ["http://127.0.0.1:8700"]
    assert "/t/lakeside/**" in web.allowed_path_patterns
    assert "/t/prairie/**" in web.allowed_path_patterns
    assert "/_admin/**" in web.blocked_path_patterns
    assert coreone_config.surfaces.desktop.allowed_bundle_ids == ["com.apple.calculator"]
    assert [rule.name for rule in coreone_config.risk.rules] == [
        "irreversible-controls",
        "review-page-commit",
    ]
