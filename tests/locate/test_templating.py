from __future__ import annotations

import logging

import pytest

from hands.core.artifact import PLACEHOLDER_PATTERN
from hands.core.conditions import (
    AllOf,
    AnyOf,
    DialogOpen,
    LocationMatches,
    NodePresent,
    Not,
    TextVisible,
    ValueMatches,
)
from hands.core.targets import (
    LabelCandidate,
    RoleNameCandidate,
    StructuralCandidate,
    TargetSpec,
    TextAnchorCandidate,
    VisualAnchorCandidate,
)
from hands.locate import (
    FillResult,
    apply_aliases,
    fill_condition,
    fill_placeholders,
    fill_target,
)

LAKESIDE_TO_PRAIRIE = {
    "Regular Savings": "Share Savings",
    "Member Number": "Account Number",
    "Search": "Find",
}


def spec_with_every_candidate_kind() -> TargetSpec:
    return TargetSpec(
        description="{{share}} balance",
        candidates=[
            RoleNameCandidate(role="button", name="Search", confidence=0.9, reason="r"),
            LabelCandidate(label="Member Number", role="textbox", confidence=0.85, reason="r"),
            TextAnchorCandidate(
                anchor_text="{{share}}",
                relation="right_of",
                role="cell",
                confidence=0.7,
                reason="r",
            ),
            StructuralCandidate(
                container_path=("frame:{{frame}}",),
                structural_path="table[2]/row[2]",
                confidence=0.5,
                reason="r",
            ),
            VisualAnchorCandidate(
                anchor_text="Regular Savings", dx=100, dy=0, confidence=0.3, reason="r"
            ),
        ],
    )


# ---------------------------------------------------------------- fill_placeholders


def test_fill_placeholders_replaces_inputs_and_credentials() -> None:
    result = fill_placeholders(
        "{{ member_number }} by {{teller.username}}",
        {"member_number": "10001", "teller.username": "teller1"},
    )
    assert result == FillResult(text="10001 by teller1", missing=[])


def test_fill_placeholders_reports_missing_once_in_order_and_keeps_placeholder() -> None:
    result = fill_placeholders("{{b}} {{a}} {{b}} {{c}}", {"c": "3"})
    assert result.text == "{{b}} {{a}} {{b}} 3"
    assert result.missing == ["b", "a"]


@pytest.mark.parametrize(
    "text", ["", "no placeholders here", "{single braces}", "{{}}", "{{1bad}}"]
)
def test_fill_placeholders_leaves_non_placeholders_alone(text: str) -> None:
    assert fill_placeholders(text, {"x": "y"}) == FillResult(text=text, missing=[])


def test_fill_placeholders_empty_params_reports_everything_missing() -> None:
    assert fill_placeholders("{{x}}", {}).missing == ["x"]


def test_fill_placeholders_does_not_escape_plain_values() -> None:
    assert fill_placeholders("{{v}}", {"v": "a.b*(c)"}).text == "a.b*(c)"


def test_fill_placeholders_uses_core_pattern_one_dotted_segment_only() -> None:
    assert PLACEHOLDER_PATTERN.findall("{{teller.password}}") == ["teller.password"]
    result = fill_placeholders(
        "{{a.b.c}} {{teller.password}}", {"teller.password": "demo-only-password"}
    )
    assert result == FillResult(text="{{a.b.c}} demo-only-password", missing=[])


# ---------------------------------------------------------------- apply_aliases


def test_apply_aliases_tenant_labels() -> None:
    assert apply_aliases("Member Number", LAKESIDE_TO_PRAIRIE) == "Account Number"
    assert (
        apply_aliases("Balance of Regular Savings", LAKESIDE_TO_PRAIRIE)
        == "Balance of Share Savings"
    )


def test_apply_aliases_longest_first_and_single_pass() -> None:
    aliases = {"Savings": "Thrift", "Regular Savings": "Share Savings"}
    assert apply_aliases("Regular Savings and Savings", aliases) == "Share Savings and Thrift"


def test_apply_aliases_does_not_realias_replacements() -> None:
    assert apply_aliases("A", {"A": "B", "B": "C"}) == "B"


@pytest.mark.parametrize(("text", "aliases"), [("", LAKESIDE_TO_PRAIRIE), ("Member Number", {})])
def test_apply_aliases_empty_inputs(text: str, aliases: dict[str, str]) -> None:
    assert apply_aliases(text, aliases) == text


def test_apply_aliases_ignores_and_logs_empty_key(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        assert apply_aliases("Search", {"": "X", "Search": "Find"}) == "Find"
    assert "empty alias key ignored" in caplog.text


def test_apply_aliases_is_case_sensitive_exact_substring() -> None:
    assert apply_aliases("member number", LAKESIDE_TO_PRAIRIE) == "member number"


# ---------------------------------------------------------------- fill_target


def test_fill_target_templates_and_aliases_every_candidate_kind() -> None:
    original = spec_with_every_candidate_kind()
    filled = fill_target(
        original, {"share": "Regular Savings", "frame": "content"}, LAKESIDE_TO_PRAIRIE
    )
    role_name, label, text_anchor, structural, visual = filled.candidates
    assert filled.description == "Regular Savings balance"  # params are not aliased
    assert isinstance(role_name, RoleNameCandidate) and role_name.name == "Find"
    assert isinstance(label, LabelCandidate) and label.label == "Account Number"
    assert (
        isinstance(text_anchor, TextAnchorCandidate)
        and text_anchor.anchor_text == "Regular Savings"
    )
    assert isinstance(structural, StructuralCandidate) and structural.container_path == (
        "frame:content",
    )
    assert isinstance(visual, VisualAnchorCandidate) and visual.anchor_text == "Share Savings"
    assert [candidate.kind for candidate in filled.candidates] == [
        c.kind for c in original.candidates
    ]


def test_fill_target_does_not_mutate_original() -> None:
    original = spec_with_every_candidate_kind()
    snapshot = original.model_dump()
    fill_target(original, {"share": "X", "frame": "content"}, LAKESIDE_TO_PRAIRIE)
    assert original.model_dump() == snapshot


def test_fill_target_missing_placeholder_left_in_place_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        filled = fill_target(spec_with_every_candidate_kind(), {}, {})
    assert filled.description == "{{share}} balance"
    assert "placeholders have no value" in caplog.text


def test_fill_target_with_empty_params_and_aliases_is_identity() -> None:
    spec = TargetSpec(
        description="Search",
        candidates=[RoleNameCandidate(role="button", name="Search", confidence=0.9, reason="")],
    )
    assert fill_target(spec, {}, {}) == spec


# ---------------------------------------------------------------- fill_condition


def search_target() -> TargetSpec:
    return TargetSpec(
        description="search",
        candidates=[RoleNameCandidate(role="button", name="Search", confidence=0.9, reason="r")],
    )


def test_fill_condition_text_visible_plain_is_not_escaped() -> None:
    condition = TextVisible(pattern="No member found for number {{n}}.")
    filled = fill_condition(condition, {"n": "1.5"}, {})
    assert isinstance(filled, TextVisible) and filled.pattern == "No member found for number 1.5."


def test_fill_condition_text_visible_regex_escapes_values_and_aliases() -> None:
    condition = TextVisible(pattern=r"Regular Savings .* {{amount}}", regex=True)
    filled = fill_condition(
        condition, {"amount": "1,250.00"}, {"Regular Savings": "Share (Savings)"}
    )
    assert isinstance(filled, TextVisible)
    assert filled.pattern == r"Share\ \(Savings\) .* 1,250\.00"


def test_fill_condition_node_present_fills_target() -> None:
    filled = fill_condition(NodePresent(target=search_target()), {}, LAKESIDE_TO_PRAIRIE)
    assert isinstance(filled, NodePresent)
    candidate = filled.target.candidates[0]
    assert isinstance(candidate, RoleNameCandidate) and candidate.name == "Find"


def test_fill_condition_location_escapes_only_title_regex() -> None:
    condition = LocationMatches(pattern="/t/{{tenant}}/member/:id", title_pattern="Member {{n}}")
    filled = fill_condition(condition, {"tenant": "prairie", "n": "1+1"}, {})
    assert isinstance(filled, LocationMatches)
    assert filled.pattern == "/t/prairie/member/:id"
    assert filled.title_pattern == r"Member 1\+1"


def test_fill_condition_location_keeps_none_fields() -> None:
    filled = fill_condition(LocationMatches(), {"a": "b"}, LAKESIDE_TO_PRAIRIE)
    assert filled == LocationMatches()


def test_fill_condition_dialog_open_escapes_values() -> None:
    filled = fill_condition(
        DialogOpen(title_pattern="{{t}}", text_pattern=None), {"t": "Notice?"}, {}
    )
    assert isinstance(filled, DialogOpen)
    assert filled.title_pattern == r"Notice\?"
    assert filled.text_pattern is None


def test_fill_condition_value_matches_escapes_pattern_and_fills_target() -> None:
    condition = ValueMatches(target=search_target(), pattern="^{{n}}$")
    filled = fill_condition(condition, {"n": "10.01"}, LAKESIDE_TO_PRAIRIE)
    assert isinstance(filled, ValueMatches)
    assert filled.pattern == r"^10\.01$"
    candidate = filled.target.candidates[0]
    assert isinstance(candidate, RoleNameCandidate) and candidate.name == "Find"


def test_fill_condition_nested_composites() -> None:
    condition = AllOf(
        conditions=[
            AnyOf(
                conditions=[
                    TextVisible(pattern="Member Number"),
                    Not(condition=TextVisible(pattern="{{x}}")),
                ]
            ),
            NodePresent(target=search_target()),
        ]
    )
    filled = fill_condition(condition, {"x": "Regular Savings"}, LAKESIDE_TO_PRAIRIE)
    assert isinstance(filled, AllOf)
    any_of = filled.conditions[0]
    assert isinstance(any_of, AnyOf)
    first, negation = any_of.conditions
    assert isinstance(first, TextVisible) and first.pattern == "Account Number"
    assert isinstance(negation, Not)
    assert isinstance(negation.condition, TextVisible)
    assert negation.condition.pattern == "Regular Savings"
