"""Placeholder filling and tenant text aliasing for targets and conditions.

Placeholder syntax
    `hands.core.artifact.PLACEHOLDER_PATTERN`: `{{name}}` refers to an invocation input and
    `{{credential.field}}` (one dotted segment) to a credential field. Whitespace inside the braces is
    allowed: `{{ member_number }}`. Params are keyed by the captured name, e.g. "teller.password".

Order of operations
    Aliases are applied to the recorded (base tenant) text first, then placeholders are filled. Caller
    supplied values are therefore never rewritten by tenant aliases.

Regex fields
    Fields that are regular expressions (TextVisible.pattern when regex=True, ValueMatches.pattern,
    LocationMatches.title_pattern, DialogOpen title/text patterns) receive `re.escape`d parameter values
    and alias replacements, so a member number or a tenant label is always matched literally.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from hands.core.artifact import PLACEHOLDER_PATTERN
from hands.core.conditions import (
    AllOf,
    AnyOf,
    Condition,
    DialogOpen,
    LocationMatches,
    NodePresent,
    Not,
    TextVisible,
    ValueMatches,
)
from hands.core.log import get_logger, log_failure
from hands.core.targets import TargetSpec

_logger = get_logger(__name__)

_NON_TEMPLATED_FIELDS = frozenset({"kind"})

TextTransform = Callable[[str], str]


class FillResult(BaseModel):
    """Templated text plus the placeholder names that had no value (left in place, in first-seen order)."""

    text: str
    missing: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- strings


def fill_placeholders(text: str, params: Mapping[str, str]) -> FillResult:
    """Replace every `{{name}}` / `{{cred.field}}` with its value from `params`."""
    return _fill_placeholders_with(text, params, escape_values=False)


def apply_aliases(text: str, aliases: Mapping[str, str]) -> str:
    """Replace exact substrings using tenant aliases in a single pass, longest alias first.

    A single pass means a replacement is never itself re-aliased ('Regular Savings' -> 'Share Savings'
    is not then hit by a shorter 'Savings' alias).
    """
    return _apply_aliases_with(text, aliases, escape_replacements=False)


def _fill_placeholders_with(
    text: str, params: Mapping[str, str], escape_values: bool
) -> FillResult:
    if not text:
        return FillResult(text="")
    missing_names: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        placeholder_name = match.group(1)
        if placeholder_name not in params:
            if placeholder_name not in missing_names:
                missing_names.append(placeholder_name)
            return match.group(0)
        value = str(params[placeholder_name])
        return re.escape(value) if escape_values else value

    filled_text = PLACEHOLDER_PATTERN.sub(substitute, text)
    return FillResult(text=filled_text, missing=missing_names)


def _apply_aliases_with(text: str, aliases: Mapping[str, str], escape_replacements: bool) -> str:
    usable_aliases = _usable_aliases(aliases)
    if not text or not usable_aliases:
        return text
    longest_first = sorted(usable_aliases, key=len, reverse=True)
    alias_pattern = re.compile("|".join(re.escape(alias) for alias in longest_first))

    def substitute(match: re.Match[str]) -> str:
        replacement = usable_aliases[match.group(0)]
        return re.escape(replacement) if escape_replacements else replacement

    return alias_pattern.sub(substitute, text)


def _usable_aliases(aliases: Mapping[str, str]) -> dict[str, str]:
    usable: dict[str, str] = {}
    for base_text, tenant_text in aliases.items():
        if not base_text:
            log_failure(
                _logger, "apply_aliases", "empty alias key ignored", tenant_text=tenant_text
            )
            continue
        usable[base_text] = tenant_text
    return usable


def _template_text(
    text: str, params: Mapping[str, str], aliases: Mapping[str, str], regex_field: bool
) -> str:
    aliased_text = _apply_aliases_with(text, aliases, escape_replacements=regex_field)
    fill_result = _fill_placeholders_with(aliased_text, params, escape_values=regex_field)
    if fill_result.missing:
        log_failure(
            _logger,
            "fill_target/fill_condition",
            "placeholders have no value and were left in place",
            text=text,
            missing=fill_result.missing,
        )
    return fill_result.text


# ---------------------------------------------------------------- targets


def fill_target(
    spec: TargetSpec, params: Mapping[str, str], aliases: Mapping[str, str]
) -> TargetSpec:
    """A copy of `spec` with every string field of every candidate templated and aliased."""

    def transform(text: str) -> str:
        return _template_text(text, params, aliases, regex_field=False)

    templated_dump = _transform_strings(spec.model_dump(), transform)
    return TargetSpec.model_validate(templated_dump)


def _transform_strings(value: Any, transform: TextTransform) -> Any:
    """Apply `transform` to every string in a model dump, leaving discriminator fields untouched."""
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, dict):
        return {
            key: item if key in _NON_TEMPLATED_FIELDS else _transform_strings(item, transform)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(_transform_strings(item, transform) for item in value)
    return value


# ---------------------------------------------------------------- conditions


def fill_condition(
    condition: Condition, params: Mapping[str, str], aliases: Mapping[str, str]
) -> Condition:
    """A copy of `condition` (recursively) with every string templated and aliased."""
    return _ConditionTemplater(params, aliases).fill(condition)


class _ConditionTemplater:
    """Dispatches on condition kind so regex fields get escaped values and literal fields do not."""

    def __init__(self, params: Mapping[str, str], aliases: Mapping[str, str]) -> None:
        self._params = params
        self._aliases = aliases

    def fill(self, condition: Condition) -> Condition:
        if isinstance(condition, TextVisible):
            return condition.model_copy(
                update={"pattern": self._text(condition.pattern, condition.regex)}
            )
        if isinstance(condition, NodePresent):
            return condition.model_copy(update={"target": self._target(condition.target)})
        if isinstance(condition, LocationMatches):
            return self._fill_location(condition)
        if isinstance(condition, DialogOpen):
            return self._fill_dialog(condition)
        if isinstance(condition, ValueMatches):
            return self._fill_value_matches(condition)
        return self._fill_composite(condition)

    def _fill_composite(self, condition: AllOf | AnyOf | Not) -> Condition:
        if isinstance(condition, Not):
            return condition.model_copy(update={"condition": self.fill(condition.condition)})
        filled_children = [self.fill(child) for child in condition.conditions]
        return condition.model_copy(update={"conditions": filled_children})

    def _fill_location(self, condition: LocationMatches) -> LocationMatches:
        return condition.model_copy(
            update={
                "pattern": self._optional_text(condition.pattern, regex_field=False),
                "title_pattern": self._optional_text(condition.title_pattern, regex_field=True),
            }
        )

    def _fill_dialog(self, condition: DialogOpen) -> DialogOpen:
        return condition.model_copy(
            update={
                "title_pattern": self._optional_text(condition.title_pattern, regex_field=True),
                "text_pattern": self._optional_text(condition.text_pattern, regex_field=True),
            }
        )

    def _fill_value_matches(self, condition: ValueMatches) -> ValueMatches:
        return condition.model_copy(
            update={
                "target": self._target(condition.target),
                "pattern": self._text(condition.pattern, regex_field=True),
            }
        )

    def _target(self, spec: TargetSpec) -> TargetSpec:
        return fill_target(spec, self._params, self._aliases)

    def _text(self, text: str, regex_field: bool) -> str:
        return _template_text(text, self._params, self._aliases, regex_field)

    def _optional_text(self, text: str | None, regex_field: bool) -> str | None:
        return None if text is None else self._text(text, regex_field)
