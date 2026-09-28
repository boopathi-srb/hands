from __future__ import annotations

import json
from datetime import UTC, date, datetime
from enum import Enum

import pytest
from pydantic import BaseModel

from hands.core.actions import TypeAction
from hands.redact import RedactionConfig, Redactor
from hands.redact.secrets import SecretRegistry, encoded_variants, normalize_label

SECRET = "Tr0ub4dor&3 x"


@pytest.fixture
def redactor() -> Redactor:
    redactor = Redactor()
    assert redactor.register_secret(SECRET, "credential.password")
    return redactor


# ---------------------------------------------------------------- registry


@pytest.mark.parametrize("value", [None, "", "   ", "\n\t"])
def test_register_rejects_empty_values(value: str | None) -> None:
    registry = SecretRegistry()
    assert registry.register(value, "x") is False
    assert len(registry) == 0
    assert registry.mask("anything") == "anything"


def test_encoded_variants_are_unique_and_stable() -> None:
    variants = encoded_variants('p a"s&s')
    assert variants[0] == 'p a"s&s'
    assert "p%20a%22s%26s" in variants
    assert "p+a%22s%26s" in variants
    assert 'p a\\"s&s' in variants
    assert "p a&quot;s&amp;s" in variants
    assert len(variants) == len(set(variants))
    assert encoded_variants("plain") == ["plain"]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("credential.password", "credential.password"),
        ("input ssn!", "input_ssn"),
        ("", "secret"),
        ("***", "secret"),
    ],
)
def test_normalize_label(label: str, expected: str) -> None:
    assert normalize_label(label) == expected


def test_longer_secrets_are_masked_before_their_substrings() -> None:
    redactor = Redactor()
    redactor.register_secret("abcd", "short")
    redactor.register_secret("abcdefgh", "long")
    assert redactor.redact_text("xabcdefghx abcd") == "x[REDACTED:long]x [REDACTED:short]"


def test_first_label_wins_for_the_same_value() -> None:
    redactor = Redactor()
    redactor.register_secret("same-value", "first")
    redactor.register_secret("same-value", "second")
    assert redactor.redact_text("same-value") == "[REDACTED:first]"


def test_secret_count_counts_variants(redactor: Redactor) -> None:
    assert redactor.secret_count == len(encoded_variants(SECRET))


# ---------------------------------------------------------------- redact_text with secrets


@pytest.mark.parametrize(
    "carrier",
    [
        f"password={SECRET}",
        "q=Tr0ub4dor%263%20x",
        "q=Tr0ub4dor%263+x",
        '{"pw": "Tr0ub4dor&3 x"}',
        "<td>Tr0ub4dor&amp;3 x</td>",
    ],
)
def test_registered_secret_is_masked_in_all_encodings(redactor: Redactor, carrier: str) -> None:
    redacted = redactor.redact_text(carrier)
    assert "Tr0ub4dor" not in redacted
    assert "[REDACTED:credential.password]" in redacted


def test_redact_text_empty(redactor: Redactor) -> None:
    assert redactor.redact_text("") == ""


# ---------------------------------------------------------------- redact_value


class Color(Enum):
    RED = "red"


class Payload(BaseModel):
    note: str
    raw: bytes = b"\x00\x01"
    nested: dict[str, list[str]]


def test_redact_value_recurses_into_nested_structures(redactor: Redactor) -> None:
    value = {
        "outer": [{"inner": (SECRET, {"deep": f"x {SECRET} y"})}],
        SECRET: "secret used as a key",
        "set": {SECRET},
    }
    redacted = redactor.redact_value(value)
    assert SECRET not in json.dumps(redacted)
    assert redacted["outer"][0]["inner"][0] == "[REDACTED:credential.password]"
    assert "[REDACTED:credential.password]" in redacted


def test_redact_value_handles_pydantic_models(redactor: Redactor) -> None:
    redacted = redactor.redact_value(Payload(note=SECRET, nested={"k": ["SSN 123-45-6789"]}))
    assert redacted["note"] == "[REDACTED:credential.password]"
    assert redacted["nested"]["k"] == ["SSN [REDACTED:ssn]"]
    assert isinstance(redacted, dict)


def test_redact_value_masks_typed_text_in_actions(redactor: Redactor) -> None:
    redacted = redactor.redact_value({"action": TypeAction(text=SECRET)})
    assert redacted["action"] == {
        "kind": "type",
        "text": "[REDACTED:credential.password]",
        "clear_first": True,
    }


@pytest.mark.parametrize(
    "key", ["password", "Password", "api-key", "token", "ssn", "authorization"]
)
def test_sensitive_keys_mask_the_whole_value(key: str) -> None:
    redacted = Redactor().redact_value({key: "not-a-pattern", "other": "visible"})
    assert redacted[key].startswith("[REDACTED:")
    assert redacted["other"] == "visible"


def test_sensitive_keys_keep_empty_values() -> None:
    assert Redactor().redact_value({"password": None, "token": ""}) == {
        "password": None,
        "token": "",
    }


def test_custom_sensitive_keys() -> None:
    redactor = Redactor(RedactionConfig(sensitive_keys=("member_pin",)))
    assert redactor.redact_value({"member_pin": "1234", "password": "x"}) == {
        "member_pin": "[REDACTED:member_pin]",
        "password": "x",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (True, True),
        (1.5, 1.5),
        (10001, 10001),
        (123456789012, "[REDACTED:account_number]"),
        (b"\x89PNG", "<4 bytes omitted>"),
        (datetime(2026, 9, 28, tzinfo=UTC), "2026-09-28T00:00:00+00:00"),
        (date(2026, 9, 28), "2026-09-28"),
        (Color.RED, "red"),
        ([], []),
        ({}, {}),
        ("", ""),
    ],
)
def test_redact_value_scalars_and_empties(value: object, expected: object) -> None:
    assert Redactor().redact_value(value) == expected


def test_redact_value_sorts_sets_deterministically() -> None:
    assert Redactor().redact_value({"b", "a", "c"}) == ["a", "b", "c"]


def test_redact_value_stringifies_unknown_objects(redactor: Redactor) -> None:
    class Opaque:
        def __str__(self) -> str:
            return f"opaque {SECRET}"

    assert redactor.redact_value(Opaque()) == "opaque [REDACTED:credential.password]"
