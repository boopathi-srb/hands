"""Pure, surface-agnostic functions over an Observation: the heart of deterministic replay.

- templating: fill `{{param}}` / `{{cred.field}}` placeholders and apply tenant text aliases
- resolve:    find the node a TargetSpec refers to
- evaluate:   decide whether a Condition holds
- candidates: turn a node into a ranked, verified TargetSpec (recording)

No I/O, no browser, no async.
"""

from hands.locate.candidates import build_target_spec, generate_candidates, is_volatile_text
from hands.locate.evaluate import ConditionResult, evaluate
from hands.locate.resolve import Resolution, resolve_target
from hands.locate.templating import (
    FillResult,
    apply_aliases,
    fill_condition,
    fill_placeholders,
    fill_target,
)

__all__ = [
    "ConditionResult",
    "FillResult",
    "Resolution",
    "apply_aliases",
    "build_target_spec",
    "evaluate",
    "fill_condition",
    "fill_placeholders",
    "fill_target",
    "generate_candidates",
    "is_volatile_text",
    "resolve_target",
]
