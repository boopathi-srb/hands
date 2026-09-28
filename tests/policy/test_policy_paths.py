from __future__ import annotations

import pytest

from hands.policy.addresses import (
    looks_like_url,
    normalize_origin,
    parse_web_address,
)
from hands.policy.paths import (
    first_matching_pattern,
    normalize_url_path,
    path_matches,
    pattern_problem,
    split_pattern,
    title_matches,
)

# ---------------------------------------------------------------- normalize / split


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("", ()),
        ("/", ()),
        ("/t/lakeside/", ("t", "lakeside")),
        ("/a/./b/../c", ("a", "c")),
        ("/../../etc", ("etc",)),
        ("/t/lakeside/%2e%2e/_admin", ("t", "_admin")),
        ("//double//slash", ("double", "slash")),
    ],
)
def test_normalize_url_path(raw_path: str, expected: tuple[str, ...]) -> None:
    assert normalize_url_path(raw_path) == expected


def test_split_pattern_keeps_tokens_undecoded() -> None:
    assert split_pattern("/t/:tenant/**") == ("t", ":tenant", "**")
    assert split_pattern("") == ()


# ---------------------------------------------------------------- pattern validation


@pytest.mark.parametrize(
    ("pattern", "problem_fragment"),
    [
        ("t/lakeside", "must start with '/'"),
        ("/t/a**", "'**' must be a whole segment"),
        ("/t/../x", "'.' and '..'"),
        ("/t/:", "needs a parameter name"),
    ],
)
def test_pattern_problem_reports_invalid_patterns(pattern: str, problem_fragment: str) -> None:
    problem = pattern_problem(pattern)
    assert problem is not None and problem_fragment in problem


@pytest.mark.parametrize("pattern", ["/", "/t/*/**", "/t/:tenant/member/:id", "/reports/eod-*"])
def test_pattern_problem_accepts_valid_patterns(pattern: str) -> None:
    assert pattern_problem(pattern) is None


# ---------------------------------------------------------------- matching


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("/t/lakeside/inquiry", "/t/lakeside/inquiry", True),
        ("/t/lakeside/inquiry", "/t/lakeside/inquiry/", True),
        ("/t/lakeside/inquiry", "/t/prairie/inquiry", False),
        ("/t/:tenant/member/:id", "/t/prairie/member/10001", True),
        ("/t/:tenant/member/:id", "/t/prairie/member", False),
        ("/t/*/member/*/review", "/t/lakeside/member/10001/review", True),
        ("/t/*/member/*/review", "/t/lakeside/member/review", False),
        ("/t/*", "/t/a/b", False),
        ("/t/lakeside/**", "/t/lakeside", True),
        ("/t/lakeside/**", "/t/lakeside/member/10001/open-share", True),
        ("/t/lakeside/**", "/t/lakesideX/main", False),
        ("/**", "/", True),
        ("/", "/", True),
        ("/", "/x", False),
        ("/reports/eod-*", "/reports/eod-2026", True),
        ("/reports/eod-*", "/reports/weekly", False),
        ("/_admin/**", "/t/lakeside/../../_admin/faults", True),
        ("/t/**/review", "/t/a/b/c/review", True),
        ("/t/**/review", "/t/review", True),
    ],
)
def test_path_matches(pattern: str, path: str, expected: bool) -> None:
    assert path_matches(pattern, path) is expected


def test_segment_glob_does_not_treat_regex_characters_specially() -> None:
    assert path_matches("/a.b-*", "/a.b-c")
    assert not path_matches("/a.b-*", "/aXb-c")


def test_first_matching_pattern_returns_first_in_declaration_order() -> None:
    patterns = ["/t/prairie/**", "/t/*/**", "/t/lakeside/**"]
    assert first_matching_pattern(patterns, "/t/lakeside/main") == "/t/*/**"


def test_first_matching_pattern_none_and_empty() -> None:
    assert first_matching_pattern(["/t/prairie/**"], "/t/lakeside") is None
    assert first_matching_pattern([], "/anything") is None


@pytest.mark.parametrize(
    ("pattern", "title", "expected"),
    [
        ("*", "", True),
        ("*", "Calculator", True),
        ("Calculator", "Calculator", True),
        ("Calculator", "Calculator 2", False),
        ("Calc*", "Calculator", True),
        ("*Report*", "Daily Report (1)", True),
        ("a.c", "abc", False),
    ],
)
def test_title_matches(pattern: str, title: str, expected: bool) -> None:
    assert title_matches(pattern, title) is expected


# ---------------------------------------------------------------- addresses


def test_parse_web_address_normalizes_origin() -> None:
    address = parse_web_address("HTTP://127.0.0.1:8700/t/lakeside/login?next=1#top")
    assert address is not None
    assert address.origin == "http://127.0.0.1:8700"
    assert address.path == "/t/lakeside/login"


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("http://Example.com/x", "http://example.com:80"),
        ("https://example.com", "https://example.com:443"),
        ("http://[::1]:8700/", "http://[::1]:8700"),
    ],
)
def test_parse_web_address_default_ports_and_hosts(url: str, origin: str) -> None:
    address = parse_web_address(url)
    assert address is not None and address.origin == origin


@pytest.mark.parametrize(
    "url",
    [
        "",
        "about:blank",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://127.0.0.1:8700@evil.example/t/lakeside",
        "http://127.0.0.1:99999/",
        "http://127.0.0.1:abc/",
        "http:///nohost",
    ],
)
def test_parse_web_address_rejects_non_plain_urls(url: str) -> None:
    assert parse_web_address(url) is None


def test_parse_web_address_defaults_empty_path_to_root() -> None:
    address = parse_web_address("http://127.0.0.1:8700")
    assert address is not None and address.path == "/"


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("http://127.0.0.1:8700", "http://127.0.0.1:8700"),
        ("http://127.0.0.1:8700/", "http://127.0.0.1:8700"),
        ("https://Bank.example", "https://bank.example:443"),
        ("http://127.0.0.1:8700/t/lakeside", None),
        ("http://127.0.0.1:8700?x=1", None),
        ("ftp://127.0.0.1", None),
        ("127.0.0.1:8700", None),
        ("", None),
    ],
)
def test_normalize_origin(origin: str, expected: str | None) -> None:
    assert normalize_origin(origin) == expected


@pytest.mark.parametrize(
    ("entry_point", "expected"),
    [("http://127.0.0.1:8700/t", True), ("com.apple.calculator", False), ("", False)],
)
def test_looks_like_url(entry_point: str, expected: bool) -> None:
    assert looks_like_url(entry_point) is expected
