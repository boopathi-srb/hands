from __future__ import annotations

import pytest
from pydantic import ValidationError

from hands.discovery.planner import (
    MAX_RATIONALE_CHARS,
    PLANNER_ACTIONS,
    HistoryEntry,
    InputHint,
    PlannerDecision,
    decision_json_schema,
    parse_decision_payload,
    parse_decision_text,
)
from hands.discovery.prompts import SYSTEM_PROMPT, build_user_prompt, format_history_entry

from .helpers import planner_context


def test_schema_is_strict_and_complete() -> None:
    schema = decision_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(schema["properties"])
    assert schema["properties"]["action"]["enum"] == list(PLANNER_ACTIONS)
    assert next(iter(schema["properties"])) == "rationale"
    assert "$defs" not in schema


def test_parse_plain_json() -> None:
    parsed = parse_decision_text('{"rationale": "go", "action": "click", "node_ref": "n3"}')
    assert parsed.error is None
    assert parsed.decision == PlannerDecision(rationale="go", action="click", node_ref="n3")


def test_parse_tolerates_fences_and_prose() -> None:
    parsed = parse_decision_text('Sure:\n```json\n{"rationale": "r", "action": "done"}\n```')
    assert parsed.decision is not None and parsed.decision.action == "done"


@pytest.mark.parametrize("raw_text", ["", "   ", "no json here"])
def test_parse_without_json_is_an_error(raw_text: str) -> None:
    parsed = parse_decision_text(raw_text)
    assert parsed.decision is None
    assert parsed.error == "no JSON object found in the model output"


def test_parse_invalid_json_is_an_error() -> None:
    parsed = parse_decision_text('{"rationale": "r", "action": }')
    assert parsed.decision is None and parsed.error is not None and "invalid JSON" in parsed.error


def test_parse_rejects_unknown_action_and_extra_keys() -> None:
    assert parse_decision_text('{"rationale": "r", "action": "fill"}').error is not None
    extra = parse_decision_text('{"rationale": "r", "action": "done", "confidence": 1}')
    assert extra.error is not None and "confidence" in extra.error


def test_parse_payload_requires_an_object() -> None:
    assert parse_decision_payload(["done"]).error == "expected a JSON object, got list"


def test_missing_rationale_is_rejected() -> None:
    assert parse_decision_payload({"action": "done"}).error is not None


def test_decision_normalizes_text_fields() -> None:
    decision = PlannerDecision(rationale="  a \n b " + "x" * 400, action="click", node_ref="", value="")
    assert decision.rationale.startswith("a b")
    assert len(decision.rationale) == MAX_RATIONALE_CHARS
    assert decision.node_ref is None and decision.value is None


def test_decision_is_frozen() -> None:
    decision = PlannerDecision(rationale="r", action="done")
    with pytest.raises(ValidationError):
        decision.action = "stuck"  # type: ignore[misc]


def test_user_prompt_contains_goal_placeholders_history_and_screen() -> None:
    context = planner_context(
        "[n1] button \"Search\"",
        goal="Find member",
        inputs=[InputHint(name="member_number", example="10001")],
        credential_placeholders=["{{teller.password}}"],
        history=[HistoryEntry(step=1, action="type", node_ref="n2", target='textbox "User ID"',
                              value="{{teller.username}}", result="ok")],
        extracted={"balance": "1.00"},
        feedback="node_ref 'n9' is not on the current SCREEN",
    )
    prompt = build_user_prompt(context)
    assert "GOAL: Find member" in prompt
    assert "{{member_number}} (this run: 10001)" in prompt
    assert "{{teller.password}}" in prompt
    assert "EXTRACTED: balance = 1.00" in prompt
    assert "FEEDBACK ON YOUR LAST ANSWER" in prompt
    assert prompt.index("SCREEN:") > prompt.index("HISTORY:")
    assert "1. type [n2] textbox \"User ID\" value='{{teller.username}}' -> ok" in prompt


def test_user_prompt_with_minimal_context() -> None:
    prompt = build_user_prompt(planner_context("LOCATION: about:blank"))
    assert "EXTRACTED: nothing yet" in prompt
    assert "HISTORY" not in prompt and "INPUTS" not in prompt and "FEEDBACK" not in prompt


def test_format_history_entry_without_optional_parts() -> None:
    assert format_history_entry(HistoryEntry(step=3, action="press", result="ok")) == "3. press -> ok"


def test_system_prompt_is_short_and_names_every_action() -> None:
    assert len(SYSTEM_PROMPT) < 2500
    for action in PLANNER_ACTIONS:
        assert f"- {action}:" in SYSTEM_PROMPT
