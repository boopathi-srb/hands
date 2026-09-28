"""Unit tests for the pure replay helpers: value coercion, input validation, extraction, descriptions."""

from __future__ import annotations

import pytest

from hands.core.actions import ClickAction, NodeRef, Point, TypeAction
from hands.core.artifact import InputSpec, OutputSpec
from hands.core.observation import Dialog, Location, Node, Observation
from hands.core.targets import TargetSpec
from hands.locate import Resolution
from hands.replay import coerce_value
from hands.replay.actions import act_target_for, describe_action
from hands.replay.extraction import ExtractionError, apply_pattern, extract_value, raw_node_text
from hands.replay.failures import describe_observation, describe_target, visible_texts
from hands.replay.inputs import (
    InputRejected,
    prepare_params,
    resolve_credentials,
    validate_input,
    validate_inputs,
)
from hands.replay.values import Coerced, CoercionError

from .app import lookup_capability
from .fakes import FakeCredentials, SecretLog

# ---------------------------------------------------------------- values


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,250.00", "1250.00"), ("1250", "1250"), ("(12.50)", "-12.50"), ("USD 9,870.12", "9870.12"),
     ("-3.5", "-3.5"), ("0.00", "0.00"), (" 85.00 ", "85.00")],
)
def test_decimal_coercion_keeps_a_string_without_float(raw: str, expected: str) -> None:
    coerced = coerce_value(raw, "decimal")
    assert isinstance(coerced, Coerced)
    assert coerced.value == expected and isinstance(coerced.value, str)


@pytest.mark.parametrize("raw", ["", "abc", "1.2.3", "$", "12,34,5x"])
def test_decimal_coercion_rejects_non_numbers(raw: str) -> None:
    assert isinstance(coerce_value(raw, "decimal"), CoercionError)


def test_integer_boolean_date_and_string_coercion() -> None:
    assert coerce_value("1,024", "integer") == Coerced(value=1024, text="1024")
    assert isinstance(coerce_value("1.5", "integer"), CoercionError)
    assert coerce_value("Yes", "boolean") == Coerced(value=True, text="true")
    assert coerce_value("0", "boolean") == Coerced(value=False, text="false")
    assert isinstance(coerce_value("maybe", "boolean"), CoercionError)
    assert coerce_value("2026-09-28", "date").text == "2026-09-28"  # type: ignore[union-attr]
    assert coerce_value("09/28/2026", "date").text == "2026-09-28"  # type: ignore[union-attr]
    assert isinstance(coerce_value("2026-02-30", "date"), CoercionError)
    assert isinstance(coerce_value("", "date"), CoercionError)
    assert coerce_value(" as is ", "string") == Coerced(value=" as is ", text=" as is ")


# ---------------------------------------------------------------- inputs


def test_validate_input_coerces_and_checks_pattern() -> None:
    spec = InputSpec(type="integer", description="n", pattern=r"^\d{3}$")
    assert validate_input("n", spec, "123") == "123"
    assert validate_input("n", spec, 456) == "456"
    rejected = validate_input("n", spec, "1234")
    assert isinstance(rejected, InputRejected) and "pattern" in rejected.message


def test_validate_input_optional_blank_becomes_empty_string() -> None:
    spec = InputSpec(type="string", description="nick", required=False)
    assert validate_input("nick", spec, None) == ""
    assert validate_input("nick", spec, "   ") == ""


def test_validate_input_boolean_value_and_bad_type() -> None:
    assert validate_input("flag", InputSpec(type="boolean", description="f"), True) == "true"
    rejected = validate_input("amount", InputSpec(type="decimal", description="a"), "lots")
    assert isinstance(rejected, InputRejected) and rejected.observed == "'lots'"


def test_invalid_pattern_in_capability_is_reported_not_raised() -> None:
    rejected = validate_input("n", InputSpec(type="string", description="n", pattern="(unclosed"), "1")
    assert isinstance(rejected, InputRejected) and "invalid pattern" in rejected.message


def test_validate_inputs_with_empty_specs_and_empty_inputs() -> None:
    assert validate_inputs({}, {}) == {}
    assert isinstance(validate_inputs({}, {"x": "1"}), InputRejected)


def test_resolve_credentials_registers_every_value() -> None:
    secrets = SecretLog()
    capability = lookup_capability()
    resolved = resolve_credentials(capability.credentials, FakeCredentials(), secrets)
    assert resolved == {"teller.username": "teller1", "teller.password": "pw-123"}
    assert ("pw-123", "credential:teller.password") in secrets.registered


def test_resolve_credentials_provider_exception_is_missing_credential() -> None:
    class BrokenProvider:
        def get(self, credential_name: str, field: str) -> str | None:
            raise OSError("vault unreachable")

    rejected = resolve_credentials(lookup_capability().credentials, BrokenProvider(), None)
    assert isinstance(rejected, InputRejected) and "teller.username" in rejected.message


def test_prepare_params_merges_inputs_and_credentials() -> None:
    prepared = prepare_params(lookup_capability(), {"member_number": "10001"}, FakeCredentials(), None)
    assert not isinstance(prepared, InputRejected)
    assert prepared.params == {"member_number": "10001", "teller.username": "teller1", "teller.password": "pw-123"}


# ---------------------------------------------------------------- extraction


def node(text: str = "", value: str | None = None, name: str = "") -> Node:
    return Node(ref="n1", role="cell", name=name, text=text, value=value)


def test_raw_node_text_prefers_value_then_text_then_name() -> None:
    assert raw_node_text(node(text="t", value="v")) == "v"
    assert raw_node_text(node(text="  a   b ")) == "a b"
    assert raw_node_text(node(name="n")) == "n"
    assert raw_node_text(node()) == ""


def test_apply_pattern_group_whole_match_and_errors() -> None:
    assert apply_pattern("Balance: 1.00", r"Balance:\s*(\S+)") == "1.00"
    assert apply_pattern("abc123", r"\d+") == "123"
    assert apply_pattern("abc", None) == "abc"
    assert isinstance(apply_pattern("abc", r"\d+"), ExtractionError)
    assert isinstance(apply_pattern("abc", "(bad"), ExtractionError)


def test_extract_value_coerces_to_output_type() -> None:
    decimal_spec = OutputSpec(type="decimal", description="d")
    assert extract_value(node(text="$1,250.00"), None, decimal_spec) == Coerced(value="1250.00", text="1250.00")
    assert isinstance(extract_value(node(), None, decimal_spec), ExtractionError)
    assert isinstance(extract_value(node(text="n/a"), None, decimal_spec), ExtractionError)


# ---------------------------------------------------------------- descriptions and act targets


def observation(nodes: list[Node], dialogs: list[Dialog] | None = None) -> Observation:
    from datetime import UTC, datetime

    return Observation(
        observed_at=datetime(2026, 9, 28, tzinfo=UTC),
        location=Location(kind="url", value="http://app.test/x", title="X"),
        nodes=nodes,
        dialogs=dialogs or [],
        fingerprint="fp",
    )


def test_describe_observation_lists_location_dialogs_and_texts() -> None:
    described = describe_observation(
        observation([Node(ref="a", role="text", text="Hello"), Node(ref="b", role="button", name="Go")],
                    [Dialog(title="Notice")])
    )
    assert "http://app.test/x" in described and "'X'" in described
    assert "Notice" in described and "Hello" in described and "Go" not in described
    assert describe_observation(None) == "nothing observed yet"


def test_visible_texts_is_bounded_and_deduplicated() -> None:
    nodes = [Node(ref=f"n{index}", role="text", text=f"line {index % 20}") for index in range(40)]
    texts = visible_texts(observation(nodes))
    assert len(texts) == 8 and len(set(texts)) == 8


def test_describe_target_names_every_candidate() -> None:
    spec = TargetSpec.model_validate({"description": "Box", "candidates": [
        {"kind": "label", "label": "Member", "confidence": 0.8, "reason": "r"},
        {"kind": "structural", "container_path": ["frame:content"], "structural_path": "table[1]/row[1]",
         "confidence": 0.5, "reason": "r"},
        {"kind": "text_anchor", "anchor_text": "Savings", "relation": "right_of", "confidence": 0.5, "reason": "r"},
        {"kind": "visual_anchor", "anchor_text": "Logo", "dx": 10, "dy": -5, "confidence": 0.2, "reason": "r"},
    ]})
    described = describe_target(spec)
    for fragment in ("label('Member')", "structural(frame:content table[1]/row[1])",
                     "text_anchor(right_of 'Savings' #0)", "visual_anchor('Logo' +10,-5)"):
        assert fragment in described


def test_act_target_for_node_point_and_none() -> None:
    matched = Node(ref="n7", role="button", name="Go")
    by_node = Resolution(node=matched, point=Point(x=1, y=2), rank=0, candidate_kind="role_name",
                         ambiguous=False, match_count=1)
    visual = by_node.model_copy(update={"candidate_kind": "visual_anchor"})
    assert act_target_for(by_node) == NodeRef(ref="n7")
    assert act_target_for(visual) == Point(x=1, y=2)
    assert act_target_for(None) is None


def test_describe_action_hides_typed_text() -> None:
    assert describe_action(TypeAction(text="secret")) == {"kind": "type", "clear_first": True, "text_length": 6}
    assert describe_action(ClickAction()) == {"kind": "click"}
