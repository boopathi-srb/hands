"""Credential provider backed by environment variables. Values never reach the model or the artifact."""

from __future__ import annotations

import os
from collections.abc import Mapping

from hands.core.log import get_logger, log_failure

logger = get_logger(__name__)

DEMO_DEFAULTS: dict[tuple[str, str], str] = {("teller", "username"): "teller1"}
DEMO_PASSWORD_ENV = "HANDS_DEMO_PASSWORD"
DEMO_PASSWORD_DEFAULT = "demo-only-password"


def credential_env_name(credential_name: str, field: str) -> str:
    """`teller.password` is read from `HANDS_CRED_TELLER_PASSWORD`."""
    return f"HANDS_CRED_{credential_name}_{field}".upper()


class EnvCredentialProvider:
    """Reads `HANDS_CRED_<NAME>_<FIELD>`; falls back to the mock app's demo teller for local runs."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    def get(self, credential_name: str, field: str) -> str | None:
        configured_value = self._environment.get(credential_env_name(credential_name, field))
        if configured_value:
            return configured_value
        demo_value = self._demo_value(credential_name, field)
        if demo_value is None:
            log_failure(logger, "EnvCredentialProvider.get", "credential not configured",
                        credential_name=credential_name, field=field)
        return demo_value

    def _demo_value(self, credential_name: str, field: str) -> str | None:
        if (credential_name, field) == ("teller", "password"):
            return self._environment.get(DEMO_PASSWORD_ENV) or DEMO_PASSWORD_DEFAULT
        return DEMO_DEFAULTS.get((credential_name, field))
