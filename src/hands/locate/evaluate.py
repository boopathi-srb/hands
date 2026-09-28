"""Evaluate a (templated) Condition against an Observation. Pure; never raises for bad patterns.

Semantics
- text_visible: searches every node's text, name and value, and every dialog's title and text.
  Plain patterns are whitespace-collapsed substring matches (case-insensitive unless case_sensitive);
  regex patterns use re.search (IGNORECASE unless case_sensitive).
- node_present: the target resolves (see hands.locate.resolve).
- location_matches: for kind 'url' the pattern is matched against the URL path only (scheme, host,
  query and fragment are ignored), case-sensitively; for kind 'window' against the window title,
  case-insensitively. ':name' matches one path segment, '*' matches any run of characters, and a
  trailing '/*' also matches nothing ('/member/:id/*' matches '/member/10001'). title_pattern is a
  case-insensitive regex searched in Location.title. Both parts must hold; a condition with neither is met.
- dialog_open: some entry of Observation.dialogs matches title_pattern and text_pattern
  (case-insensitive regex search; None matches anything).
- value_matches: the target resolves to a node and `pattern` (regex, re.search) matches its value,
  falling back to its visible text when value is None.
- all_of / any_of / not: nested evaluation; all_of stops at the first unmet child.
An invalid regex is logged with log_failure and evaluates to not met.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel

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
from hands.core.observation import Dialog, Location, Observation
from hands.locate._text import collapse_whitespace
from hands.locate.resolve import resolve_target

_logger = get_logger(__name__)

MAX_DETAIL_VALUE_CHARS = 80
_PATH_PARAMETER = re.compile(r":[A-Za-z_][A-Za-z0-9_]*")


class ConditionResult(BaseModel):
    """Whether a condition held, and a human-readable account of what was checked and seen."""

    met: bool
    detail: str


def evaluate(condition: Condition, observation: Observation) -> ConditionResult:
    """Evaluate any Condition kind, including nested all_of / any_of / not."""
    if isinstance(condition, TextVisible):
        return _evaluate_text_visible(condition, observation)
    if isinstance(condition, NodePresent):
        return _evaluate_node_present(condition, observation)
    if isinstance(condition, LocationMatches):
        return _evaluate_location(condition, observation.location)
    if isinstance(condition, DialogOpen):
        return _evaluate_dialog_open(condition, observation.dialogs)
    if isinstance(condition, ValueMatches):
        return _evaluate_value_matches(condition, observation)
    return _evaluate_composite(condition, observation)


# ---------------------------------------------------------------- regex helper


def compile_pattern(pattern: str, flags: int, context: str) -> re.Pattern[str] | None:
    """Compile a regex from an artifact, logging and returning None when it is invalid."""
    try:
        return re.compile(pattern, flags)
    except re.error as compile_error:
        log_failure(_logger, context, f"invalid regex: {compile_error}", pattern=pattern)
        return None


def _invalid_pattern_result(kind: str, pattern: str) -> ConditionResult:
    return ConditionResult(
        met=False, detail=f"{kind}: pattern {pattern!r} is not a valid regular expression"
    )


def _preview(value: str) -> str:
    collapsed = collapse_whitespace(value)
    if len(collapsed) <= MAX_DETAIL_VALUE_CHARS:
        return collapsed
    return collapsed[: MAX_DETAIL_VALUE_CHARS - 3] + "..."


# ---------------------------------------------------------------- text_visible


def _evaluate_text_visible(condition: TextVisible, observation: Observation) -> ConditionResult:
    haystacks = _visible_haystacks(observation)
    matcher = _text_matcher(condition)
    if matcher is None:
        return _invalid_pattern_result("text_visible", condition.pattern)
    found_in = next((source for source, text in haystacks if matcher(text)), None)
    if found_in is not None:
        return ConditionResult(
            met=True, detail=f"text_visible: {condition.pattern!r} found in {found_in}"
        )
    return ConditionResult(
        met=False,
        detail=(
            f"text_visible: {condition.pattern!r} not found in {len(observation.nodes)} nodes "
            f"and {len(observation.dialogs)} dialogs"
        ),
    )


def _visible_haystacks(observation: Observation) -> list[tuple[str, str]]:
    """(source description, text) pairs for every piece of visible text."""
    haystacks: list[tuple[str, str]] = []
    for node in observation.nodes:
        source = f"{node.role} node {node.ref}"
        for text in (node.text, node.name, node.value or ""):
            if text:
                haystacks.append((source, text))
    for index, dialog in enumerate(observation.dialogs):
        for text in (dialog.title, dialog.text):
            if text:
                haystacks.append((f"dialog[{index}]", text))
    return haystacks


def _text_matcher(condition: TextVisible) -> _TextMatcher | None:
    if condition.regex:
        flags = 0 if condition.case_sensitive else re.IGNORECASE
        compiled = compile_pattern(condition.pattern, flags, "evaluate.text_visible")
        return None if compiled is None else _TextMatcher(regex=compiled)
    return _TextMatcher(
        needle=_fold(collapse_whitespace(condition.pattern), condition.case_sensitive),
        case_sensitive=condition.case_sensitive,
    )


class _TextMatcher:
    """Either a compiled regex or a normalized substring needle."""

    def __init__(
        self, regex: re.Pattern[str] | None = None, needle: str = "", case_sensitive: bool = False
    ) -> None:
        self._regex = regex
        self._needle = needle
        self._case_sensitive = case_sensitive

    def __call__(self, text: str) -> bool:
        if self._regex is not None:
            return self._regex.search(text) is not None
        if not self._needle:
            return False
        return self._needle in _fold(collapse_whitespace(text), self._case_sensitive)


def _fold(text: str, case_sensitive: bool) -> str:
    return text if case_sensitive else text.casefold()


# ---------------------------------------------------------------- node_present / value_matches


def _evaluate_node_present(condition: NodePresent, observation: Observation) -> ConditionResult:
    resolution = resolve_target(condition.target, observation)
    description = condition.target.description
    if resolution is None:
        return ConditionResult(
            met=False,
            detail=f"node_present: no candidate of {description!r} matched ({len(condition.target.candidates)} tried)",
        )
    matched_ref = resolution.node.ref if resolution.node is not None else "a point"
    return ConditionResult(
        met=True,
        detail=(
            f"node_present: {description!r} matched {matched_ref} via {resolution.candidate_kind} "
            f"at rank {resolution.rank}"
        ),
    )


def _evaluate_value_matches(condition: ValueMatches, observation: Observation) -> ConditionResult:
    description = condition.target.description
    compiled = compile_pattern(condition.pattern, 0, "evaluate.value_matches")
    if compiled is None:
        return _invalid_pattern_result("value_matches", condition.pattern)
    resolution = resolve_target(condition.target, observation)
    if resolution is None or resolution.node is None:
        return ConditionResult(met=False, detail=f"value_matches: target {description!r} not found")
    node = resolution.node
    observed_value = node.value if node.value is not None else node.text
    met = compiled.search(observed_value) is not None
    verdict = "matches" if met else "does not match"
    return ConditionResult(
        met=met,
        detail=f"value_matches: {description!r} value {_preview(observed_value)!r} {verdict} {condition.pattern!r}",
    )


# ---------------------------------------------------------------- location_matches


def _evaluate_location(condition: LocationMatches, location: Location) -> ConditionResult:
    subject = _location_subject(location)
    checks: list[tuple[bool, str]] = []
    if condition.pattern is not None:
        checks.append(_check_location_pattern(condition.pattern, subject, location.kind))
    if condition.title_pattern is not None:
        checks.append(_check_title_pattern(condition.title_pattern, location.title))
    if not checks:
        return ConditionResult(met=True, detail="location_matches: no pattern given, trivially met")
    met = all(passed for passed, _detail in checks)
    return ConditionResult(
        met=met, detail="location_matches: " + "; ".join(detail for _passed, detail in checks)
    )


def _location_subject(location: Location) -> str:
    if location.kind == "window":
        return location.title
    return urlsplit(location.value).path or "/"


def location_pattern_to_regex(pattern: str, case_sensitive: bool) -> re.Pattern[str]:
    """Translate a ':name' / '*' location pattern into an anchored regex."""
    trailing_wildcard = pattern.endswith("/*")
    body = pattern[:-2] if trailing_wildcard else pattern
    regex_body = _translate_location_body(body)
    if trailing_wildcard:
        regex_body += "(?:/.*)?"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(f"^{regex_body}$", flags)


def _translate_location_body(body: str) -> str:
    translated_parts: list[str] = []
    for literal_or_param in re.split(r"(:[A-Za-z_][A-Za-z0-9_]*)", body):
        if _PATH_PARAMETER.fullmatch(literal_or_param):
            translated_parts.append("[^/]+")
        else:
            translated_parts.append(
                ".*".join(re.escape(piece) for piece in literal_or_param.split("*"))
            )
    return "".join(translated_parts)


def _check_location_pattern(pattern: str, subject: str, kind: str) -> tuple[bool, str]:
    compiled = location_pattern_to_regex(pattern, case_sensitive=kind == "url")
    passed = compiled.fullmatch(subject) is not None
    verdict = "matches" if passed else "does not match"
    subject_name = "path" if kind == "url" else "window title"
    return passed, f"{subject_name} {subject!r} {verdict} {pattern!r}"


def _check_title_pattern(title_pattern: str, title: str) -> tuple[bool, str]:
    compiled = compile_pattern(title_pattern, re.IGNORECASE, "evaluate.location_matches")
    if compiled is None:
        return False, f"title_pattern {title_pattern!r} is not a valid regular expression"
    passed = compiled.search(title) is not None
    verdict = "matches" if passed else "does not match"
    return passed, f"title {title!r} {verdict} {title_pattern!r}"


# ---------------------------------------------------------------- dialog_open


def _evaluate_dialog_open(condition: DialogOpen, dialogs: list[Dialog]) -> ConditionResult:
    title_regex = _compile_optional(condition.title_pattern)
    text_regex = _compile_optional(condition.text_pattern)
    if _is_invalid(condition.title_pattern, title_regex) or _is_invalid(
        condition.text_pattern, text_regex
    ):
        return _invalid_pattern_result(
            "dialog_open", f"{condition.title_pattern} / {condition.text_pattern}"
        )
    wanted = f"title~{condition.title_pattern!r} text~{condition.text_pattern!r}"
    for index, dialog in enumerate(dialogs):
        if _regex_hits(title_regex, dialog.title) and _regex_hits(text_regex, dialog.text):
            return ConditionResult(
                met=True,
                detail=f"dialog_open: dialog[{index}] {_preview(dialog.title)!r} matches {wanted}",
            )
    seen_titles = [_preview(dialog.title or dialog.text) for dialog in dialogs]
    return ConditionResult(
        met=False, detail=f"dialog_open: no dialog matches {wanted}; open dialogs: {seen_titles}"
    )


def _compile_optional(pattern: str | None) -> re.Pattern[str] | None:
    if pattern is None:
        return None
    return compile_pattern(pattern, re.IGNORECASE, "evaluate.dialog_open")


def _is_invalid(pattern: str | None, compiled: re.Pattern[str] | None) -> bool:
    return pattern is not None and compiled is None


def _regex_hits(regex: re.Pattern[str] | None, text: str) -> bool:
    """A missing regex (no pattern given) matches anything."""
    return regex is None or regex.search(text) is not None


# ---------------------------------------------------------------- composites


def _evaluate_composite(
    condition: AllOf | AnyOf | Not, observation: Observation
) -> ConditionResult:
    if isinstance(condition, Not):
        return _evaluate_not(condition, observation)
    if isinstance(condition, AllOf):
        return _evaluate_all_of(condition, observation)
    return _evaluate_any_of(condition, observation)


def _evaluate_not(condition: Not, observation: Observation) -> ConditionResult:
    inner = evaluate(condition.condition, observation)
    return ConditionResult(met=not inner.met, detail=f"not({inner.detail})")


def _evaluate_all_of(condition: AllOf, observation: Observation) -> ConditionResult:
    child_details: list[str] = []
    for index, child in enumerate(condition.conditions):
        child_result = evaluate(child, observation)
        if not child_result.met:
            return ConditionResult(
                met=False, detail=f"all_of: condition [{index}] unmet: {child_result.detail}"
            )
        child_details.append(child_result.detail)
    return ConditionResult(met=True, detail="all_of: " + " AND ".join(child_details))


def _evaluate_any_of(condition: AnyOf, observation: Observation) -> ConditionResult:
    child_details: list[str] = []
    for index, child in enumerate(condition.conditions):
        child_result = evaluate(child, observation)
        if child_result.met:
            return ConditionResult(
                met=True, detail=f"any_of: condition [{index}] met: {child_result.detail}"
            )
        child_details.append(child_result.detail)
    return ConditionResult(met=False, detail="any_of: none met: " + " OR ".join(child_details))
