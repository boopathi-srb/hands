"""The Redactor: one object every evidence write, log line and operator view passes through.

Order of application to any string (deterministic):
1. exact registered secrets (and their URL/JSON/HTML encodings), longest first -> [REDACTED:<label>]
2. pattern rules in `hands.redact.patterns.build_rules` order                 -> [REDACTED:<kind>]

Structured data additionally masks whole values under sensitive keys (password, token, ssn, ...), and
observations additionally mask password fields and fields labelled as sensitive, regardless of content.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel

from hands.core.observation import Dialog, Location, Node, Observation, Rect
from hands.redact.fields import (
    DEFAULT_PASSWORD_PATTERN,
    DEFAULT_SENSITIVE_KEYS,
    DEFAULT_SENSITIVE_LABEL_PATTERN,
    FieldRules,
    is_password_field,
    is_sensitive_key,
    is_sensitive_labelled_field,
)
from hands.redact.patterns import REDACTION_PREFIX, apply_rule, build_rules, redaction_marker
from hands.redact.screenshot import DEFAULT_PADDING_PX, black_out
from hands.redact.secrets import SecretRegistry, normalize_label

PASSWORD_LABEL = "password"
SENSITIVE_FIELD_LABEL = "sensitive_field"


class RedactionConfig(BaseModel):
    """Tunable parts of redaction. The defaults are the conservative, bank-appropriate choice."""

    redact_amounts: bool = False
    password_field_pattern: str = DEFAULT_PASSWORD_PATTERN
    sensitive_field_label_pattern: str = DEFAULT_SENSITIVE_LABEL_PATTERN
    sensitive_keys: tuple[str, ...] = DEFAULT_SENSITIVE_KEYS


class Redactor:
    """Masks sensitive values in text, structured data, observations and screenshots."""

    def __init__(self, config: RedactionConfig | None = None) -> None:
        effective_config = config or RedactionConfig()
        self._rules = build_rules(effective_config.redact_amounts)
        self._field_rules = FieldRules(
            password_pattern=re.compile(effective_config.password_field_pattern, re.IGNORECASE),
            sensitive_label_pattern=re.compile(
                effective_config.sensitive_field_label_pattern, re.IGNORECASE
            ),
            sensitive_keys=frozenset(key.lower() for key in effective_config.sensitive_keys),
        )
        self._secrets = SecretRegistry()

    # ------------------------------------------------------------ secrets

    def register_secret(self, value: str | None, label: str) -> bool:
        """Mask this exact value everywhere from now on. False for None/empty values (nothing registered)."""
        return self._secrets.register(value, label)

    @property
    def secret_count(self) -> int:
        """Number of registered variants (each secret adds itself plus its distinct encodings)."""
        return len(self._secrets)

    # ------------------------------------------------------------ text and data

    def redact_text(self, text: str) -> str:
        if not text:
            return text
        redacted = self._secrets.mask(text)
        for rule in self._rules:
            redacted = apply_rule(rule, redacted)
        return redacted

    def redact_value(self, value: Any) -> Any:
        """Recursively redact plain data and pydantic models; always returns JSON-compatible plain data."""
        if isinstance(value, BaseModel):
            return self.redact_value(value.model_dump(mode="json"))
        if isinstance(value, Mapping):
            return self._redact_mapping(value)
        if isinstance(value, list | tuple | set | frozenset):
            return [self.redact_value(item) for item in _stable_items(value)]
        return self._redact_scalar(value)

    def _redact_mapping(self, mapping: Mapping[Any, Any]) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, item in mapping.items():
            key_text = self.redact_text(str(key))
            if is_sensitive_key(str(key), self._field_rules) and item not in (None, ""):
                redacted[key_text] = redaction_marker(normalize_label(str(key).lower()))
            else:
                redacted[key_text] = self.redact_value(item)
        return redacted

    def _redact_scalar(self, value: Any) -> Any:
        if value is None or isinstance(value, bool | float):
            return value
        if isinstance(value, int):
            redacted_digits = self.redact_text(str(value))
            return value if redacted_digits == str(value) else redacted_digits
        if isinstance(value, bytes | bytearray | memoryview):
            return f"<{len(bytes(value))} bytes omitted>"
        if isinstance(value, datetime | date | time):
            return value.isoformat()
        if isinstance(value, Enum):
            return self._redact_scalar(value.value)
        return self.redact_text(str(value))

    # ------------------------------------------------------------ observations

    def redact_node(self, node: Node) -> Node:
        """Redact every free-text field; password and sensitive-labelled fields lose their value entirely."""
        whole_value_label = self._whole_value_label(node)
        return node.model_copy(
            update={
                "name": self.redact_text(node.name),
                "label": self.redact_text(node.label) if node.label is not None else None,
                "text": self._mask_or_redact(node.text, whole_value_label),
                "value": self._mask_or_redact(node.value, whole_value_label),
                "container_path": tuple(self.redact_text(part) for part in node.container_path),
            }
        )

    def redact_dialog(self, dialog: Dialog) -> Dialog:
        return dialog.model_copy(
            update={"title": self.redact_text(dialog.title), "text": self.redact_text(dialog.text)}
        )

    def redact_location(self, location: Location) -> Location:
        return location.model_copy(
            update={
                "value": self.redact_text(location.value),
                "title": self.redact_text(location.title),
            }
        )

    def redact_observation(
        self, observation: Observation, screenshot_scale: float = 1.0
    ) -> Observation:
        """A redacted copy. A screenshot, if present, is masked using the ORIGINAL nodes' bounds."""
        masked_screenshot = (
            self.mask_screenshot(observation.screenshot_png, observation, scale=screenshot_scale)
            if observation.screenshot_png is not None
            else None
        )
        return observation.model_copy(
            update={
                "location": self.redact_location(observation.location),
                "nodes": [self.redact_node(node) for node in observation.nodes],
                "dialogs": [self.redact_dialog(dialog) for dialog in observation.dialogs],
                "screenshot_png": masked_screenshot,
            }
        )

    def node_needs_mask(self, node: Node) -> bool:
        """True for password fields, sensitive-labelled fields, and nodes with any redacted text."""
        if self._whole_value_label(node) is not None:
            return True
        texts = [node.name, node.text, node.value or "", node.label or ""]
        return any(
            REDACTION_PREFIX in text or self.redact_text(text) != text for text in texts if text
        )

    def sensitive_rects(self, observation: Observation) -> list[Rect]:
        return [
            node.bounds
            for node in observation.nodes
            if node.bounds is not None and self.node_needs_mask(node)
        ]

    def mask_screenshot(
        self,
        png: bytes,
        observation: Observation,
        scale: float = 1.0,
        padding: int = DEFAULT_PADDING_PX,
    ) -> bytes:
        """Black out the bounds of every sensitive node. `scale` = screenshot pixels per CSS pixel.

        Limit: pixels not described by the accessibility tree cannot be detected and are not masked.
        """
        return black_out(png, self.sensitive_rects(observation), scale=scale, padding=padding)

    # ------------------------------------------------------------ helpers

    def _whole_value_label(self, node: Node) -> str | None:
        if is_password_field(node, self._field_rules):
            return PASSWORD_LABEL
        if is_sensitive_labelled_field(node, self._field_rules):
            return SENSITIVE_FIELD_LABEL
        return None

    def _mask_or_redact(self, text: str | None, whole_value_label: str | None) -> Any:
        if not text:
            return text
        if whole_value_label is not None:
            return redaction_marker(whole_value_label)
        return self.redact_text(text)


def _stable_items(collection: list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any]) -> list[Any]:
    """Sets have no order; sort them by repr so redacted output is deterministic."""
    if isinstance(collection, set | frozenset):
        return sorted(collection, key=repr)
    return list(collection)
