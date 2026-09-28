"""Pattern rules for US banking PII, applied in a fixed order so redaction is deterministic.

Order matters: more specific shapes (labelled DOB, SSN, EIN, email, card with Luhn, phone, routing with ABA
checksum) run before the broad "8-17 digit run" account rule, so each value gets the most precise label.

Digit runs are delimited by non-word characters only (`(?<!\\w)` / `(?!\\w)`): identifiers such as uuid hex or
'n42' are left alone, while 'Acct#12345678' and 'ACCT-12345678' are still caught. Member numbers in the mock
(5 digits) are below the 8-digit threshold and stay readable.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

REDACTION_PREFIX = "[REDACTED:"
VALUE_GROUP = "value"


def redaction_marker(label: str) -> str:
    return f"{REDACTION_PREFIX}{label}]"


@dataclass(frozen=True)
class PatternRule:
    """One detector. If `regex` has a group named 'value', only that group is replaced (e.g. the date after
    a 'DOB:' label); otherwise the whole match is. `validator` receives the digits-only candidate and can veto."""

    name: str
    label: str
    regex: re.Pattern[str]
    validator: Callable[[str], bool] | None = None


def digits_only(text: str) -> str:
    return "".join(character for character in text if character.isdigit())


def passes_luhn(digits: str) -> bool:
    """Luhn (mod 10) checksum used by payment card numbers."""
    if not digits.isdigit() or len(digits) < 2:
        return False
    checksum = 0
    for index, character in enumerate(reversed(digits)):
        digit = int(character)
        if index % 2 == 1:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        checksum += digit
    return checksum % 10 == 0


def passes_aba_checksum(digits: str) -> bool:
    """ABA routing transit number checksum (weights 3, 7, 1)."""
    if len(digits) != 9 or not digits.isdigit():
        return False
    weights = (3, 7, 1) * 3
    return sum(int(digit) * weight for digit, weight in zip(digits, weights, strict=True)) % 10 == 0


def _card_validator(candidate: str) -> bool:
    digits = digits_only(candidate)
    return 13 <= len(digits) <= 19 and passes_luhn(digits)


def _routing_validator(candidate: str) -> bool:
    return passes_aba_checksum(digits_only(candidate))


_MONTH_NAMES = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_VALUE = rf"(?:\d{{1,4}}[/.-]\d{{1,2}}[/.-]\d{{1,4}}|{_MONTH_NAMES}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{_MONTH_NAMES}\s+\d{{4}})"

DATE_OF_BIRTH = PatternRule(
    name="date_of_birth",
    label="date_of_birth",
    regex=re.compile(
        rf"\b(?:dob|d\.o\.b\.?|date\s+of\s+birth|birth\s*date)\b[\s:=#-]*(?P<{VALUE_GROUP}>{_DATE_VALUE})",
        re.IGNORECASE,
    ),
)
SSN = PatternRule(
    name="us_ssn",
    label="ssn",
    regex=re.compile(r"(?<!\w)(?!000|666|9\d\d)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}(?!\w)"),
)
EIN = PatternRule(name="us_ein", label="tax_id", regex=re.compile(r"(?<!\w)\d{2}-\d{7}(?!\w)"))
EMAIL = PatternRule(
    name="email",
    label="email",
    regex=re.compile(
        r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?!\w)"
    ),
)
CARD_NUMBER = PatternRule(
    name="card_pan",
    label="card_number",
    regex=re.compile(r"(?<!\w)\d(?:[ -]?\d){12,18}(?!\w)"),
    validator=_card_validator,
)
US_PHONE = PatternRule(
    name="us_phone",
    label="phone",
    regex=re.compile(r"(?<![\w+])(?:\+?1[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\w)"),
)
ROUTING_NUMBER = PatternRule(
    name="aba_routing",
    label="routing_number",
    regex=re.compile(r"(?<!\w)\d{9}(?!\w)"),
    validator=_routing_validator,
)
TAX_ID = PatternRule(
    name="nine_digit_tax_id", label="tax_id", regex=re.compile(r"(?<!\w)\d{9}(?!\w)")
)
ACCOUNT_NUMBER = PatternRule(
    name="account_like_digits", label="account_number", regex=re.compile(r"(?<!\w)\d{8,17}(?!\w)")
)
CURRENCY_AMOUNT = PatternRule(
    name="currency_amount",
    label="amount",
    regex=re.compile(
        r"\$\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?(?!\d)"
        r"|(?<![\w.,])\d{1,3}(?:,\d{3})*\.\d{2}(?!\w)"
    ),
)

DEFAULT_RULES: tuple[PatternRule, ...] = (
    DATE_OF_BIRTH,
    SSN,
    EIN,
    EMAIL,
    CARD_NUMBER,
    US_PHONE,
    ROUTING_NUMBER,
    TAX_ID,
    ACCOUNT_NUMBER,
)


def build_rules(redact_amounts: bool) -> tuple[PatternRule, ...]:
    """The default rule chain, plus currency amounts when enabled (off by default: balances are business data)."""
    return (*DEFAULT_RULES, CURRENCY_AMOUNT) if redact_amounts else DEFAULT_RULES


def apply_rule(rule: PatternRule, text: str) -> str:
    return rule.regex.sub(lambda match: _replacement(rule, match), text)


def _replacement(rule: PatternRule, match: re.Match[str]) -> str:
    whole_match = match.group(0)
    if rule.validator is not None and not rule.validator(whole_match):
        return whole_match
    if VALUE_GROUP not in rule.regex.groupindex:
        return redaction_marker(rule.label)
    value_start = match.start(VALUE_GROUP) - match.start()
    value_end = match.end(VALUE_GROUP) - match.start()
    return whole_match[:value_start] + redaction_marker(rule.label) + whole_match[value_end:]
