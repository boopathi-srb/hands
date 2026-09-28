"""Run ids that are safe directory names and never look like account numbers to the redactor."""

from __future__ import annotations

import re
import secrets

_LONG_DIGIT_RUN = re.compile(r"\d{5,}")


def new_run_id(prefix: str) -> str:
    """`disc-3f9ab2c1e0d4`, regenerated until it has no run of 5+ digits (the redactor masks 8+)."""
    candidate = f"{prefix}-{secrets.token_hex(6)}"
    while _LONG_DIGIT_RUN.search(candidate):
        candidate = f"{prefix}-{secrets.token_hex(6)}"
    return candidate
