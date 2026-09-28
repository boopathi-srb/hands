"""Field-level detection over accessibility nodes: password fields and fields labelled as sensitive.

These do not depend on the value's shape. A password field's value is always masked, whatever it contains,
and a field labelled 'SSN' or 'Date of Birth' is masked even when its value is not in a recognizable format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hands.core.observation import Node

EDITABLE_ROLES = frozenset(
    {
        "textbox",
        "searchbox",
        "combobox",
        "spinbutton",
        "textfield",
        "text_field",
        "securetextfield",
        "password",
    }
)
DEFAULT_PASSWORD_PATTERN = r"\b(pass(word|code|phrase)?|pwd|pin)\b"
DEFAULT_SENSITIVE_LABEL_PATTERN = (
    r"\b(ssn|social\s+security|tax\s*id|tin|ein|date\s+of\s+birth|dob|birth\s*date"
    r"|security\s+(answer|code)|secret\s+answer|mother'?s\s+maiden|cvv|cvc)\b"
)
DEFAULT_SENSITIVE_KEYS = (
    "password",
    "passwd",
    "passcode",
    "pin",
    "ssn",
    "social_security_number",
    "tax_id",
    "secret",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set_cookie",
    "security_answer",
)


@dataclass(frozen=True)
class FieldRules:
    password_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(DEFAULT_PASSWORD_PATTERN, re.IGNORECASE)
    )
    sensitive_label_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(DEFAULT_SENSITIVE_LABEL_PATTERN, re.IGNORECASE)
    )
    sensitive_keys: frozenset[str] = frozenset(DEFAULT_SENSITIVE_KEYS)


def _normalized_role(node: Node) -> str:
    """Lowercase role with a macOS 'AX' prefix removed ('AXSecureTextField' -> 'securetextfield')."""
    role = node.role.lower()
    return role.removeprefix("ax")


def _descriptors(node: Node) -> list[str]:
    return [text for text in (node.name, node.label or "") if text]


def is_editable(node: Node) -> bool:
    role = _normalized_role(node)
    return role in EDITABLE_ROLES or "secure" in role


def is_password_field(node: Node, rules: FieldRules) -> bool:
    """A secure text field, or an editable field whose name or label says password/passcode/PIN."""
    role = _normalized_role(node)
    if "secure" in role or role == "password":
        return True
    return is_editable(node) and any(
        rules.password_pattern.search(text) for text in _descriptors(node)
    )


def is_sensitive_labelled_field(node: Node, rules: FieldRules) -> bool:
    """A node whose own label or name marks it as sensitive (SSN, DOB, security answer...)."""
    return any(rules.sensitive_label_pattern.search(text) for text in _descriptors(node)) and bool(
        node.value or (node.label and node.text)
    )


def is_sensitive_key(key: str, rules: FieldRules) -> bool:
    return key.strip().lower().replace("-", "_") in rules.sensitive_keys
