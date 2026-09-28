from __future__ import annotations

import logging
import re

import pytest

from hands.core.conditions import (
    AllOf,
    AnyOf,
    Condition,
    DialogOpen,
    LocationMatches,
    NodePresent,
    Not,
    TextVisible,
    ValueMatches,
)
from hands.core.observation import Location
from hands.core.targets import LabelCandidate, RoleNameCandidate, TargetSpec
from hands.locate import ConditionResult, evaluate
from hands.locate.evaluate import compile_pattern, location_pattern_to_regex

from .fixtures import (
    desktop_window_observation,
    empty_observation,
    login_observation,
    maintenance_modal_observation,
    make_node,
    make_observation,
    member_detail_observation,
    native_alert_observation,
)


def target(role: str, name: str) -> TargetSpec:
    return TargetSpec(
        description=f"{role} {name}",
        candidates=[RoleNameCandidate(role=role, name=name, confidence=0.9, reason="test")],
    )


def test_condition_result_model() -> None:
    assert ConditionResult(met=True, detail="ok").model_dump() == {"met": True, "detail": "ok"}


# ---------------------------------------------------------------- text_visible


def test_text_visible_plain_substring_case_insensitive() -> None:
    result = evaluate(TextVisible(pattern="regular   SAVINGS"), member_detail_observation())
    assert result.met
    assert "found in table node s0" in result.detail  # first haystack in node order


def test_text_visible_case_sensitive() -> None:
    observation = member_detail_observation()
    assert not evaluate(
        TextVisible(pattern="regular savings", case_sensitive=True), observation
    ).met
    assert evaluate(TextVisible(pattern="Regular Savings", case_sensitive=True), observation).met


def test_text_visible_regex() -> None:
    observation = member_detail_observation()
    assert evaluate(TextVisible(pattern=r"^1,250\.\d{2}$", regex=True), observation).met
    assert not evaluate(TextVisible(pattern=r"^9,999\.\d{2}$", regex=True), observation).met


def test_text_visible_regex_case_flags() -> None:
    observation = member_detail_observation()
    assert evaluate(TextVisible(pattern="HOLIDAY", regex=True), observation).met
    assert not evaluate(
        TextVisible(pattern="HOLIDAY", regex=True, case_sensitive=True), observation
    ).met


def test_text_visible_searches_values_and_dialogs() -> None:
    typed = make_node("t", "textbox", value="10001")
    assert evaluate(TextVisible(pattern="10001"), make_observation([typed])).met
    assert evaluate(TextVisible(pattern="printer queue offline"), native_alert_observation()).met


def test_text_visible_not_met_detail() -> None:
    result = evaluate(TextVisible(pattern="ACCESS DENIED"), member_detail_observation())
    assert not result.met
    assert "not found" in result.detail and "0 dialogs" in result.detail


def test_text_visible_invalid_regex_is_logged_and_unmet(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        result = evaluate(
            TextVisible(pattern="([unclosed", regex=True), member_detail_observation()
        )
    assert not result.met
    assert "not a valid regular expression" in result.detail
    assert "invalid regex" in caplog.text


def test_text_visible_empty_pattern_and_empty_observation() -> None:
    assert not evaluate(TextVisible(pattern=""), member_detail_observation()).met
    assert not evaluate(TextVisible(pattern="anything"), empty_observation()).met


# ---------------------------------------------------------------- node_present


def test_node_present_met_and_unmet() -> None:
    observation = member_detail_observation()
    met = evaluate(NodePresent(target=target("link", "Reports")), observation)
    assert met.met and "via role_name at rank 0" in met.detail
    unmet = evaluate(NodePresent(target=target("button", "Submit")), observation)
    assert not unmet.met and "no candidate" in unmet.detail


def test_node_present_on_empty_observation() -> None:
    assert not evaluate(NodePresent(target=target("link", "Reports")), empty_observation()).met


# ---------------------------------------------------------------- location_matches


@pytest.mark.parametrize(
    ("pattern", "url", "expected"),
    [
        ("/t/:tenant/member/:id", "http://127.0.0.1:8000/t/lakeside/member/10001", True),
        (
            "/t/:tenant/member/:id",
            "http://127.0.0.1:8000/t/lakeside/member/10001/open-share",
            False,
        ),
        (
            "/t/:tenant/member/:id/*",
            "http://127.0.0.1:8000/t/lakeside/member/10001/open-share",
            True,
        ),
        ("/t/:tenant/member/:id/*", "http://127.0.0.1:8000/t/lakeside/member/10001", True),
        ("*/member/:id", "https://core.example/t/prairie/member/10002?x=1#top", True),
        ("/t/:tenant/login", "http://127.0.0.1:8000/t/lakeside/login?next=/main", True),
        ("/t/:tenant/login", "http://127.0.0.1:8000/t/lakeside/LOGIN", False),
        ("/t/:tenant/member/:id", "http://127.0.0.1:8000/t/lakeside/member/", False),
        ("/", "http://127.0.0.1:8000", True),
    ],
)
def test_location_path_patterns(pattern: str, url: str, expected: bool) -> None:
    result = evaluate(LocationMatches(pattern=pattern), make_observation([], url=url))
    assert result.met is expected, result.detail


def test_location_title_pattern_regex_case_insensitive() -> None:
    observation = member_detail_observation()
    assert evaluate(LocationMatches(title_pattern="member detail$"), observation).met
    assert not evaluate(LocationMatches(title_pattern="^Sign On"), observation).met


def test_location_pattern_and_title_both_required() -> None:
    observation = member_detail_observation()
    both = LocationMatches(pattern="/t/:tenant/member/:id", title_pattern="Member Detail")
    assert evaluate(both, observation).met
    wrong_title = LocationMatches(pattern="/t/:tenant/member/:id", title_pattern="Inquiry")
    result = evaluate(wrong_title, observation)
    assert not result.met and "does not match" in result.detail


def test_location_with_no_patterns_is_met() -> None:
    assert evaluate(LocationMatches(), empty_observation()).met


def test_location_window_kind_matches_title() -> None:
    observation = desktop_window_observation()
    assert evaluate(LocationMatches(pattern="member inquiry*"), observation).met
    assert not evaluate(LocationMatches(pattern="Member Detail*"), observation).met


def test_location_invalid_title_regex_is_unmet(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        result = evaluate(LocationMatches(title_pattern="(("), member_detail_observation())
    assert not result.met and "not a valid regular expression" in result.detail


def test_location_pattern_to_regex_translation() -> None:
    compiled = location_pattern_to_regex("/member/:id/*", case_sensitive=True)
    assert compiled.fullmatch("/member/10001")
    assert compiled.fullmatch("/member/10001/open-share/review")
    assert not compiled.fullmatch("/member")
    assert location_pattern_to_regex("/a.b", case_sensitive=True).fullmatch("/axb") is None
    assert location_pattern_to_regex("/Member", case_sensitive=False).fullmatch("/member")


def test_location_empty_title_window() -> None:
    observation = make_observation([], location=Location(kind="window", value="com.x", title=""))
    assert not evaluate(LocationMatches(pattern="Member*"), observation).met


# ---------------------------------------------------------------- dialog_open


def test_dialog_open_by_title_and_text() -> None:
    observation = maintenance_modal_observation()
    assert evaluate(DialogOpen(title_pattern="system notice"), observation).met
    assert evaluate(DialogOpen(title_pattern="Notice", text_pattern="maintenance"), observation).met
    assert not evaluate(
        DialogOpen(title_pattern="Notice", text_pattern="identity"), observation
    ).met


def test_dialog_open_any_dialog_when_no_patterns() -> None:
    assert evaluate(DialogOpen(), native_alert_observation()).met
    result = evaluate(DialogOpen(), member_detail_observation())
    assert not result.met and "open dialogs: []" in result.detail


def test_dialog_open_native_alert_by_text() -> None:
    assert evaluate(DialogOpen(text_pattern="Printer queue"), native_alert_observation()).met


def test_dialog_open_invalid_pattern(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        result = evaluate(DialogOpen(text_pattern="[bad"), native_alert_observation())
    assert not result.met


# ---------------------------------------------------------------- value_matches


def test_value_matches_uses_value_then_text() -> None:
    field = make_node("f", "textbox", label="Member Number", value="10001", box=(0, 0, 100, 20))
    observation = make_observation([field])
    field_target = TargetSpec(
        description="member field",
        candidates=[LabelCandidate(label="Member Number", confidence=0.85, reason="test")],
    )
    assert evaluate(ValueMatches(target=field_target, pattern=r"^\d{5}$"), observation).met
    balance = target("cell", "Holiday Club")
    assert evaluate(
        ValueMatches(target=balance, pattern="^Holiday"), member_detail_observation()
    ).met


def test_value_matches_mismatch_detail_shows_observed() -> None:
    result = evaluate(
        ValueMatches(target=target("cell", "Checking"), pattern="^Savings$"),
        member_detail_observation(),
    )
    assert not result.met
    assert "'Checking'" in result.detail and "does not match" in result.detail


def test_value_matches_target_missing_or_invalid_regex(caplog: pytest.LogCaptureFixture) -> None:
    observation = member_detail_observation()
    missing = evaluate(ValueMatches(target=target("cell", "Nope"), pattern="x"), observation)
    assert not missing.met and "not found" in missing.detail
    with caplog.at_level(logging.ERROR):
        invalid = evaluate(
            ValueMatches(target=target("cell", "Checking"), pattern="(x"), observation
        )
    assert not invalid.met


def test_value_matches_empty_value() -> None:
    observation = login_observation()
    field_target = TargetSpec(
        description="user id",
        candidates=[LabelCandidate(label="User ID", confidence=0.85, reason="test")],
    )
    assert evaluate(ValueMatches(target=field_target, pattern="^$"), observation).met
    assert not evaluate(ValueMatches(target=field_target, pattern="."), observation).met


# ---------------------------------------------------------------- composites


def test_all_of_any_of_not_nested() -> None:
    observation = maintenance_modal_observation()
    notice_blocks_work: Condition = AllOf(
        conditions=[
            DialogOpen(title_pattern="System Notice"),
            AnyOf(
                conditions=[
                    TextVisible(pattern="ACCESS DENIED"),
                    NodePresent(target=target("button", "Acknowledge")),
                ]
            ),
            Not(condition=TextVisible(pattern="Internal Error")),
        ]
    )
    result = evaluate(notice_blocks_work, observation)
    assert result.met
    assert result.detail.startswith("all_of:")


def test_all_of_reports_first_unmet_child() -> None:
    condition = AllOf(
        conditions=[TextVisible(pattern="Checking"), TextVisible(pattern="Money Market")]
    )
    result = evaluate(condition, member_detail_observation())
    assert not result.met and "condition [1] unmet" in result.detail


def test_any_of_none_met_lists_all() -> None:
    condition = AnyOf(conditions=[TextVisible(pattern="alpha"), TextVisible(pattern="beta")])
    result = evaluate(condition, member_detail_observation())
    assert not result.met and "'alpha'" in result.detail and "'beta'" in result.detail


def test_not_inverts_with_detail() -> None:
    result = evaluate(Not(condition=TextVisible(pattern="Checking")), member_detail_observation())
    assert not result.met and result.detail.startswith("not(")
    assert evaluate(
        Not(condition=Not(condition=TextVisible(pattern="Checking"))), member_detail_observation()
    ).met


def test_composites_on_empty_observation() -> None:
    observation = empty_observation()
    assert evaluate(Not(condition=DialogOpen()), observation).met
    assert not evaluate(AnyOf(conditions=[DialogOpen()]), observation).met


# ---------------------------------------------------------------- compile_pattern


def test_compile_pattern_valid_and_invalid(caplog: pytest.LogCaptureFixture) -> None:
    compiled = compile_pattern("a+", re.IGNORECASE, "test")
    assert compiled is not None and compiled.search("AAA")
    with caplog.at_level(logging.ERROR):
        assert compile_pattern("a(", 0, "test.context") is None
    assert "test.context failed" in caplog.text
