"""Read an output value from a resolved node: node value, else text, else name; optional regex group;
then coercion to the declared OutputSpec type (decimals stay strings such as '1250.00')."""

from __future__ import annotations

import re

from pydantic import BaseModel

from hands.core.artifact import OutputSpec
from hands.core.log import get_logger, log_failure
from hands.core.observation import Node
from hands.replay.values import Coerced, CoercionError, coerce_value

_logger = get_logger(__name__)


class ExtractionError(BaseModel):
    reason: str


def raw_node_text(node: Node) -> str:
    for candidate_text in (node.value, node.text, node.name):
        if candidate_text and candidate_text.strip():
            return " ".join(candidate_text.split())
    return ""


def apply_pattern(text: str, pattern: str | None) -> str | ExtractionError:
    """The first group of `pattern` (or the whole match when it has no group)."""
    if pattern is None:
        return text
    try:
        compiled = re.compile(pattern)
    except re.error as pattern_error:
        log_failure(_logger, "apply_pattern", f"invalid extract pattern: {pattern_error}", pattern=pattern)
        return ExtractionError(reason=f"extract pattern {pattern!r} is not a valid regular expression")
    match = compiled.search(text)
    if match is None:
        return ExtractionError(reason=f"pattern {pattern!r} did not match the node text")
    return match.group(1) if compiled.groups else match.group(0)


def extract_value(node: Node, pattern: str | None, spec: OutputSpec) -> Coerced | ExtractionError:
    raw_text = raw_node_text(node)
    if not raw_text:
        return ExtractionError(reason="the node has no value or text")
    matched_text = apply_pattern(raw_text, pattern)
    if isinstance(matched_text, ExtractionError):
        return matched_text
    coerced = coerce_value(matched_text.strip(), spec.type)
    if isinstance(coerced, CoercionError):
        return ExtractionError(reason=f"not a valid {spec.type}: {coerced.reason}")
    return coerced
