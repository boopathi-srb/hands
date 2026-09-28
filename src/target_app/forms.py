"""Form parsing and field validation. Pure functions, no framework types.

python-multipart is not a project dependency, so url-encoded bodies are parsed here directly.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs

FIELD_MEMBER_NUMBER = "MBR_NO"
FIELD_SHARE_TYPE = "SHR_TYPE"
FIELD_DEPOSIT = "INIT_DEP"
FIELD_NICKNAME = "NICK"
FIELD_SECURITY_ANSWER = "SEC_ANS"

MEMBER_NUMBER_NOT_NUMERIC = "Member number must be numeric."
DEPOSIT_NOT_POSITIVE = "Initial deposit must be a positive amount."
MAX_MEMBER_NUMBER_DIGITS = 12
MAX_NICKNAME_LENGTH = 30
MAX_DEPOSIT = Decimal("999999999.99")


def parse_form_body(body: bytes) -> dict[str, str]:
    """Decode an application/x-www-form-urlencoded body, keeping the first value of each field."""
    if not body:
        return {}
    decoded = body.decode("utf-8", errors="replace")
    parsed = parse_qs(decoded, keep_blank_values=True)
    return {field_name: values[0] for field_name, values in parsed.items() if values}


def parse_member_number(raw_value: str | None) -> str | None:
    """Return the trimmed member number when it is all ASCII digits, else None."""
    if raw_value is None:
        return None
    candidate = raw_value.strip()
    is_digits = candidate.isascii() and candidate.isdigit()
    if not is_digits or len(candidate) > MAX_MEMBER_NUMBER_DIGITS:
        return None
    return candidate


def _to_decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_deposit(raw_value: str | None) -> Decimal | None:
    """Return a positive, finite deposit rounded to cents, else None. Commas are tolerated."""
    if raw_value is None:
        return None
    cleaned = raw_value.strip().replace(",", "")
    if not cleaned:
        return None
    amount = _to_decimal(cleaned)
    if amount is None or not amount.is_finite() or amount > MAX_DEPOSIT:
        return None
    rounded = amount.quantize(Decimal("0.01"))
    if rounded <= 0:
        return None
    return rounded


def clean_nickname(raw_value: str | None) -> str:
    """Trim the optional nickname and cap it at the field length the core allows."""
    if raw_value is None:
        return ""
    return raw_value.strip()[:MAX_NICKNAME_LENGTH]
