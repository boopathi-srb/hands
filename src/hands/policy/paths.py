"""URL path and title pattern matching shared by allowlists and risk rules.

Path pattern grammar (segment based, '/' separated, case sensitive):

- a literal segment matches itself                    '/t/lakeside/inquiry'
- ':name' matches exactly one non-empty segment       '/t/:tenant/member/:id'
- '*' matches exactly one non-empty segment           '/t/*/member/*/review'
- '*' inside a segment is a glob within that segment  '/reports/eod-*'
- '**' matches zero or more whole segments            '/t/lakeside/**'

Paths are normalized before matching: percent-decoded, empty and '.' segments dropped, '..' resolved, so
'/t/lakeside/../_admin/faults' is judged as '/_admin/faults'. Query strings and fragments are never part of a path.

Title patterns (desktop window titles) are whole-string globs where '*' matches any run of characters.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import unquote

ANY_SEGMENTS = "**"
ANY_SEGMENT = "*"
PARAM_PREFIX = ":"


def normalize_url_path(raw_path: str) -> tuple[str, ...]:
    """Percent-decode a URL path and resolve '.' and '..' into a tuple of segments."""
    resolved_segments: list[str] = []
    for segment in unquote(raw_path).split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if resolved_segments:
                resolved_segments.pop()
            continue
        resolved_segments.append(segment)
    return tuple(resolved_segments)


def split_pattern(pattern: str) -> tuple[str, ...]:
    """Split a path pattern into segments without decoding (patterns are written by policy authors)."""
    return tuple(segment for segment in pattern.split("/") if segment)


def pattern_problem(pattern: str) -> str | None:
    """Return why a path pattern is invalid, or None when it is well formed."""
    if not pattern.startswith("/"):
        return f"path pattern '{pattern}' must start with '/'"
    for segment in split_pattern(pattern):
        if ANY_SEGMENTS in segment and segment != ANY_SEGMENTS:
            return f"path pattern '{pattern}': '**' must be a whole segment"
        if segment in (".", ".."):
            return f"path pattern '{pattern}': '.' and '..' segments are not allowed"
        if segment == PARAM_PREFIX:
            return f"path pattern '{pattern}': ':' needs a parameter name"
    return None


def path_matches(pattern: str, raw_path: str) -> bool:
    """True when the normalized path matches the pattern."""
    return _segments_match(split_pattern(pattern), normalize_url_path(raw_path))


def first_matching_pattern(patterns: list[str], raw_path: str) -> str | None:
    """The first pattern (in declaration order) that matches the path, else None."""
    return next((pattern for pattern in patterns if path_matches(pattern, raw_path)), None)


def title_matches(pattern: str, title: str) -> bool:
    """Whole-string glob match for window titles; '*' matches any characters, including none."""
    return _compiled_title_glob(pattern).fullmatch(title) is not None


def _segments_match(pattern_segments: tuple[str, ...], path_segments: tuple[str, ...]) -> bool:
    if not pattern_segments:
        return not path_segments
    head, remaining_pattern = pattern_segments[0], pattern_segments[1:]
    if head == ANY_SEGMENTS:
        return any(
            _segments_match(remaining_pattern, path_segments[split_at:])
            for split_at in range(len(path_segments) + 1)
        )
    if not path_segments:
        return False
    return _segment_matches(head, path_segments[0]) and _segments_match(
        remaining_pattern, path_segments[1:]
    )


def _segment_matches(pattern_segment: str, path_segment: str) -> bool:
    if pattern_segment == ANY_SEGMENT or pattern_segment.startswith(PARAM_PREFIX):
        return bool(path_segment)
    if ANY_SEGMENT in pattern_segment:
        return _compiled_segment_glob(pattern_segment).fullmatch(path_segment) is not None
    return pattern_segment == path_segment


@lru_cache(maxsize=256)
def _compiled_segment_glob(pattern_segment: str) -> re.Pattern[str]:
    literal_parts = [re.escape(part) for part in pattern_segment.split(ANY_SEGMENT)]
    return re.compile("[^/]*".join(literal_parts))


@lru_cache(maxsize=256)
def _compiled_title_glob(pattern: str) -> re.Pattern[str]:
    literal_parts = [re.escape(part) for part in pattern.split(ANY_SEGMENT)]
    return re.compile(".*".join(literal_parts), re.DOTALL)
