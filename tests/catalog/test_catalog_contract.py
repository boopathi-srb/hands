"""The agent-facing tool schema, profile merging, and semver helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from hands.catalog import (
    capability_result_schema,
    capability_tool_schema,
    latest_version,
    merge_profile,
    parse_semver,
    satisfies_range,
    tool_name_for,
)
from hands.core.artifact import SubflowResponse
from hands.core.targets import TargetSpec
from hands.profiles import AppProfile, load_profile

from .fixtures import balance_capability, balance_capability_data, candidate, target

PROFILE_PATH = Path(__file__).resolve().parents[2] / "profiles" / "coreone.yaml"


def coreone_profile() -> AppProfile:
    loaded = load_profile(PROFILE_PATH)
    assert loaded.profile is not None, loaded.error
    return loaded.profile


# ---------------------------------------------------------------- tool schema


def test_tool_schema_has_exactly_the_tool_keys_and_a_closed_input_schema() -> None:
    schema = capability_tool_schema(balance_capability())

    assert set(schema) == {"name", "description", "input_schema"}
    assert schema["name"] == "coreone__member_balance"
    input_schema = schema["input_schema"]
    assert input_schema["type"] == "object"
    assert input_schema["additionalProperties"] is False
    assert input_schema["required"] == ["member_number"]
    member = input_schema["properties"]["member_number"]
    assert member == {"type": "string", "pattern": r"^\d+$", "examples": ["10001"], "description": "Member number"}


def test_tool_description_explains_outputs_outcomes_and_result_statuses() -> None:
    description = capability_tool_schema(balance_capability())["description"]

    assert "Member savings balance" in description
    assert "balance (decimal)" in description
    assert "MEMBER_NOT_FOUND" in description
    assert "business_outcome" in description and "failed" in description
    assert "teller" not in description  # credentials are never part of the caller's contract


def test_tool_schema_types_sensitive_and_optional_inputs() -> None:
    inputs = {
        "count": {"type": "integer", "description": "Count"},
        "amount": {"type": "decimal", "description": "Amount"},
        "flag": {"type": "boolean", "description": "Flag", "required": False},
        "on": {"type": "date", "description": "Date", "required": False},
        "code": {"type": "string", "description": "Code", "sensitive": True},
    }
    data = balance_capability_data()
    data["steps"][1]["value"] = "{{count}}"
    schema = capability_tool_schema(balance_capability(inputs=inputs, steps=data["steps"]))["input_schema"]

    assert schema["properties"]["count"]["type"] == "integer"
    assert schema["properties"]["amount"] == {"type": "string", "pattern": r"^-?\d+(\.\d+)?$", "description": "Amount"}
    assert schema["properties"]["flag"]["type"] == "boolean"
    assert schema["properties"]["on"]["format"] == "date"
    assert "Sensitive" in schema["properties"]["code"]["description"]
    assert schema["required"] == ["count", "amount", "code"]


def test_tool_schema_for_capability_without_inputs() -> None:
    data = balance_capability_data()
    data["steps"] = [step for step in data["steps"] if step["id"] != "type_member"]
    schema = capability_tool_schema(balance_capability(inputs={}, steps=data["steps"]))

    assert schema["input_schema"]["properties"] == {}
    assert schema["input_schema"]["required"] == []


def test_tool_description_flags_risky_steps() -> None:
    data = balance_capability_data()
    data["steps"][2]["risk"] = "risky"
    description = capability_tool_schema(balance_capability(steps=data["steps"]))["description"]

    assert "irreversible steps (search)" in description
    assert "risky_confirmed" in description


def test_result_schema_describes_outputs() -> None:
    schema = capability_result_schema(balance_capability())

    assert schema["required"] == ["balance"]
    assert schema["properties"]["balance"]["type"] == "string"
    assert "1250.00" in schema["properties"]["balance"]["description"]


@pytest.mark.parametrize(
    ("capability_id", "expected"),
    [("coreone.member_balance", "coreone__member_balance"), ("a-b_c", "a-b_c"), ("x" * 80, "x" * 64)],
)
def test_tool_name_for(capability_id: str, expected: str) -> None:
    assert tool_name_for(capability_id) == expected


# ---------------------------------------------------------------- profile merge


def test_merge_profile_adds_runtime_knowledge_the_capability_lacks() -> None:
    data = balance_capability_data()
    data["subflows"] = {}
    data["credentials"] = {}
    data["steps"] = [step for step in data["steps"] if step["id"] != "sign_in"]
    data["steps"][0]["value"] = "{{member_number}}"
    base = balance_capability(**{key: data[key] for key in ("subflows", "credentials", "steps")})

    merged = merge_profile(base, coreone_profile())

    assert "teller" in merged.credentials
    assert "login" in merged.subflows
    assert [detector.code for detector in merged.outcomes] == [
        "MEMBER_NOT_FOUND", "MEMBER_RESTRICTED", "INVALID_MEMBER_NUMBER", "INVALID_DEPOSIT",
    ]
    assert [rule.name for rule in merged.recoveries] == [
        "session_expired", "maintenance_notice", "native_alert", "transient_app_error", "identity_verification",
    ]
    assert base.recoveries == []  # pure: the input is not mutated


def test_merge_profile_capability_wins_on_conflicts() -> None:
    own_rule = {"name": "session_expired", "description": "Own rule",
                "when": {"kind": "text_visible", "pattern": "expired"}, "response": {"kind": "retry"}}
    data = balance_capability_data()
    data["subflows"]["login"].append({"id": "login_extra", "action": "wait", "description": "w",
                                      "until": {"kind": "text_visible", "pattern": "x"}})
    base = balance_capability(recoveries=[own_rule], subflows=data["subflows"])

    merged = merge_profile(base, coreone_profile())

    assert merged.outcomes[0].description == "No such member"
    session_rule = next(rule for rule in merged.recoveries if rule.name == "session_expired")
    assert session_rule.description == "Own rule"
    assert [step.id for step in merged.subflows["login"]][-1] == "login_extra"
    assert merged.credentials["teller"].description == "Teller sign-on"


def test_merge_profile_skips_colliding_subflow_and_the_rules_that_need_it() -> None:
    data = balance_capability_data()
    data["subflows"] = {}
    data["steps"] = [
        {"id": "login_open", "action": "open", "description": "Open", "entry_point": "http://127.0.0.1:8700/x"},
        *[step for step in data["steps"] if step["id"] != "sign_in"],
    ]
    base = balance_capability(subflows={}, steps=data["steps"])

    merged = merge_profile(base, coreone_profile())

    assert "login" not in merged.subflows
    assert all(not isinstance(rule.response, SubflowResponse) for rule in merged.recoveries)
    assert "maintenance_notice" in [rule.name for rule in merged.recoveries]


def test_merge_profile_for_another_product_returns_capability_unchanged() -> None:
    other = coreone_profile().model_copy(update={"product": "OtherCore"})
    base = balance_capability()

    assert merge_profile(base, other) == base


def test_merge_empty_profile_is_identity() -> None:
    empty = AppProfile(vendor="Northwind Core Systems", product="CoreOne", product_versions=["7.4"])
    base = balance_capability()

    assert merge_profile(base, empty) == base


def test_merge_profile_that_would_invalidate_the_capability_returns_it_unchanged() -> None:
    profile = coreone_profile()
    bad_outcome = profile.outcomes[0].model_copy(
        update={
            "code": "NEEDS_UNDECLARED",
            "message_target": TargetSpec.model_validate(target("x", candidate("label", label="{{nope}}"))),
        }
    )
    base = balance_capability()

    merged = merge_profile(base, profile.model_copy(update={"outcomes": [bad_outcome]}))

    assert merged == base


# ---------------------------------------------------------------- versions


def test_parse_semver_and_latest() -> None:
    assert parse_semver("1.10.2") == (1, 10, 2)
    assert parse_semver("1.2") is None
    assert parse_semver(None) is None
    assert parse_semver("") is None
    assert latest_version(["1.2.0", "1.10.0", "bad", "1.9.9"]) == "1.10.0"
    assert latest_version([]) is None


@pytest.mark.parametrize(
    ("version", "version_range", "satisfied"),
    [("1.2.0", ">=1.0.0,<2.0.0", True), ("2.0.0", ">=1.0.0,<2.0.0", False), ("1.0.0", ">1.0.0", False),
     ("1.0.0", "<=1.0.0", True), ("1.0.0", "==1.0.0", True), ("1.0.0", "1.0.0", True), ("1.0.1", "=1.0.0", False),
     ("3.1.4", "*", True), ("3.1.4", "", True), ("3.1.4", None, True)],
)
def test_satisfies_range(version: str, version_range: str | None, satisfied: bool) -> None:
    check = satisfies_range(version, version_range)
    assert check.error is None
    assert check.satisfied is satisfied


def test_satisfies_range_errors() -> None:
    assert satisfies_range("1.0", ">=1.0.0").error
    assert satisfies_range("1.0.0", ">=abc").error
    assert satisfies_range("1.0.0", "~1.0.0").error
