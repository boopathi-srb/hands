"""Redaction: masks PII and registered secrets in text, data, observations and screenshots.

Everything that leaves the process (evidence files, operator views, logs of inputs) goes through a Redactor.
"""

from hands.redact.patterns import REDACTION_PREFIX, redaction_marker
from hands.redact.redactor import RedactionConfig, Redactor

__all__ = ["REDACTION_PREFIX", "RedactionConfig", "Redactor", "redaction_marker"]
