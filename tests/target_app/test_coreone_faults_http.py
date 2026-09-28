"""HTTP integration tests for fault injection: admin API, each fault's effect, env seeding."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from target_app.app import create_app
from target_app.config import AppConfig

SignOn = Callable[..., TestClient]
ArmFault = Callable[..., Any]

MEMBER_PAGE = "/t/lakeside/member/10001"
SESSION_EXPIRED_TEXT = "Your session has expired. Please sign on again."
APP_ERROR_TEXT = "Internal Error. Reference ID ERR-5521."
ALERT_SNIPPET = "onload='alert(\"Printer queue offline\")'"
SHARE_FORM = {"MBR_NO": "10001", "SHR_TYPE": "savings", "INIT_DEP": "250", "NICK": ""}


def _armed(client: TestClient) -> list[dict[str, Any]]:
    armed: list[dict[str, Any]] = client.get("/_admin/faults").json()["armed"]
    return armed


# --- admin API -----------------------------------------------------------------------------------


def test_admin_arm_list_clear(client: TestClient, arm_fault: ArmFault) -> None:
    assert _armed(client) == []
    body = arm_fault("slow", count=2, delay_ms=10)
    assert body["armed"] == [
        {"fault": "slow", "tenant": "lakeside", "remaining": 2, "delay_ms": 10}
    ]
    arm_fault("app_error", tenant="prairie")
    assert len(_armed(client)) == 2
    cleared = client.delete("/_admin/faults", params={"tenant": "prairie"}).json()
    assert cleared["removed"] == 1 and len(cleared["armed"]) == 1
    assert client.delete("/_admin/faults").json() == {"removed": 1, "armed": []}


def test_admin_tenant_defaults_to_any(client: TestClient) -> None:
    response = client.post("/_admin/faults", json={"fault": "native_alert"})
    assert response.status_code == 201
    assert response.json()["armed"][0]["tenant"] == "*"


@pytest.mark.parametrize(
    "payload",
    [
        {"fault": "explode", "count": 1, "tenant": "lakeside"},
        {"fault": "slow", "count": 0, "tenant": "lakeside"},
        {"fault": "slow", "count": 1, "tenant": "lakeside", "delay_ms": -5},
        {"count": 1, "tenant": "lakeside"},
    ],
)
def test_admin_rejects_invalid_payload(client: TestClient, payload: dict[str, Any]) -> None:
    assert client.post("/_admin/faults", json=payload).status_code == 422
    assert _armed(client) == []


def test_admin_rejects_unknown_tenant(client: TestClient) -> None:
    response = client.post("/_admin/faults", json={"fault": "slow", "count": 1, "tenant": "mars"})
    assert response.status_code == 400
    assert _armed(client) == []


# --- each fault arms, fires, disarms -------------------------------------------------------------


def test_session_expired_fires_once_and_ends_session(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("session_expired")
    html = client.get(MEMBER_PAGE).text
    assert SESSION_EXPIRED_TEXT in html
    assert '<a href="/t/lakeside/login" target="_top">' in html and "Sign On" in html
    assert _armed(client) == []
    assert client.get(MEMBER_PAGE, follow_redirects=False).status_code == 303
    sign_on()
    assert "Avery Quinn" in client.get(MEMBER_PAGE).text


def test_app_error_fires_count_times(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("app_error", count=2)
    for _ in range(2):
        response = client.get(MEMBER_PAGE)
        assert response.status_code == 500 and APP_ERROR_TEXT in response.text
    assert _armed(client) == []
    assert "Avery Quinn" in client.get(MEMBER_PAGE).text


def test_slow_delays_with_requested_and_default_delay(
    sign_on: SignOn, arm_fault: ArmFault, recorded_delays: list[int]
) -> None:
    client = sign_on()
    arm_fault("slow", delay_ms=1500)
    assert "Avery Quinn" in client.get(MEMBER_PAGE).text
    arm_fault("slow")
    client.get("/t/lakeside/inquiry")
    client.get(MEMBER_PAGE)
    assert recorded_delays == [1500, 4000]
    assert _armed(client) == []


def test_slow_actually_waits(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("slow", delay_ms=120)
    started = time.monotonic()
    assert client.get(MEMBER_PAGE).status_code == 200
    assert time.monotonic() - started >= 0.12
    assert _armed(client) == []


def test_maintenance_notice_overlay(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("maintenance_notice")
    html = client.get(MEMBER_PAGE).text
    assert "System Notice" in html and 'value="Acknowledge"' in html
    assert 'onclick="coDismiss(this)"' in html
    assert "Avery Quinn" in html
    assert "System Notice" not in client.get(MEMBER_PAGE).text


def test_native_alert_on_load(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("native_alert")
    assert ALERT_SNIPPET in client.get("/t/lakeside/inquiry").text
    assert "alert(" not in client.get("/t/lakeside/inquiry").text


def test_identity_check_overlay(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("identity_check")
    html = client.get(MEMBER_PAGE).text
    assert "Verify Member Identity" in html
    assert "Security Answer" in html and 'value="Verify"' in html
    assert "supervisor-override" not in html
    assert "Verify Member Identity" not in client.get(MEMBER_PAGE).text


@pytest.mark.parametrize(
    ("method", "path", "form"),
    [
        ("get", "/t/lakeside/inquiry", None),
        ("get", "/t/lakeside/member/10001", None),
        ("get", "/t/lakeside/member/10001/open-share", None),
        ("post", "/t/lakeside/review", SHARE_FORM),
    ],
)
def test_faults_fire_on_each_eligible_page(
    sign_on: SignOn, arm_fault: ArmFault, method: str, path: str, form: dict[str, str] | None
) -> None:
    client = sign_on()
    arm_fault("app_error")
    response = client.request(method.upper(), path, data=form)
    assert APP_ERROR_TEXT in response.text
    assert _armed(client) == []


@pytest.mark.parametrize(
    ("method", "path", "form"),
    [
        ("get", "/t/lakeside/main", None),
        ("get", "/t/lakeside/top", None),
        ("get", "/t/lakeside/nav", None),
        ("get", "/t/lakeside/reports", None),
        ("get", "/t/lakeside/login", None),
        ("post", "/t/lakeside/submit", SHARE_FORM),
    ],
)
def test_faults_do_not_fire_on_ineligible_pages(
    sign_on: SignOn, arm_fault: ArmFault, method: str, path: str, form: dict[str, str] | None
) -> None:
    client = sign_on()
    arm_fault("app_error")
    response = client.request(method.upper(), path, data=form)
    assert APP_ERROR_TEXT not in response.text
    assert len(_armed(client)) == 1


def test_fault_for_other_tenant_does_not_fire(sign_on: SignOn, arm_fault: ArmFault) -> None:
    client = sign_on()
    arm_fault("app_error", tenant="prairie")
    assert APP_ERROR_TEXT not in client.get(MEMBER_PAGE).text
    assert len(_armed(client)) == 1


def test_unauthenticated_request_does_not_consume_fault(
    client: TestClient, arm_fault: ArmFault
) -> None:
    arm_fault("app_error")
    assert client.get(MEMBER_PAGE, follow_redirects=False).status_code == 303
    assert len(_armed(client)) == 1


# --- env seeding ---------------------------------------------------------------------------------


def test_env_seeded_faults_fire(caplog: pytest.LogCaptureFixture) -> None:
    config = AppConfig.from_env({"COREONE_FAULTS": "maintenance_notice:1,native_alert:2,nope:1"})
    with TestClient(create_app(config)) as client:
        seeded = {item["fault"]: item["remaining"] for item in _armed(client)}
        assert seeded == {"maintenance_notice": 1, "native_alert": 2}
        client.post("/t/prairie/login", data={"USERID": "teller1", "PASSWD": "demo-only-password"})
        first = client.get("/t/prairie/member/10001").text
        assert "System Notice" in first and ALERT_SNIPPET in first
        second = client.get("/t/prairie/member/10001").text
        assert "System Notice" not in second and ALERT_SNIPPET in second
        assert _armed(client) == []
    assert "unknown fault 'nope'" in caplog.text


def test_env_without_faults_arms_nothing() -> None:
    with TestClient(create_app(AppConfig.from_env({}))) as client:
        assert _armed(client) == []
