"""Typed value coercion shared by input validation and output extraction.

Decimals stay strings ('1250.00') so money never passes through float. Currency symbols, ISO currency
codes, thousands separators and accounting parentheses are understood.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from hands.core.artifact import ValueType

_INTEGER = re.compile(r"^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_CURRENCY_SYMBOLS = re.compile(r"[$€£¥₹]")
_CURRENCY_CODE = re.compile(r"^[A-Z]{3}\s+|\s+[A-Z]{3}$")
_THOUSANDS_SEPARATORS = re.compile(r"[,\s](?=\d{3}\b)")
_TRUE_WORDS = ("true", "yes", "y", "1", "on")
_FALSE_WORDS = ("false", "no", "n", "0", "off")
_DATE_FORMATS = ("%m/%d/%Y", "%d-%b-%Y", "%b %d, %Y")


class Coerced(BaseModel):
    """`value` is the typed value returned to callers; `text` is its canonical string for templating."""

    value: Any
    text: str


class CoercionError(BaseModel):
    reason: str


def coerce_value(raw: str, value_type: ValueType) -> Coerced | CoercionError:
    """Parse `raw` as `value_type`."""
    if value_type == "integer":
        return coerce_integer(raw)
    if value_type == "decimal":
        return coerce_decimal(raw)
    if value_type == "boolean":
        return coerce_boolean(raw)
    if value_type == "date":
        return coerce_date(raw)
    return Coerced(value=raw, text=raw)


def coerce_integer(raw: str) -> Coerced | CoercionError:
    cleaned = _THOUSANDS_SEPARATORS.sub("", raw.strip())
    if not _INTEGER.fullmatch(cleaned):
        return CoercionError(reason="expected a whole number")
    number = int(cleaned)
    return Coerced(value=number, text=str(number))


def coerce_decimal(raw: str) -> Coerced | CoercionError:
    cleaned, negative = _strip_money_formatting(raw)
    if not _DECIMAL.fullmatch(cleaned):
        return CoercionError(reason="expected a decimal number")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return CoercionError(reason="expected a decimal number")
    canonical = format(-number if negative else number, "f")
    return Coerced(value=canonical, text=canonical)


def coerce_boolean(raw: str) -> Coerced | CoercionError:
    word = raw.strip().casefold()
    if word in _TRUE_WORDS:
        return Coerced(value=True, text="true")
    if word in _FALSE_WORDS:
        return Coerced(value=False, text="false")
    return CoercionError(reason=f"expected one of {list(_TRUE_WORDS + _FALSE_WORDS)}")


def coerce_date(raw: str) -> Coerced | CoercionError:
    parsed = _parse_date(raw.strip())
    if parsed is None:
        return CoercionError(reason="expected a date (YYYY-MM-DD)")
    return Coerced(value=parsed.isoformat(), text=parsed.isoformat())


def _strip_money_formatting(raw: str) -> tuple[str, bool]:
    """('1250.00', False) from '$1,250.00'; ('12.50', True) from '(12.50)'."""
    text = _CURRENCY_CODE.sub("", raw.strip())
    text = _CURRENCY_SYMBOLS.sub("", text).strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    return _THOUSANDS_SEPARATORS.sub("", text).replace(" ", ""), negative


def _parse_date(text: str) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    return None
