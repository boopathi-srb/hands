"""Validate caller inputs and resolve credentials into the params used for templating.

Runs before the surface is touched. Rules:
- unknown inputs are rejected (the contract is closed);
- a required input that is missing, None, or blank is rejected;
- optional inputs that are absent become '' so templates never keep a raw placeholder;
- integer / decimal / boolean / date inputs are coerced to a canonical string;
- `pattern` must fullmatch the canonical value;
- credential fields come from the CredentialProvider only, keyed 'credential.field' (e.g. 'teller.password').
Sensitive input values and every credential value are registered as secrets before anything is recorded.
Error messages name the field but never echo a sensitive value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from hands.core.artifact import Capability, CredentialSpec, InputSpec
from hands.core.log import get_logger, log_failure
from hands.core.ports import CredentialProvider
from hands.replay.context import SecretRegistrar
from hands.replay.values import CoercionError, coerce_value

_logger = get_logger(__name__)


class PreparedParams(BaseModel):
    params: dict[str, str]


class InputRejected(BaseModel):
    field: str
    message: str
    expected: str | None = None
    observed: str | None = None


def prepare_params(
    capability: Capability,
    inputs: Mapping[str, Any] | None,
    credentials: CredentialProvider,
    register_secret: SecretRegistrar | None,
) -> PreparedParams | InputRejected:
    """Caller inputs plus credential fields, validated and ready for templating."""
    supplied = dict(inputs or {})
    _register_sensitive_inputs(capability.inputs, supplied, register_secret)
    validated = validate_inputs(capability.inputs, supplied)
    if isinstance(validated, InputRejected):
        return validated
    resolved = resolve_credentials(capability.credentials, credentials, register_secret)
    if isinstance(resolved, InputRejected):
        return resolved
    return PreparedParams(params={**validated, **resolved})


def validate_inputs(specs: Mapping[str, InputSpec], supplied: Mapping[str, Any]) -> dict[str, str] | InputRejected:
    unknown_names = sorted(name for name in supplied if name not in specs)
    if unknown_names:
        return _reject(unknown_names[0], f"unknown input '{unknown_names[0]}'; declared inputs: {sorted(specs)}")
    params: dict[str, str] = {}
    for name, spec in specs.items():
        checked = validate_input(name, spec, supplied.get(name))
        if isinstance(checked, InputRejected):
            return checked
        params[name] = checked
    return params


def validate_input(name: str, spec: InputSpec, raw_value: Any) -> str | InputRejected:
    """The canonical string for one input, or why it was rejected."""
    text = _as_text(raw_value)
    if text is None or not text.strip():
        if spec.required:
            return _reject(name, f"missing required input '{name}'", expected=f"a {spec.type} value")
        return ""
    coerced = coerce_value(text, spec.type)
    if isinstance(coerced, CoercionError):
        return _reject(
            name, f"input '{name}' is not a valid {spec.type}: {coerced.reason}",
            expected=spec.type, observed=_shown(text, spec),
        )
    return _check_pattern(name, spec, coerced.text)


def resolve_credentials(
    specs: Mapping[str, CredentialSpec],
    provider: CredentialProvider,
    register_secret: SecretRegistrar | None,
) -> dict[str, str] | InputRejected:
    resolved: dict[str, str] = {}
    for credential_name, spec in specs.items():
        for field_name in spec.fields:
            key = f"{credential_name}.{field_name}"
            value = _fetch_credential(provider, credential_name, field_name)
            if not value:
                return _reject(key, f"credential '{key}' is missing from the credential provider")
            _register(register_secret, value, f"credential:{key}")
            resolved[key] = value
    return resolved


# ---------------------------------------------------------------- helpers


def _check_pattern(name: str, spec: InputSpec, canonical: str) -> str | InputRejected:
    if spec.pattern is None:
        return canonical
    try:
        compiled = re.compile(spec.pattern)
    except re.error as pattern_error:
        log_failure(_logger, "validate_input", f"invalid input pattern: {pattern_error}", input=name)
        return _reject(name, f"input '{name}' has an invalid pattern in the capability", expected=spec.pattern)
    if compiled.fullmatch(canonical) is None:
        return _reject(
            name, f"input '{name}' does not match the required pattern {spec.pattern!r}",
            expected=spec.pattern, observed=_shown(canonical, spec),
        )
    return canonical


def _fetch_credential(provider: CredentialProvider, credential_name: str, field_name: str) -> str | None:
    """I/O boundary: a vault-backed provider may fail; that is reported as a missing credential."""
    try:
        return provider.get(credential_name, field_name)
    except Exception as provider_error:  # noqa: BLE001 - adapter boundary, logged and returned as missing
        log_failure(
            _logger, "resolve_credentials", f"credential provider failed: {provider_error}",
            credential=credential_name, field=field_name,
        )
        return None


def _register_sensitive_inputs(
    specs: Mapping[str, InputSpec], supplied: Mapping[str, Any], register_secret: SecretRegistrar | None
) -> None:
    for name, spec in specs.items():
        text = _as_text(supplied.get(name))
        if spec.sensitive and text:
            _register(register_secret, text, f"input:{name}")


def _register(register_secret: SecretRegistrar | None, value: str, label: str) -> None:
    if register_secret is not None:
        register_secret(value, label)


def _as_text(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return "true" if raw_value else "false"
    return str(raw_value)


def _shown(value: str, spec: InputSpec) -> str:
    return f"<sensitive value, {len(value)} characters>" if spec.sensitive else repr(value)


def _reject(field: str, message: str, expected: str | None = None, observed: str | None = None) -> InputRejected:
    log_failure(_logger, "prepare_params", message, field=field)
    return InputRejected(field=field, message=message, expected=expected, observed=observed)
