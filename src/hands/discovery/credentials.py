"""SecretBook: credential values resolved at the seam, known to the loop and never to the model.

The planner only ever sees placeholder names such as `{{teller.password}}`. The loop substitutes the
real value into the surface action at the last moment, registers every value with the redaction
registrar, and masks values anywhere they might echo back (observations, rationales, errors).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from hands.core.log import get_logger, log_failure
from hands.core.ports import CredentialProvider
from hands.discovery.render import mask_secrets

_logger = get_logger(__name__)

DEFAULT_CREDENTIAL_FIELDS: tuple[str, ...] = ("username", "password")
SecretRegistrar = Callable[[str, str], object]


def placeholder(name: str) -> str:
    return f"{{{{{name}}}}}"


def expand_credential_names(credential_names: Sequence[str]) -> list[str]:
    """'teller' -> ['teller.username', 'teller.password']; 'teller.pin' stays as is."""
    expanded: list[str] = []
    for credential_name in credential_names:
        cleaned = credential_name.strip()
        if not cleaned:
            continue
        names = [cleaned] if "." in cleaned else [f"{cleaned}.{field}" for field in DEFAULT_CREDENTIAL_FIELDS]
        expanded.extend(name for name in names if name not in expanded)
    return expanded


class SecretBook:
    """Resolved credential fields keyed by placeholder name ('teller.password')."""

    def __init__(self, values_by_name: dict[str, str] | None = None) -> None:
        self._values_by_name = dict(values_by_name or {})

    @classmethod
    def resolve(
        cls,
        provider: CredentialProvider,
        credential_names: Sequence[str],
        registrar: SecretRegistrar | None = None,
    ) -> SecretBook:
        """Fetch every requested field; missing ones are logged and left out (their placeholder is
        then unknown, so a decision using it is rejected with feedback)."""
        values_by_name: dict[str, str] = {}
        for name in expand_credential_names(credential_names):
            value = _fetch(provider, name)
            if value is None:
                continue
            values_by_name[name] = value
            if registrar is not None:
                registrar(value, name)
        return cls(values_by_name)

    @property
    def names(self) -> list[str]:
        return list(self._values_by_name)

    @property
    def placeholders(self) -> list[str]:
        return [placeholder(name) for name in self._values_by_name]

    @property
    def values(self) -> list[str]:
        return list(self._values_by_name.values())

    @property
    def params(self) -> dict[str, str]:
        return dict(self._values_by_name)

    def contains_secret(self, text: str | None) -> bool:
        return bool(text) and any(value in (text or "") for value in self.values)

    def mask(self, text: str) -> str:
        return mask_secrets(text, self.values)

    def mask_optional(self, text: str | None) -> str | None:
        return None if text is None else self.mask(text)


def _fetch(provider: CredentialProvider, name: str) -> str | None:
    credential_name, field = name.split(".", 1)
    value = provider.get(credential_name, field)
    if not value:
        log_failure(_logger, "SecretBook.resolve", "credential field not available",
                    credential=credential_name, field=field)
        return None
    return value
