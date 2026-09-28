"""Individual, pure policy checks. Each returns a CheckResult naming the rule that decided it."""

from __future__ import annotations

from dataclasses import dataclass

from hands.core.actions import OpenAction
from hands.core.observation import Location
from hands.core.ports import PolicyRequest
from hands.policy.addresses import looks_like_url, parse_web_address
from hands.policy.config import (
    DesktopSurfacePolicy,
    ModeActionKinds,
    SurfacesPolicy,
    WebSurfacePolicy,
)
from hands.policy.paths import first_matching_pattern, title_matches


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    rule: str
    reason: str


def _passed(rule: str, reason: str) -> CheckResult:
    return CheckResult(passed=True, rule=rule, reason=reason)


def _failed(rule: str, reason: str) -> CheckResult:
    return CheckResult(passed=False, rule=rule, reason=reason)


# ---------------------------------------------------------------- web


def check_web_url(web: WebSurfacePolicy, url: str) -> CheckResult:
    """Origin allowlist, then blocked paths, then allowed paths."""
    address = parse_web_address(url)
    if address is None:
        return _failed("surfaces.web.allowed_origins", f"'{url}' is not a plain http(s) URL")
    if address.origin not in web.allowed_origins:
        return _failed(
            "surfaces.web.allowed_origins", f"origin {address.origin} is not allowlisted"
        )
    blocked_pattern = first_matching_pattern(web.blocked_path_patterns, address.path)
    if blocked_pattern is not None:
        return _failed(
            "surfaces.web.blocked_path_patterns",
            f"path {address.path} matches blocked pattern '{blocked_pattern}'",
        )
    allowed_pattern = first_matching_pattern(web.allowed_path_patterns, address.path)
    if allowed_pattern is None:
        return _failed(
            "surfaces.web.allowed_path_patterns", f"path {address.path} matches no allowed pattern"
        )
    return _passed(
        "surfaces.web.allowed_path_patterns",
        f"{address.origin}{address.path} allowed by '{allowed_pattern}'",
    )


# ---------------------------------------------------------------- desktop


def check_desktop_bundle(desktop: DesktopSurfacePolicy, bundle_id: str) -> CheckResult:
    if bundle_id not in desktop.allowed_bundle_ids:
        return _failed(
            "surfaces.desktop.allowed_bundle_ids", f"application '{bundle_id}' is not allowlisted"
        )
    return _passed(
        "surfaces.desktop.allowed_bundle_ids", f"application '{bundle_id}' is allowlisted"
    )


def check_desktop_window(
    desktop: DesktopSurfacePolicy, bundle_id: str, window_title: str
) -> CheckResult:
    bundle_check = check_desktop_bundle(desktop, bundle_id)
    if not bundle_check.passed:
        return bundle_check
    title_pattern = next(
        (
            pattern
            for pattern in desktop.allowed_window_title_patterns
            if title_matches(pattern, window_title)
        ),
        None,
    )
    if title_pattern is None:
        return _failed(
            "surfaces.desktop.allowed_window_title_patterns",
            f"window '{window_title}' of '{bundle_id}' matches no allowed title pattern",
        )
    return _passed(
        "surfaces.desktop.allowed_window_title_patterns",
        f"window '{window_title}' of '{bundle_id}' allowed by '{title_pattern}'",
    )


# ---------------------------------------------------------------- locations and entry points


def check_location(surfaces: SurfacesPolicy, location: Location) -> CheckResult:
    """Is the surface's current location allowlisted?"""
    if location.kind == "url":
        return check_web_url(surfaces.web, location.value)
    return check_desktop_window(surfaces.desktop, location.value, location.title)


def check_entry_point(surfaces: SurfacesPolicy, entry_point: str) -> CheckResult:
    """Is the target of an `open` action allowlisted? URLs are web targets; anything else is a bundle id."""
    if looks_like_url(entry_point):
        return check_web_url(surfaces.web, entry_point)
    return check_desktop_bundle(surfaces.desktop, entry_point)


def check_request_location(surfaces: SurfacesPolicy, request: PolicyRequest) -> CheckResult:
    """Current location must be allowlisted; `open` may also start from a start location and must target an
    allowlisted entry point."""
    if not isinstance(request.action, OpenAction):
        return check_location(surfaces, request.location)
    current_check = _check_open_origin(surfaces, request.location)
    if not current_check.passed:
        return current_check
    return check_entry_point(surfaces, request.action.entry_point)


def _check_open_origin(surfaces: SurfacesPolicy, location: Location) -> CheckResult:
    if location.value in surfaces.start_locations:
        return _passed(
            "surfaces.start_locations", f"'{location.value}' is a permitted start location"
        )
    return check_location(surfaces, location)


# ---------------------------------------------------------------- action kinds


def check_action_kind(allowed: ModeActionKinds, request: PolicyRequest) -> CheckResult:
    rule = f"actions.allowed.{request.mode}"
    action_kind = request.action.kind
    if action_kind not in allowed.for_mode(request.mode):
        return _failed(rule, f"'{action_kind}' actions are not allowed in {request.mode} mode")
    return _passed(rule, f"'{action_kind}' is allowed in {request.mode} mode")
