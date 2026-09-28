"""Tests for the Capability validators in hands.core.artifact."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from hands.core.artifact import (
    PLACEHOLDER_PATTERN,
    Capability,
    iter_all_steps,
    placeholders_in,
)

SEARCH_BUTTON_TARGET: dict[str, Any] = {
    "description": "Search button",
    "candidates": [
        {
            "kind": "role_name",
            "role": "button",
            "name": "Search",
            "confidence": 0.9,
            "reason": "unique button",
        }
    ],
}
MEMBER_FIELD_TARGET: dict[str, Any] = {
    "description": "Member number field",
    "candidates": [
        {
            "kind": "label",
            "label": "Member Number",
            "role": "textbox",
            "confidence": 0.85,
            "reason": "label cell",
        }
    ],
}
BALANCE_TARGET: dict[str, Any] = {
    "description": "Regular Savings balance",
    "candidates": [
        {
            "kind": "text_anchor",
            "anchor_text": "Regular Savings",
            "relation": "right_of",
            "role": "cell",
            "confidence": 0.7,
            "reason": "row anchor",
        },
        {
            "kind": "structural",
            "container_path": ["frame:content"],
            "structural_path": "table[2]/row[2]/cell[3]",
            "confidence": 0.5,
            "reason": "stable legacy layout",
        },
    ],
}


def minimal_capability_data() -> dict[str, Any]:
    return {
        "id": "coreone.open_page",
        "version": "1.0.0",
        "title": "Open inquiry",
        "description": "Opens the member inquiry page.",
        "app": {
            "vendor": "Northwind Core Systems",
            "product": "CoreOne",
            "product_version": "7.4",
            "surface": "web",
        },
        "steps": [
            {
                "id": "open",
                "action": "open",
                "description": "Open",
                "entry_point": "http://127.0.0.1:8000/",
            }
        ],
        "checkpoint": {"kind": "text_visible", "pattern": "Member Inquiry"},
        "provenance": {
            "discovery_run_id": "run-1",
            "recorded_at": datetime(2026, 9, 28, tzinfo=UTC).isoformat(),
            "planner": "scripted",
            "goal": "open the inquiry page",
        },
    }


def full_capability_data() -> dict[str, Any]:
    data = minimal_capability_data()
    data.update(
        {
            "id": "coreone.member_balance",
            "inputs": {
                "member_number": {
                    "type": "string",
                    "description": "Member number",
                    "pattern": r"^\d+$",
                }
            },
            "outputs": {"balance": {"type": "decimal", "description": "Regular Savings balance"}},
            "credentials": {"teller": {"description": "Teller sign-on"}},
            "steps": [
                {
                    "id": "open",
                    "action": "open",
                    "description": "Open",
                    "entry_point": "http://127.0.0.1:8000/",
                },
                {
                    "id": "type-user",
                    "action": "type",
                    "description": "User",
                    "target": MEMBER_FIELD_TARGET,
                    "value": "{{teller.username}}",
                },
                {
                    "id": "type-member",
                    "action": "type",
                    "description": "Member",
                    "target": MEMBER_FIELD_TARGET,
                    "value": "{{ member_number }}",
                    "recoveries": ["session-expired"],
                },
                {
                    "id": "search",
                    "action": "click",
                    "description": "Search",
                    "target": SEARCH_BUTTON_TARGET,
                },
                {
                    "id": "read-balance",
                    "action": "extract",
                    "description": "Balance",
                    "target": BALANCE_TARGET,
                    "output": "balance",
                },
            ],
            "checkpoint": {
                "kind": "all_of",
                "conditions": [
                    {"kind": "location_matches", "pattern": "/t/:tenant/member/:id"},
                    {
                        "kind": "not",
                        "condition": {"kind": "text_visible", "pattern": "ACCESS DENIED"},
                    },
                ],
            },
            "outcomes": [
                {
                    "code": "MEMBER_NOT_FOUND",
                    "description": "No such member",
                    "when": {
                        "kind": "text_visible",
                        "pattern": "No member found for number {{member_number}}",
                    },
                }
            ],
            "recoveries": [
                {
                    "name": "session-expired",
                    "description": "Sign on again",
                    "when": {"kind": "text_visible", "pattern": "session has expired"},
                    "response": {"kind": "subflow", "subflow": "sign-on"},
                    "scope": "step",
                }
            ],
            "subflows": {
                "sign-on": [
                    {
                        "id": "sign-on-password",
                        "action": "type",
                        "description": "Password",
                        "target": MEMBER_FIELD_TARGET,
                        "value": "{{teller.password}}",
                    }
                ]
            },
        }
    )
    return data


def build(data: dict[str, Any]) -> Capability:
    return Capability.model_validate(data)


# ---------------------------------------------------------------- valid capabilities


def test_valid_minimal_capability() -> None:
    capability = build(minimal_capability_data())
    assert capability.status == "draft"
    assert capability.schema_version == "1.0"
    assert capability.stats.runs == 0
    assert [step.id for step in capability.steps] == ["open"]


def test_valid_full_capability_with_subflows_outcomes_and_credentials() -> None:
    capability = build(full_capability_data())
    assert [step.id for step in iter_all_steps(capability)][-1] == "sign-on-password"


def test_json_round_trip_is_lossless() -> None:
    capability = build(full_capability_data())
    restored = Capability.model_validate_json(capability.model_dump_json())
    assert restored == capability
    assert json.loads(restored.model_dump_json()) == json.loads(capability.model_dump_json())


def test_json_schema_export() -> None:
    schema = Capability.model_json_schema()
    assert schema["title"] == "Capability"
    assert {"id", "version", "steps", "checkpoint", "provenance"} <= set(schema["required"])
    assert "$defs" in schema and "TargetSpec" in schema["$defs"]
    json.dumps(schema)  # serializable


# ---------------------------------------------------------------- validators


def test_duplicate_step_ids_rejected() -> None:
    data = minimal_capability_data()
    data["steps"].append(dict(data["steps"][0]))
    with pytest.raises(ValidationError, match="duplicate step id 'open'"):
        build(data)


def test_duplicate_step_id_between_main_flow_and_subflow_rejected() -> None:
    data = full_capability_data()
    data["subflows"]["sign-on"][0]["id"] = "search"
    with pytest.raises(ValidationError, match="duplicate step id 'search'"):
        build(data)


def test_undeclared_input_placeholder_rejected() -> None:
    data = full_capability_data()
    data["steps"][2]["value"] = "{{member_id}}"
    with pytest.raises(
        ValidationError, match="placeholder '\\{\\{member_id\\}\\}' is not a declared"
    ):
        build(data)


def test_undeclared_placeholder_in_outcome_rejected() -> None:
    data = full_capability_data()
    data["outcomes"][0]["when"]["pattern"] = "No member {{nope}}"
    with pytest.raises(ValidationError, match="nope"):
        build(data)


def test_undeclared_placeholder_in_checkpoint_rejected() -> None:
    data = minimal_capability_data()
    data["checkpoint"] = {"kind": "text_visible", "pattern": "{{ghost}}"}
    with pytest.raises(ValidationError, match="ghost"):
        build(data)


def test_declared_credential_placeholder_accepted() -> None:
    data = full_capability_data()
    data["steps"][1]["value"] = "{{teller.password}}"
    capability = build(data)
    assert capability.credentials["teller"].fields == ["username", "password"]


@pytest.mark.parametrize("placeholder", ["{{teller.pin}}", "{{operator.password}}", "{{teller}}"])
def test_undeclared_credential_placeholder_rejected(placeholder: str) -> None:
    data = full_capability_data()
    data["steps"][1]["value"] = placeholder
    with pytest.raises(ValidationError, match="is not a declared input or credential field"):
        build(data)


def test_credential_placeholder_rejected_when_no_credentials_declared() -> None:
    data = minimal_capability_data()
    data["steps"].append(
        {
            "id": "pw",
            "action": "type",
            "description": "pw",
            "target": MEMBER_FIELD_TARGET,
            "value": "{{teller.password}}",
        }
    )
    with pytest.raises(ValidationError, match="teller.password"):
        build(data)


def test_output_never_extracted_rejected() -> None:
    data = minimal_capability_data()
    data["outputs"] = {"balance": {"type": "decimal", "description": "balance"}}
    with pytest.raises(ValidationError, match="declared output 'balance' is never extracted"):
        build(data)


def test_extract_of_undeclared_output_rejected() -> None:
    data = full_capability_data()
    data["outputs"] = {}
    with pytest.raises(ValidationError, match="extract step fills undeclared output 'balance'"):
        build(data)


def test_unknown_step_recovery_rejected() -> None:
    data = full_capability_data()
    data["steps"][2]["recoveries"] = ["printer-alert"]
    with pytest.raises(ValidationError, match="unknown recovery 'printer-alert'"):
        build(data)


def test_unknown_subflow_step_rejected() -> None:
    data = minimal_capability_data()
    data["steps"].append(
        {"id": "relogin", "action": "subflow", "description": "x", "subflow": "sign-on"}
    )
    with pytest.raises(ValidationError, match="unknown subflow 'sign-on'"):
        build(data)


def test_unknown_subflow_in_recovery_response_rejected() -> None:
    data = full_capability_data()
    data["subflows"] = {}
    with pytest.raises(
        ValidationError, match="recovery 'session-expired' references unknown subflow 'sign-on'"
    ):
        build(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", "Bad Id"), ("version", "1.0"), ("steps", [])],
)
def test_field_constraints(field: str, value: Any) -> None:
    data = minimal_capability_data()
    data[field] = value
    with pytest.raises(ValidationError):
        build(data)


def test_placeholders_in_helper() -> None:
    assert placeholders_in("{{a}} and {{ teller.password }} and {{a.b.c}}") == [
        "a",
        "teller.password",
    ]
    assert placeholders_in("") == []
    assert PLACEHOLDER_PATTERN.fullmatch("{{x}}") is not None


# ---------------------------------------------------------------- reference validation


def test_duplicate_recovery_names_rejected() -> None:
    data = full_capability_data()
    data["recoveries"].append(dict(data["recoveries"][0]))
    with pytest.raises(ValidationError):
        build(data)


def test_outcome_scope_with_unknown_step_rejected() -> None:
    data = full_capability_data()
    data["outcomes"][0]["scope"] = ["no-such-step"]
    with pytest.raises(ValidationError):
        build(data)
