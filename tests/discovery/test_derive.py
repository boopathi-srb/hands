from __future__ import annotations

import pytest

from hands.core.conditions import LocationMatches, TextVisible
from hands.core.observation import Location
from hands.discovery.derive import (
    canonical_path,
    derive_postcondition,
    distinctive_new_text,
    infer_value_type,
    is_stable_label,
    parameterize_text,
    uses_any_placeholder,
)

from .helpers import make_node, make_observation

INPUTS = {"member_number": "10001"}


def test_parameterize_exact_value_and_url_segments() -> None:
    assert parameterize_text("10001", INPUTS) == "{{member_number}}"
    assert parameterize_text(" 10001 ", INPUTS) == "{{member_number}}"
    assert parameterize_text("http://x/t/a/member/10001?q=1", INPUTS) == "http://x/t/a/member/{{member_number}}?q=1"
    assert parameterize_text("member 10001 please", INPUTS) == "member 10001 please"
    assert parameterize_text("{{teller.password}}", INPUTS) == "{{teller.password}}"
    assert parameterize_text("", INPUTS) == ""
    assert parameterize_text("10001", {"empty": ""}) == "10001"


def test_parameterize_prefers_longest_value() -> None:
    values = {"short": "100", "long": "10001"}
    assert parameterize_text("10001", values) == "{{long}}"


def test_canonical_path() -> None:
    member = Location(kind="url", value="http://x/t/lakeside/member/10001")
    assert canonical_path(member, INPUTS) == "/t/lakeside/member/:member_number"
    assert canonical_path(member, INPUTS, tenant_id="lakeside") == "/t/:tenant/member/:member_number"
    other_id = Location(kind="url", value="http://x/orders/987654/view")
    assert canonical_path(other_id, {}) == "/orders/:id/view"
    assert canonical_path(Location(kind="url", value="http://x"), {}) == "/"
    assert canonical_path(Location(kind="window", value="com.apple.calculator", title="Calc"), {}) is None


def test_postcondition_prefers_location_change() -> None:
    before = make_observation([], url="http://x/t/lakeside/login")
    after = make_observation([make_node("n1", "text", "Welcome")], url="http://x/t/lakeside/main")
    condition = derive_postcondition(before, after, INPUTS, tenant_id="lakeside")
    assert condition == LocationMatches(pattern="/t/:tenant/main")


def test_postcondition_uses_distinctive_new_text_then_none() -> None:
    before = make_observation([make_node("n1", "link", "Member Inquiry")])
    after = make_observation([
        make_node("n1", "link", "Member Inquiry"),
        make_node("n2", "text", "Member Inquiry"),
        make_node("n3", "cell", "1,250.00"),
        make_node("n4", "cell", "Member 10001"),
        make_node("n5", "heading", "Member Detail"),
    ])
    assert derive_postcondition(before, after, INPUTS) == TextVisible(pattern="Member Detail")
    assert derive_postcondition(before, before, INPUTS) is None
    assert derive_postcondition(before, None, INPUTS) is None


def test_distinctive_text_skips_masked_and_interactive() -> None:
    before = make_observation([])
    after = make_observation([make_node("n1", "text", "Signed on as ••••"), make_node("n2", "button", "Go"),
                              make_node("n3", "text", "OK")])
    assert distinctive_new_text(before, after, {}) is None


def test_is_stable_label() -> None:
    assert is_stable_label("Member Detail", INPUTS)
    for text in ("ab", "x" * 61, "1,250.00", "Member 10001", "{{member_number}}", "as ••••", "2026-09-28"):
        assert not is_stable_label(text, INPUTS)


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        ("1,250.00", "decimal"), ("0.00", "decimal"), ("$ 12.50", "decimal"), ("12,000", "decimal"),
        ("42", "integer"), ("-7", "integer"), ("0001", "string"), ("2026-09-28", "date"),
        ("9/28/2026", "date"), ("Avery Quinn", "string"), ("", "string"),
    ],
)
def test_infer_value_type(sample: str, expected: str) -> None:
    assert infer_value_type(sample) == expected


def test_uses_any_placeholder() -> None:
    assert uses_any_placeholder("{{teller.password}}", ["teller.password"])
    assert not uses_any_placeholder("{{member_number}}", ["teller.password"])
    assert not uses_any_placeholder(None, ["teller.password"])
