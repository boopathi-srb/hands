"""Exact sensitive values registered at runtime (sensitive inputs, resolved credential fields).

Each value is also registered in the encodings it commonly leaks through (URL-encoded, JSON-escaped,
HTML-escaped), so a password echoed in a query string or a JSON blob is still caught. Longer values are
replaced first, so a secret that contains another secret is masked whole.
"""

from __future__ import annotations

import html
import json
import re
import threading
from urllib.parse import quote, quote_plus

from hands.redact.patterns import redaction_marker

_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")
DEFAULT_SECRET_LABEL = "secret"


def normalize_label(label: str) -> str:
    """Labels appear inside markers, so keep them to a safe character set."""
    cleaned = _LABEL_UNSAFE.sub("_", label.strip()).strip("_")
    return cleaned or DEFAULT_SECRET_LABEL


def encoded_variants(value: str) -> list[str]:
    """The value plus the encodings it is likely to appear in, deduplicated, in a stable order."""
    candidates = [
        value,
        quote(value, safe=""),
        quote_plus(value),
        json.dumps(value)[1:-1],
        html.escape(value),
    ]
    unique_variants: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique_variants:
            unique_variants.append(candidate)
    return unique_variants


class SecretRegistry:
    """Thread-safe registry of exact values and the label each one is masked with."""

    def __init__(self) -> None:
        self._label_by_variant: dict[str, str] = {}
        self._matcher: re.Pattern[str] | None = None
        self._lock = threading.Lock()

    def register(self, value: str | None, label: str) -> bool:
        """Register a value. Returns False (and registers nothing) for None, empty or whitespace-only values."""
        if value is None or not value.strip():
            return False
        safe_label = normalize_label(label)
        with self._lock:
            for variant in encoded_variants(value):
                self._label_by_variant.setdefault(variant, safe_label)
            self._matcher = _build_matcher(list(self._label_by_variant))
        return True

    def __len__(self) -> int:
        return len(self._label_by_variant)

    def mask(self, text: str) -> str:
        matcher = self._matcher
        if matcher is None or not text:
            return text
        return matcher.sub(
            lambda match: redaction_marker(self._label_by_variant[match.group(0)]), text
        )


def _build_matcher(variants: list[str]) -> re.Pattern[str]:
    longest_first = sorted(variants, key=lambda variant: (-len(variant), variant))
    return re.compile("|".join(re.escape(variant) for variant in longest_first))
