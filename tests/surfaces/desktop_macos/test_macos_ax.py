"""PyObjcAxBackend against a stub ApplicationServices module (no real AX calls)."""

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from hands.surfaces.desktop_macos import ax as ax_module
from hands.surfaces.desktop_macos.ax import (
    AX_ERROR_API_DISABLED,
    AX_ERROR_ATTRIBUTE_UNSUPPORTED,
    AX_ERROR_NO_VALUE,
    AX_VALUE_TYPE_AX_ERROR,
    AX_VALUE_TYPE_CG_POINT,
    AX_VALUE_TYPE_CG_SIZE,
    BACKEND_UNAVAILABLE,
    AxPoint,
    AxResult,
    AxSize,
    PyObjcAxBackend,
    default_ax_backend,
    describe_ax_error,
)


class AXValueRef:
    """Named like pyobjc's AXValueRef so the backend recognizes it."""

    def __init__(self, value_type: int, payload: Any) -> None:
        self.value_type = value_type
        self.payload = payload


class StubApplicationServices:
    def __init__(self) -> None:
        self.attribute_results: dict[str, tuple[int, Any]] = {}
        self.multi_result: tuple[int, Any] = (0, [])
        self.names_result: tuple[int, Any] = (0, ["AXRole"])
        self.actions_result: tuple[int, Any] = (0, ["AXPress"])
        self.settable_result: tuple[int, Any] = (0, True)
        self.set_result = 0
        self.perform_result = 0
        self.trusted = True
        self.timeouts: list[float] = []
        self.calls: list[tuple[str, Any]] = []

    def AXIsProcessTrusted(self) -> bool:
        return self.trusted

    def AXUIElementCreateApplication(self, pid: int) -> Any:
        return None if pid < 0 else f"app:{pid}"

    def AXUIElementSetMessagingTimeout(self, element: Any, seconds: float) -> int:
        self.timeouts.append(seconds)
        return 0

    def AXUIElementCopyAttributeValue(self, element: Any, name: str, _out: None) -> tuple[int, Any]:
        return self.attribute_results.get(name, (AX_ERROR_NO_VALUE, None))

    def AXUIElementCopyMultipleAttributeValues(
        self, element: Any, names: list[str], options: int, _out: None
    ) -> tuple[int, Any]:
        return self.multi_result

    def AXUIElementCopyAttributeNames(self, element: Any, _out: None) -> tuple[int, Any]:
        return self.names_result

    def AXUIElementCopyActionNames(self, element: Any, _out: None) -> tuple[int, Any]:
        return self.actions_result

    def AXUIElementIsAttributeSettable(
        self, element: Any, name: str, _out: None
    ) -> tuple[int, Any]:
        return self.settable_result

    def AXUIElementSetAttributeValue(self, element: Any, name: str, value: Any) -> int:
        self.calls.append(("set", (name, value)))
        return self.set_result

    def AXUIElementPerformAction(self, element: Any, action: str) -> int:
        self.calls.append(("perform", action))
        return self.perform_result

    def AXValueGetType(self, value: AXValueRef) -> int:
        return value.value_type

    def AXValueGetValue(self, value: AXValueRef, value_type: int, _out: None) -> tuple[bool, Any]:
        return (value.payload is not None, value.payload)


@pytest.fixture
def stub() -> StubApplicationServices:
    return StubApplicationServices()


@pytest.fixture
def backend(stub: StubApplicationServices) -> PyObjcAxBackend:
    return PyObjcAxBackend(ax_module=stub, messaging_timeout_s=0.5)  # type: ignore[arg-type]


def point(x: float, y: float) -> AXValueRef:
    return AXValueRef(AX_VALUE_TYPE_CG_POINT, SimpleNamespace(x=x, y=y))


def size(width: float, height: float) -> AXValueRef:
    return AXValueRef(AX_VALUE_TYPE_CG_SIZE, SimpleNamespace(width=width, height=height))


def test_describe_ax_error() -> None:
    assert describe_ax_error(None) == "success"
    assert describe_ax_error(AX_ERROR_API_DISABLED) == "api_disabled"
    assert describe_ax_error(-1) == "backend_unavailable"
    assert describe_ax_error(12345) == "unknown_ax_error(12345)"


def test_ax_result_success_and_failure() -> None:
    success: AxResult[int] = AxResult.success(3)
    failure: AxResult[int] = AxResult.failure(AX_ERROR_NO_VALUE)
    assert success.ok and success.value == 3 and success.error_name == "success"
    assert not failure.ok and failure.value is None and failure.error_name == "no_value"
    assert AxResult.success(None).ok


def test_is_process_trusted(backend: PyObjcAxBackend, stub: StubApplicationServices) -> None:
    assert backend.is_process_trusted() is True
    stub.trusted = False
    assert backend.is_process_trusted() is False


def test_application_element_sets_messaging_timeout(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    result = backend.application_element(123)
    assert result.ok and result.value == "app:123"
    assert stub.timeouts == [0.5]
    assert backend.application_element(-5).error_name == "failure"


def test_attribute_success_converts_values(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    stub.attribute_results = {
        "AXTitle": (0, "Calc"),
        "AXPosition": (0, point(1, 2)),
        "AXSize": (0, size(3, 4)),
        "AXChildren": (0, ("el1", "el2")),
        "AXEnabled": (0, True),
        "AXOther": (0, AXValueRef(AX_VALUE_TYPE_AX_ERROR, None)),
    }
    assert backend.attribute("el", "AXTitle").value == "Calc"
    assert backend.attribute("el", "AXPosition").value == AxPoint(1.0, 2.0)
    assert backend.attribute("el", "AXSize").value == AxSize(3.0, 4.0)
    assert backend.attribute("el", "AXChildren").value == ["el1", "el2"]
    assert backend.attribute("el", "AXEnabled").value is True
    assert backend.attribute("el", "AXOther").value is None


def test_attribute_failed_point_conversion_is_none(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    stub.attribute_results = {"AXPosition": (0, AXValueRef(AX_VALUE_TYPE_CG_POINT, None))}
    assert backend.attribute("el", "AXPosition").value is None


def test_expected_absence_is_not_logged_but_real_errors_are(
    backend: PyObjcAxBackend, stub: StubApplicationServices, caplog: pytest.LogCaptureFixture
) -> None:
    stub.attribute_results = {"AXTitle": (AX_ERROR_API_DISABLED, None)}
    with caplog.at_level(logging.ERROR):
        missing = backend.attribute("el", "AXValue")
        assert caplog.records == []
        disabled = backend.attribute("el", "AXTitle")
    assert missing.error_code == AX_ERROR_NO_VALUE
    assert disabled.error_code == AX_ERROR_API_DISABLED
    assert (
        "attribute failed" in caplog.text
        and "api_disabled" in caplog.text
        and "AXTitle" in caplog.text
    )


def test_attributes_omits_missing_values(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    stub.multi_result = (0, ["AXButton", AXValueRef(AX_VALUE_TYPE_AX_ERROR, None), point(5, 6)])
    result = backend.attributes("el", ["AXRole", "AXTitle", "AXPosition"])
    assert result.value == {"AXRole": "AXButton", "AXPosition": AxPoint(5.0, 6.0)}


def test_attributes_failure_and_empty(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    stub.multi_result = (AX_ERROR_API_DISABLED, None)
    assert backend.attributes("el", ["AXRole"]).error_code == AX_ERROR_API_DISABLED
    stub.multi_result = (0, None)
    assert backend.attributes("el", []).value == {}


def test_attribute_and_action_names(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    assert backend.attribute_names("el").value == ["AXRole"]
    assert backend.action_names("el").value == ["AXPress"]
    stub.names_result = (AX_ERROR_API_DISABLED, None)
    stub.actions_result = (0, None)
    assert not backend.attribute_names("el").ok
    assert backend.action_names("el").value == []
    stub.actions_result = (AX_ERROR_API_DISABLED, None)
    assert not backend.action_names("el").ok


def test_is_settable(backend: PyObjcAxBackend, stub: StubApplicationServices) -> None:
    assert backend.is_settable("el", "AXValue").value is True
    stub.settable_result = (AX_ERROR_ATTRIBUTE_UNSUPPORTED, False)
    assert backend.is_settable("el", "AXValue").error_code == AX_ERROR_ATTRIBUTE_UNSUPPORTED


def test_set_attribute_and_perform_action(
    backend: PyObjcAxBackend, stub: StubApplicationServices
) -> None:
    assert backend.set_attribute("el", "AXValue", "x").ok
    assert backend.perform_action("el", "AXPress").ok
    assert stub.calls == [("set", ("AXValue", "x")), ("perform", "AXPress")]
    stub.set_result = AX_ERROR_API_DISABLED
    stub.perform_result = AX_ERROR_API_DISABLED
    assert not backend.set_attribute("el", "AXValue", "x").ok
    assert not backend.perform_action("el", "AXPress").ok


def test_to_python_handles_none_numbers_and_opaque_objects(backend: PyObjcAxBackend) -> None:
    opaque = object()
    assert backend.to_python(None) is None
    assert backend.to_python(2.5) == 2.5
    assert backend.to_python(opaque) is opaque
    assert backend.to_python([["a"], point(1, 1)]) == [["a"], AxPoint(1.0, 1.0)]


def test_backend_unavailable_when_module_cannot_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ax_module, "_load_application_services", lambda: None)
    backend = PyObjcAxBackend()
    assert backend.is_process_trusted() is False
    assert backend.application_element(1).error_code == BACKEND_UNAVAILABLE
    assert backend.attribute("el", "AXRole").error_code == BACKEND_UNAVAILABLE
    assert backend.attributes("el", ["AXRole"]).error_code == BACKEND_UNAVAILABLE
    assert backend.attribute_names("el").error_code == BACKEND_UNAVAILABLE
    assert backend.action_names("el").error_code == BACKEND_UNAVAILABLE
    assert backend.is_settable("el", "AXValue").error_code == BACKEND_UNAVAILABLE
    assert backend.set_attribute("el", "AXValue", 1).error_code == BACKEND_UNAVAILABLE
    assert backend.perform_action("el", "AXPress").error_code == BACKEND_UNAVAILABLE
    assert backend.to_python(point(1, 1)) is None


def test_load_application_services_handles_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_import(name: str) -> None:
        raise ImportError(f"no {name}")

    monkeypatch.setattr(ax_module.importlib, "import_module", failing_import)
    assert ax_module._load_application_services() is None


def test_default_backend_is_real_pyobjc_backend() -> None:
    assert isinstance(default_ax_backend(), PyObjcAxBackend)
