"""Thin, mockable wrapper over the macOS Accessibility (AX) C API.

Everything above this module talks to an `AxBackend`, never to pyobjc directly, so the tree builder,
the surface and the live view are testable with an in-memory fake. Every backend call returns an
`AxResult` (a value or an AX error code); nothing here raises for AX errors.

Expected absences (an attribute the element does not support, or that currently has no value) are
normal while walking a tree and are returned without logging. Every other error is logged with
`log_failure` including the function name and inputs.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Generic, Protocol, TypeAlias, TypeVar

from hands.core.log import get_logger, log_failure

logger = get_logger(__name__)

ValueType = TypeVar("ValueType")

AxElement: TypeAlias = Any
"""Opaque AXUIElementRef (real backend) or fake element (tests). Only the backend looks inside."""

# ---------------------------------------------------------------- error codes

AX_SUCCESS = 0
AX_ERROR_FAILURE = -25200
AX_ERROR_ILLEGAL_ARGUMENT = -25201
AX_ERROR_INVALID_UI_ELEMENT = -25202
AX_ERROR_CANNOT_COMPLETE = -25204
AX_ERROR_ATTRIBUTE_UNSUPPORTED = -25205
AX_ERROR_ACTION_UNSUPPORTED = -25206
AX_ERROR_NOT_IMPLEMENTED = -25208
AX_ERROR_API_DISABLED = -25211
AX_ERROR_NO_VALUE = -25212
BACKEND_UNAVAILABLE = -1
"""Synthetic code: the pyobjc ApplicationServices module could not be imported."""

AX_ERROR_NAMES: dict[int, str] = {
    AX_SUCCESS: "success",
    AX_ERROR_FAILURE: "failure",
    AX_ERROR_ILLEGAL_ARGUMENT: "illegal_argument",
    AX_ERROR_INVALID_UI_ELEMENT: "invalid_ui_element",
    -25203: "invalid_ui_element_observer",
    AX_ERROR_CANNOT_COMPLETE: "cannot_complete",
    AX_ERROR_ATTRIBUTE_UNSUPPORTED: "attribute_unsupported",
    AX_ERROR_ACTION_UNSUPPORTED: "action_unsupported",
    -25207: "notification_unsupported",
    AX_ERROR_NOT_IMPLEMENTED: "not_implemented",
    -25209: "notification_already_registered",
    -25210: "notification_not_registered",
    AX_ERROR_API_DISABLED: "api_disabled",
    AX_ERROR_NO_VALUE: "no_value",
    -25213: "parameterized_attribute_unsupported",
    -25214: "not_enough_precision",
    BACKEND_UNAVAILABLE: "backend_unavailable",
}

EXPECTED_ABSENCE_CODES = frozenset(
    {AX_ERROR_NO_VALUE, AX_ERROR_ATTRIBUTE_UNSUPPORTED, AX_ERROR_ACTION_UNSUPPORTED}
)

# AXValueType constants (stable ABI values from AXValue.h)
AX_VALUE_TYPE_CG_POINT = 1
AX_VALUE_TYPE_CG_SIZE = 2
AX_VALUE_TYPE_AX_ERROR = 5


def describe_ax_error(error_code: int | None) -> str:
    """Human-readable name for an AX error code, e.g. -25211 -> 'api_disabled'."""
    if error_code is None:
        return "success"
    return AX_ERROR_NAMES.get(error_code, f"unknown_ax_error({error_code})")


# ---------------------------------------------------------------- attribute and action names


class Attr:
    """AX attribute names used by this surface."""

    ROLE = "AXRole"
    SUBROLE = "AXSubrole"
    TITLE = "AXTitle"
    DESCRIPTION = "AXDescription"
    LABEL = "AXLabel"
    HELP = "AXHelp"
    VALUE = "AXValue"
    PLACEHOLDER = "AXPlaceholderValue"
    TITLE_UI_ELEMENT = "AXTitleUIElement"
    POSITION = "AXPosition"
    SIZE = "AXSize"
    ENABLED = "AXEnabled"
    FOCUSED = "AXFocused"
    CHILDREN = "AXChildren"
    WINDOWS = "AXWindows"
    FOCUSED_WINDOW = "AXFocusedWindow"
    MAIN_WINDOW = "AXMainWindow"


class Action:
    """AX action names used by this surface."""

    PRESS = "AXPress"
    CANCEL = "AXCancel"
    RAISE = "AXRaise"
    SHOW_MENU = "AXShowMenu"


# ---------------------------------------------------------------- typed results and values


@dataclass(frozen=True)
class AxPoint:
    x: float
    y: float


@dataclass(frozen=True)
class AxSize:
    width: float
    height: float


@dataclass(frozen=True)
class AxResult(Generic[ValueType]):
    """Either a value (error_code is None) or an AX error code."""

    value: ValueType | None = None
    error_code: int | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None

    @property
    def error_name(self) -> str:
        return describe_ax_error(self.error_code)

    @classmethod
    def success(cls, value: ValueType | None = None) -> AxResult[ValueType]:
        return cls(value=value, error_code=None)

    @classmethod
    def failure(cls, error_code: int) -> AxResult[ValueType]:
        return cls(value=None, error_code=error_code)


class AxBackend(Protocol):
    """The AX operations the desktop surface needs. Real: `PyObjcAxBackend`. Tests: a fake."""

    def is_process_trusted(self) -> bool: ...

    def application_element(self, pid: int) -> AxResult[AxElement]: ...

    def attribute(self, element: AxElement, name: str) -> AxResult[Any]: ...

    def attributes(self, element: AxElement, names: Sequence[str]) -> AxResult[dict[str, Any]]:
        """Fetch several attributes in one round trip. Missing attributes are absent from the dict."""
        ...

    def attribute_names(self, element: AxElement) -> AxResult[list[str]]: ...

    def action_names(self, element: AxElement) -> AxResult[list[str]]: ...

    def is_settable(self, element: AxElement, name: str) -> AxResult[bool]: ...

    def set_attribute(self, element: AxElement, name: str, value: Any) -> AxResult[None]: ...

    def perform_action(self, element: AxElement, action: str) -> AxResult[None]: ...


# ---------------------------------------------------------------- real backend


def _load_application_services() -> ModuleType | None:
    """Import pyobjc's ApplicationServices lazily so non-macOS imports of this module still work."""
    try:
        return importlib.import_module("ApplicationServices")
    except ImportError as import_error:
        log_failure(
            logger,
            "_load_application_services",
            f"cannot import ApplicationServices: {import_error}",
        )
        return None


def _is_ax_value(raw_value: Any) -> bool:
    return type(raw_value).__name__ == "AXValueRef"


def _is_sequence(raw_value: Any) -> bool:
    """Python lists/tuples and bridged NSArrays (which expose objectAtIndex_)."""
    return isinstance(raw_value, list | tuple) or hasattr(raw_value, "objectAtIndex_")


class PyObjcAxBackend:
    """AxBackend over pyobjc's ApplicationServices bindings.

    `ax_module` is injectable so the conversion and error handling can be unit tested with a stub.
    """

    def __init__(
        self, ax_module: ModuleType | None = None, messaging_timeout_s: float = 1.0
    ) -> None:
        self._ax_module = ax_module
        self._module_loaded = ax_module is not None
        self._messaging_timeout_s = messaging_timeout_s

    def _ax(self) -> ModuleType | None:
        if not self._module_loaded:
            self._ax_module = _load_application_services()
            self._module_loaded = True
        return self._ax_module

    def _fail(self, function_name: str, error_code: int, **inputs: Any) -> AxResult[Any]:
        if error_code not in EXPECTED_ABSENCE_CODES:
            log_failure(
                logger, function_name, f"AX error {describe_ax_error(error_code)}", **inputs
            )
        return AxResult.failure(error_code)

    # -------------------------------------------------------- value conversion

    def to_python(self, raw_value: Any) -> Any:
        """Convert AXValueRefs to AxPoint/AxSize, arrays to lists and bridged strings to str.

        AX error values (from multi-attribute fetches) become None. Elements stay opaque.
        """
        if raw_value is None:
            return None
        if _is_ax_value(raw_value):
            return self._convert_ax_value(raw_value)
        if isinstance(raw_value, str):
            return str(raw_value)
        if isinstance(raw_value, bool | int | float):
            return raw_value
        if _is_sequence(raw_value):
            return [self.to_python(item) for item in raw_value]
        return raw_value

    def _convert_ax_value(self, ax_value: Any) -> Any:
        ax = self._ax()
        if ax is None:
            return None
        value_type = ax.AXValueGetType(ax_value)
        if value_type == AX_VALUE_TYPE_CG_POINT:
            converted, point = ax.AXValueGetValue(ax_value, value_type, None)
            return AxPoint(float(point.x), float(point.y)) if converted else None
        if value_type == AX_VALUE_TYPE_CG_SIZE:
            converted, size = ax.AXValueGetValue(ax_value, value_type, None)
            return AxSize(float(size.width), float(size.height)) if converted else None
        return None

    # -------------------------------------------------------- protocol

    def is_process_trusted(self) -> bool:
        ax = self._ax()
        if ax is None:
            return False
        return bool(ax.AXIsProcessTrusted())

    def application_element(self, pid: int) -> AxResult[AxElement]:
        ax = self._ax()
        if ax is None:
            return self._fail("application_element", BACKEND_UNAVAILABLE, pid=pid)
        app_element = ax.AXUIElementCreateApplication(pid)
        if app_element is None:
            return self._fail("application_element", AX_ERROR_FAILURE, pid=pid)
        ax.AXUIElementSetMessagingTimeout(app_element, self._messaging_timeout_s)
        return AxResult.success(app_element)

    def attribute(self, element: AxElement, name: str) -> AxResult[Any]:
        ax = self._ax()
        if ax is None:
            return self._fail("attribute", BACKEND_UNAVAILABLE, name=name)
        error_code, raw_value = ax.AXUIElementCopyAttributeValue(element, name, None)
        if error_code != AX_SUCCESS:
            return self._fail("attribute", error_code, name=name)
        return AxResult.success(self.to_python(raw_value))

    def attributes(self, element: AxElement, names: Sequence[str]) -> AxResult[dict[str, Any]]:
        ax = self._ax()
        if ax is None:
            return self._fail("attributes", BACKEND_UNAVAILABLE, names=list(names))
        error_code, raw_values = ax.AXUIElementCopyMultipleAttributeValues(
            element, list(names), 0, None
        )
        if error_code != AX_SUCCESS:
            return self._fail("attributes", error_code, names=list(names))
        values_by_name: dict[str, Any] = {}
        for name, raw_value in zip(names, raw_values or [], strict=False):
            converted = self.to_python(raw_value)
            if converted is not None:
                values_by_name[name] = converted
        return AxResult.success(values_by_name)

    def attribute_names(self, element: AxElement) -> AxResult[list[str]]:
        ax = self._ax()
        if ax is None:
            return self._fail("attribute_names", BACKEND_UNAVAILABLE)
        error_code, names = ax.AXUIElementCopyAttributeNames(element, None)
        if error_code != AX_SUCCESS:
            return self._fail("attribute_names", error_code)
        return AxResult.success([str(name) for name in names or []])

    def action_names(self, element: AxElement) -> AxResult[list[str]]:
        ax = self._ax()
        if ax is None:
            return self._fail("action_names", BACKEND_UNAVAILABLE)
        error_code, names = ax.AXUIElementCopyActionNames(element, None)
        if error_code != AX_SUCCESS:
            return self._fail("action_names", error_code)
        return AxResult.success([str(name) for name in names or []])

    def is_settable(self, element: AxElement, name: str) -> AxResult[bool]:
        ax = self._ax()
        if ax is None:
            return self._fail("is_settable", BACKEND_UNAVAILABLE, name=name)
        error_code, settable = ax.AXUIElementIsAttributeSettable(element, name, None)
        if error_code != AX_SUCCESS:
            return self._fail("is_settable", error_code, name=name)
        return AxResult.success(bool(settable))

    def set_attribute(self, element: AxElement, name: str, value: Any) -> AxResult[None]:
        ax = self._ax()
        if ax is None:
            return self._fail("set_attribute", BACKEND_UNAVAILABLE, name=name)
        error_code = ax.AXUIElementSetAttributeValue(element, name, value)
        if error_code != AX_SUCCESS:
            return self._fail("set_attribute", error_code, name=name)
        return AxResult.success(None)

    def perform_action(self, element: AxElement, action: str) -> AxResult[None]:
        ax = self._ax()
        if ax is None:
            return self._fail("perform_action", BACKEND_UNAVAILABLE, action=action)
        error_code = ax.AXUIElementPerformAction(element, action)
        if error_code != AX_SUCCESS:
            return self._fail("perform_action", error_code, action=action)
        return AxResult.success(None)


def default_ax_backend() -> PyObjcAxBackend:
    """The real backend for the current process."""
    return PyObjcAxBackend()
