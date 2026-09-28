from __future__ import annotations

import pytest

from hands.redact import RedactionConfig, Redactor, redaction_marker
from hands.redact.patterns import (
    ACCOUNT_NUMBER,
    CURRENCY_AMOUNT,
    DATE_OF_BIRTH,
    DEFAULT_RULES,
    apply_rule,
    build_rules,
    digits_only,
    passes_aba_checksum,
    passes_luhn,
)

REDACTOR = Redactor()


# ---------------------------------------------------------------- checksums


@pytest.mark.parametrize(
    ("digits", "expected"),
    [
        ("4111111111111111", True),
        ("5555555555554444", True),
        ("378282246310005", True),
        ("4111111111111112", False),
        ("1234567812345678", False),
        ("", False),
        ("7", False),
        ("41111111x1111111", False),
    ],
)
def test_passes_luhn(digits: str, expected: bool) -> None:
    assert passes_luhn(digits) is expected


@pytest.mark.parametrize(
    ("digits", "expected"),
    [
        ("021000021", True),
        ("011000015", True),
        ("021000022", False),
        ("02100002", False),
        ("", False),
    ],
)
def test_passes_aba_checksum(digits: str, expected: bool) -> None:
    assert passes_aba_checksum(digits) is expected


def test_digits_only() -> None:
    assert digits_only("4111-1111 1111.1111") == "4111111111111111"
    assert digits_only("") == ""


def test_redaction_marker() -> None:
    assert redaction_marker("ssn") == "[REDACTED:ssn]"


# ---------------------------------------------------------------- each pattern


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("SSN 123-45-6789 on file", "SSN [REDACTED:ssn] on file"),
        ("ssn:123 45 6789", "ssn:[REDACTED:ssn]"),
        ("EIN 12-3456789", "EIN [REDACTED:tax_id]"),
        ("TIN 123456789", "TIN [REDACTED:tax_id]"),
        ("card 4111 1111 1111 1111 exp", "card [REDACTED:card_number] exp"),
        ("card 4111-1111-1111-1111", "card [REDACTED:card_number]"),
        ("amex 378282246310005", "amex [REDACTED:card_number]"),
        ("routing 021000021", "routing [REDACTED:routing_number]"),
        ("acct 12345678", "acct [REDACTED:account_number]"),
        ("acct#12345678901234567", "acct#[REDACTED:account_number]"),
        ("ACCT-00012345678", "ACCT-[REDACTED:account_number]"),
        ("mail jane.doe+cu@example.org now", "mail [REDACTED:email] now"),
        ("call (555) 123-4567", "call [REDACTED:phone]"),
        ("call +1 555.123.4567", "call [REDACTED:phone]"),
        ("call 555-123-4567.", "call [REDACTED:phone]."),
        ("DOB: 01/02/1980", "DOB: [REDACTED:date_of_birth]"),
        ("Date of Birth 1980-01-02", "Date of Birth [REDACTED:date_of_birth]"),
        ("birthdate=Jan 2, 1980", "birthdate=[REDACTED:date_of_birth]"),
    ],
)
def test_patterns_redact_sensitive_values(text: str, expected: str) -> None:
    assert REDACTOR.redact_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Member 10001 Avery Quinn",
        "Regular Savings 1,250.00 Checking 310.45",
        "Balance $9,870.12",
        "Opened 2026-09-28 at 10:15",
        "ref n42 in frame:content",
        "run id 3f2a1b4c1234567890abcdef",
        "SSN 000-12-3456 is invalid",
        "Share 0007 opened for member 10001.",
        "ERR-5521 code 403-R",
    ],
)
def test_ordinary_business_text_is_untouched(text: str) -> None:
    assert REDACTOR.redact_text(text) == text


def test_luhn_invalid_card_is_not_labelled_card() -> None:
    redacted = REDACTOR.redact_text("pan 4111 1111 1111 1112")
    assert "card_number" not in redacted
    assert "4111 1111 1111 1112" in redacted  # separated, not a digit run either


def test_luhn_invalid_digit_run_falls_back_to_account() -> None:
    assert REDACTOR.redact_text("4111111111111112") == "[REDACTED:account_number]"


def test_unlabelled_dates_are_not_redacted() -> None:
    assert REDACTOR.redact_text("Opened 01/02/1980") == "Opened 01/02/1980"


def test_amounts_are_configurable() -> None:
    redactor = Redactor(RedactionConfig(redact_amounts=True))
    assert redactor.redact_text("Balance $9,870.12 and 1,250.00") == (
        "Balance [REDACTED:amount] and [REDACTED:amount]"
    )
    assert redactor.redact_text("member 10001") == "member 10001"


def test_build_rules_order_and_amount_toggle() -> None:
    assert build_rules(False) == DEFAULT_RULES
    assert build_rules(True)[-1] is CURRENCY_AMOUNT
    assert DEFAULT_RULES[-1] is ACCOUNT_NUMBER


def test_apply_rule_replaces_only_the_value_group() -> None:
    assert apply_rule(DATE_OF_BIRTH, "dob 1/2/1980 ok") == "dob [REDACTED:date_of_birth] ok"
    assert apply_rule(DATE_OF_BIRTH, "nothing here") == "nothing here"


def test_redact_text_is_deterministic() -> None:
    text = "SSN 123-45-6789, card 4111111111111111, jane@example.com"
    assert REDACTOR.redact_text(text) == REDACTOR.redact_text(text)
    assert REDACTOR.redact_text(REDACTOR.redact_text(text)) == REDACTOR.redact_text(text)
