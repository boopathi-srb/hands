"""Tiny semantic-version helpers: parse 'x.y.z', pick the latest, and check '>=x,<y' style ranges.

Only what the catalog needs: numeric major.minor.patch, no pre-release tags. Ranges are comma-separated
comparators (`>=`, `>`, `<=`, `<`, `==`, `=`, or a bare version meaning `==`); `*` or an empty range
matches every version.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from pydantic import BaseModel

from hands.core.log import get_logger, log_failure

_logger = get_logger(__name__)

SemVer = tuple[int, int, int]

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_COMPARATOR = re.compile(r"^(>=|<=|==|=|>|<)?\s*(\S+)$")
_OPERATORS: dict[str, Callable[[SemVer, SemVer], bool]] = {
    ">=": lambda version, bound: version >= bound,
    ">": lambda version, bound: version > bound,
    "<=": lambda version, bound: version <= bound,
    "<": lambda version, bound: version < bound,
    "==": lambda version, bound: version == bound,
    "=": lambda version, bound: version == bound,
    "": lambda version, bound: version == bound,
}


class RangeCheck(BaseModel):
    """Whether a version satisfies a range; `error` explains an unparsable version or range."""

    satisfied: bool
    error: str | None = None


def parse_semver(text: str | None) -> SemVer | None:
    """'1.2.3' -> (1, 2, 3); anything else -> None."""
    if not text:
        return None
    match = _SEMVER.fullmatch(text.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def latest_version(versions: Iterable[str]) -> str | None:
    """The highest valid semver in `versions`, or None when there is none."""
    parsed = [(parse_semver(version), version) for version in versions]
    valid = [(semver, version) for semver, version in parsed if semver is not None]
    if not valid:
        return None
    return max(valid)[1]


def sort_versions(versions: Iterable[str]) -> list[str]:
    """Valid semvers in ascending order; invalid strings are dropped."""
    parsed = [(parse_semver(version), version) for version in versions]
    return [version for semver, version in sorted(item for item in parsed if item[0] is not None)]


def satisfies_range(version: str, version_range: str | None) -> RangeCheck:
    """Does `version` satisfy every comparator in `version_range`?"""
    parsed_version = parse_semver(version)
    if parsed_version is None:
        log_failure(_logger, "satisfies_range", "version is not semver", version=version)
        return RangeCheck(satisfied=False, error=f"version '{version}' is not x.y.z")
    comparators = _split_range(version_range)
    for comparator in comparators:
        comparator_check = _check_comparator(parsed_version, comparator)
        if comparator_check.error is not None or not comparator_check.satisfied:
            return comparator_check
    return RangeCheck(satisfied=True)


def _split_range(version_range: str | None) -> list[str]:
    if version_range is None:
        return []
    parts = [part.strip() for part in version_range.split(",")]
    return [part for part in parts if part and part != "*"]


def _check_comparator(version: SemVer, comparator: str) -> RangeCheck:
    match = _COMPARATOR.fullmatch(comparator)
    bound = parse_semver(match.group(2)) if match else None
    if match is None or bound is None:
        log_failure(_logger, "satisfies_range", "unparsable comparator", comparator=comparator)
        return RangeCheck(satisfied=False, error=f"range comparator '{comparator}' is not valid")
    operator = match.group(1) or ""
    return RangeCheck(satisfied=_OPERATORS[operator](version, bound))


def next_minor(version: str) -> str | None:
    """`1.0.0` -> `1.1.0`: a re-recorded flow is a compatible new version. None for an invalid version."""
    parsed = parse_semver(version)
    if parsed is None:
        return None
    major, minor, _patch = parsed
    return f"{major}.{minor + 1}.0"
