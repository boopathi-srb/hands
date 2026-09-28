"""Runtime configuration for the CoreOne mock target."""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, Field

DEFAULT_DEMO_PASSWORD = "demo-only-password"
DEFAULT_SLOW_DELAY_MS = 4000
PASSWORD_ENV_VAR = "HANDS_DEMO_PASSWORD"
FAULTS_ENV_VAR = "COREONE_FAULTS"


class AppConfig(BaseModel):
    """Everything the app factory needs. Built from env in production, directly in tests."""

    teller_user_id: str = "teller1"
    teller_password: str = DEFAULT_DEMO_PASSWORD
    seeded_faults: str = Field(
        default="", description="Fault spec, format 'fault:count[:tenant],...'."
    )
    default_slow_delay_ms: int = Field(default=DEFAULT_SLOW_DELAY_MS, ge=0)
    identity_override_answer: str = "supervisor-override"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppConfig:
        """Read the demo password and seeded faults from the environment."""
        source = os.environ if environ is None else environ
        return cls(
            teller_password=source.get(PASSWORD_ENV_VAR) or DEFAULT_DEMO_PASSWORD,
            seeded_faults=source.get(FAULTS_ENV_VAR, ""),
        )
