"""AppProfile model and loader."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from hands.core.artifact import CredentialSpec, OutcomeDetector, RecoveryRule, Step
from hands.core.log import get_logger, log_failure

logger = get_logger(__name__)


class AppProfile(BaseModel):
    vendor: str
    product: str
    product_versions: list[str] = Field(description="Versions this profile was validated against.")
    surface: str = "web"
    credentials: dict[str, CredentialSpec] = Field(default_factory=dict)
    subflows: dict[str, list[Step]] = Field(default_factory=dict)
    outcomes: list[OutcomeDetector] = Field(default_factory=list)
    recoveries: list[RecoveryRule] = Field(default_factory=list)
    login_subflow: str | None = Field(default=None, description="Subflow that establishes a session.")


class ProfileLoadResult(BaseModel):
    profile: AppProfile | None = None
    error: str | None = None


def load_profile(path: str | Path) -> ProfileLoadResult:
    """Load and validate a profile YAML file. Returns an error result instead of raising."""
    profile_path = Path(path)
    if not profile_path.is_file():
        log_failure(logger, "load_profile", "file not found", path=str(profile_path))
        return ProfileLoadResult(error=f"profile not found: {profile_path}")
    raw_document = _read_yaml(profile_path)
    if raw_document is None:
        return ProfileLoadResult(error=f"profile is not valid YAML: {profile_path}")
    return _validate_profile(raw_document, profile_path)


def _read_yaml(profile_path: Path) -> dict[str, object] | None:
    try:
        loaded = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as read_error:
        log_failure(logger, "_read_yaml", str(read_error), path=str(profile_path))
        return None
    return loaded if isinstance(loaded, dict) else None


def _validate_profile(raw_document: dict[str, object], profile_path: Path) -> ProfileLoadResult:
    try:
        return ProfileLoadResult(profile=AppProfile.model_validate(raw_document))
    except ValidationError as validation_error:
        log_failure(logger, "_validate_profile", str(validation_error), path=str(profile_path))
        return ProfileLoadResult(error=f"profile failed validation: {validation_error}")
