"""The policy file: a YAML document validated into these models, loaded without raising.

A policy is deny-by-default. Nothing is reachable unless an allowlist names it, no action kind is usable in a
mode unless listed, and every model is `extra="forbid"` so a misspelled key fails loudly instead of silently
widening access. See `policies/coreone.yaml` for a complete example.

Top-level shape::

    version: 1
    name: coreone
    description: ...
    surfaces:
      start_locations: [about:blank]
      web:
        allowed_origins: [http://127.0.0.1:8700]
        allowed_path_patterns: ['/t/lakeside/**']
        blocked_path_patterns: ['/_admin/**']
      desktop:
        allowed_bundle_ids: [com.apple.calculator]
        allowed_window_title_patterns: ['*']
    actions:
      allowed:
        discovery: [open, click, type, press, select, scroll]
        replay: [...]
        human: [...]
    risk:
      default: safe
      rules:
        - name: irreversible-controls
          description: ...
          match: {control_pattern: '\\b(submit|delete)\\b', action_kinds: [click, press]}
      handling:
        discovery: escalate
        replay: allow_if_approved_and_confirmed
        human: allow
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from hands.core.actions import ActionKind
from hands.core.artifact import SLUG_PATTERN, Risk
from hands.core.log import get_logger, log_failure
from hands.policy.addresses import normalize_origin
from hands.policy.paths import pattern_problem

Mode = Literal["discovery", "replay", "human"]
RiskHandling = Literal["allow", "deny", "escalate", "allow_if_approved_and_confirmed"]
PolicyLoadErrorCode = Literal["file_not_found", "unreadable", "invalid_yaml", "invalid_schema"]

_logger = get_logger(__name__)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validate_path_patterns(patterns: list[str]) -> list[str]:
    for pattern in patterns:
        problem = pattern_problem(pattern)
        if problem is not None:
            raise ValueError(problem)
    return patterns


def _validate_regex(pattern: str | None) -> str | None:
    if pattern is None:
        return None
    try:
        re.compile(pattern)
    except re.error as regex_error:
        raise ValueError(f"invalid regex '{pattern}': {regex_error}") from regex_error
    return pattern


# ---------------------------------------------------------------- surfaces


class WebSurfacePolicy(_StrictModel):
    """Which web locations automation may observe and act on."""

    allowed_origins: list[str] = Field(
        default_factory=list,
        description="Exact origins (scheme://host:port). Default ports are made explicit when compared.",
    )
    allowed_path_patterns: list[str] = Field(
        default_factory=list,
        description="A URL on an allowed origin must match at least one of these path patterns.",
    )
    blocked_path_patterns: list[str] = Field(
        default_factory=list,
        description="Checked before the allowlist; a match denies even if an allowed pattern also matches.",
    )

    @field_validator("allowed_origins")
    @classmethod
    def _origins_are_bare(cls, origins: list[str]) -> list[str]:
        normalized_origins = []
        for origin in origins:
            normalized = normalize_origin(origin)
            if normalized is None:
                raise ValueError(
                    f"'{origin}' is not a bare http(s) origin like http://127.0.0.1:8700"
                )
            normalized_origins.append(normalized)
        return normalized_origins

    @field_validator("allowed_path_patterns", "blocked_path_patterns")
    @classmethod
    def _patterns_are_valid(cls, patterns: list[str]) -> list[str]:
        return _validate_path_patterns(patterns)


class DesktopSurfacePolicy(_StrictModel):
    """Which desktop applications and windows automation may observe and act on."""

    allowed_bundle_ids: list[str] = Field(
        default_factory=list, description="Exact bundle identifiers, e.g. com.apple.calculator."
    )
    allowed_window_title_patterns: list[str] = Field(
        default_factory=lambda: ["*"],
        description="The window title must match one of these globs ('*' = any characters).",
    )


class SurfacesPolicy(_StrictModel):
    web: WebSurfacePolicy = Field(default_factory=WebSurfacePolicy)
    desktop: DesktopSurfacePolicy = Field(default_factory=DesktopSurfacePolicy)
    start_locations: list[str] = Field(
        default_factory=lambda: ["about:blank"],
        description=(
            "Exact Location.value strings from which an `open` action may start even though they are not "
            "allowlisted (a fresh browser tab). No other action kind is permitted there."
        ),
    )


# ---------------------------------------------------------------- actions


class ModeActionKinds(_StrictModel):
    """Action kinds usable in each mode. A mode that is omitted may not act at all."""

    discovery: list[ActionKind] = Field(default_factory=list)
    replay: list[ActionKind] = Field(default_factory=list)
    human: list[ActionKind] = Field(default_factory=list)

    def for_mode(self, mode: Mode) -> list[ActionKind]:
        kinds_by_mode = {"discovery": self.discovery, "replay": self.replay, "human": self.human}
        return kinds_by_mode[mode]


class ActionsPolicy(_StrictModel):
    allowed: ModeActionKinds = Field(default_factory=ModeActionKinds)


# ---------------------------------------------------------------- risk


class RiskMatch(_StrictModel):
    """Criteria of one risk rule. Every criterion that is set must hold (logical AND); at least one is set.

    Control patterns are case-insensitive regexes searched in the target node's name, text and label.
    `control_pattern` never matches an action without a target node; `control_exclude_pattern` is satisfied
    by such an action, so exclusions stay conservative.
    """

    control_pattern: str | None = Field(default=None, description="Regex; the control must match.")
    control_exclude_pattern: str | None = Field(
        default=None,
        description="Regex; the control must NOT match (e.g. Cancel on a review page).",
    )
    path_patterns: list[str] = Field(
        default_factory=list,
        description="URL path patterns; for `open` the entry point's path, otherwise the current location.",
    )
    action_kinds: list[ActionKind] = Field(
        default_factory=list, description="Action kinds this rule covers."
    )

    @field_validator("control_pattern", "control_exclude_pattern")
    @classmethod
    def _regex_compiles(cls, pattern: str | None) -> str | None:
        return _validate_regex(pattern)

    @field_validator("path_patterns")
    @classmethod
    def _patterns_are_valid(cls, patterns: list[str]) -> list[str]:
        return _validate_path_patterns(patterns)

    @model_validator(mode="after")
    def _has_a_criterion(self) -> RiskMatch:
        has_criterion = any(
            [
                self.control_pattern,
                self.control_exclude_pattern,
                self.path_patterns,
                self.action_kinds,
            ]
        )
        if not has_criterion:
            raise ValueError("a risk rule match needs at least one criterion")
        return self


class RiskRule(_StrictModel):
    """Classifies matching actions. Rules are evaluated in order and the first match wins."""

    name: str = Field(pattern=SLUG_PATTERN)
    description: str
    match: RiskMatch
    risk: Risk = Field(default="risky", description="Risk assigned when this rule matches.")


class ModeRiskHandling(_StrictModel):
    """What happens to a risky action in each mode. All three modes must be stated explicitly.

    - allow: permitted and flagged in the decision reason for audit
    - deny: refused
    - escalate: a human decides (the caller raises an intervention)
    - allow_if_approved_and_confirmed: permitted only when the capability status is `approved` AND the caller
      passed `risky_confirmed=True`; otherwise denied
    """

    discovery: RiskHandling
    replay: RiskHandling
    human: RiskHandling

    def for_mode(self, mode: Mode) -> RiskHandling:
        handling_by_mode = {"discovery": self.discovery, "replay": self.replay, "human": self.human}
        return handling_by_mode[mode]


class RiskPolicy(_StrictModel):
    default: Risk = Field(default="safe", description="Risk when no rule matches.")
    rules: list[RiskRule] = Field(default_factory=list)
    handling: ModeRiskHandling

    @field_validator("rules")
    @classmethod
    def _rule_names_unique(cls, rules: list[RiskRule]) -> list[RiskRule]:
        seen_names: list[str] = []
        for rule in rules:
            if rule.name in seen_names:
                raise ValueError(f"duplicate risk rule name '{rule.name}'")
            seen_names.append(rule.name)
        return rules


# ---------------------------------------------------------------- the policy


class PolicyConfig(_StrictModel):
    version: Literal[1] = 1
    name: str = Field(min_length=1)
    description: str = ""
    surfaces: SurfacesPolicy = Field(default_factory=SurfacesPolicy)
    actions: ActionsPolicy = Field(default_factory=ActionsPolicy)
    risk: RiskPolicy


# ---------------------------------------------------------------- loading


@dataclass(frozen=True)
class PolicyLoaded:
    config: PolicyConfig
    source: str
    ok: Literal[True] = True


@dataclass(frozen=True)
class PolicyLoadFailed:
    code: PolicyLoadErrorCode
    message: str
    source: str
    ok: Literal[False] = False


PolicyLoadResult = PolicyLoaded | PolicyLoadFailed


def load_policy(path: str | Path) -> PolicyLoadResult:
    """Read, parse and validate a policy file. Never raises; failures are typed and logged."""
    policy_path = Path(path)
    if not policy_path.is_file():
        return _failure(
            "load_policy",
            "file_not_found",
            f"policy file not found: {policy_path}",
            str(policy_path),
        )
    try:
        policy_text = policy_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as read_error:
        return _failure(
            "load_policy", "unreadable", f"cannot read policy: {read_error}", str(policy_path)
        )
    return parse_policy(policy_text, source=str(policy_path))


def parse_policy(policy_text: str, source: str = "<string>") -> PolicyLoadResult:
    """Parse YAML text and validate it as a policy."""
    try:
        document = yaml.safe_load(policy_text)
    except yaml.YAMLError as yaml_error:
        return _failure("parse_policy", "invalid_yaml", f"invalid YAML: {yaml_error}", source)
    if not isinstance(document, dict):
        return _failure(
            "parse_policy", "invalid_schema", "policy document must be a mapping", source
        )
    return policy_from_mapping(document, source=source)


def policy_from_mapping(document: dict[str, Any], source: str = "<mapping>") -> PolicyLoadResult:
    """Validate an already-parsed mapping as a policy."""
    try:
        config = PolicyConfig.model_validate(document)
    except ValidationError as validation_error:
        message = f"invalid policy: {_summarize_validation(validation_error)}"
        return _failure("policy_from_mapping", "invalid_schema", message, source)
    return PolicyLoaded(config=config, source=source)


def _summarize_validation(validation_error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in validation_error.errors()
    )


def _failure(
    function_name: str, code: PolicyLoadErrorCode, message: str, source: str
) -> PolicyLoadFailed:
    log_failure(_logger, function_name, message, source=source, code=code)
    return PolicyLoadFailed(code=code, message=message, source=source)
