"""HTTP integration tests: sign on, frames, member outcomes, open-share flow, tenant differences."""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from target_app.app import create_app
from target_app.config import AppConfig

SignOn = Callable[..., TestClient]

LOGIN_FORM = {"USERID": "teller1", "PASSWD": "demo-only-password"}


def _no_redirect_get(client: TestClient, path: str) -> tuple[int, str]:
    response = client.get(path, follow_redirects=False)
    return response.status_code, response.headers.get("location", "")


def _share_headers(html: str) -> list[str]:
    header_row = re.search(r'<tr bgcolor="#DDDDDD">(.*?)</tr>', html)
    assert header_row is not None
    return re.findall(r"<b>([^<]+)</b>", header_row.group(1))


# --- sign on / sign off / auth -------------------------------------------------------------------


def test_login_page_is_legacy_markup(client: TestClient) -> None:
    html = client.get("/t/lakeside/login").text
    assert "Lakeside Community CU" in html
    assert 'value="Sign On"' in html and "<label>" in html
    assert "User ID" in html and "Password" in html
    assert " id=" not in html and "data-testid" not in html


def test_login_success_redirects_to_frameset_and_sets_cookie(client: TestClient) -> None:
    response = client.post("/t/lakeside/login", data=LOGIN_FORM, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/t/lakeside/main"
    assert "CORESESSID=" in response.headers["set-cookie"]
    assert "Path=/t/lakeside" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "form",
    [
        {"USERID": "teller1", "PASSWD": "wrong"},
        {"USERID": "teller2", "PASSWD": "demo-only-password"},
        {"USERID": "", "PASSWD": ""},
        {},
    ],
)
def test_login_failure_rerenders_with_error(client: TestClient, form: dict[str, str]) -> None:
    response = client.post("/t/lakeside/login", data=form, follow_redirects=False)
    assert response.status_code == 401
    assert "Invalid User ID or Password." in response.text
    assert _no_redirect_get(client, "/t/lakeside/inquiry")[0] == 303


def test_login_uses_password_from_env_config() -> None:
    config = AppConfig.from_env({"HANDS_DEMO_PASSWORD": "rotated-demo"})
    with TestClient(create_app(config)) as custom_client:
        rejected = custom_client.post("/t/lakeside/login", data=LOGIN_FORM, follow_redirects=False)
        accepted = custom_client.post(
            "/t/lakeside/login",
            data={"USERID": "teller1", "PASSWD": "rotated-demo"},
            follow_redirects=False,
        )
    assert rejected.status_code == 401
    assert accepted.status_code == 303


@pytest.mark.parametrize(
    "path",
    [
        "/t/lakeside/main",
        "/t/lakeside/top",
        "/t/lakeside/nav",
        "/t/lakeside/inquiry",
        "/t/lakeside/member/10001",
        "/t/lakeside/member/10001/open-share",
        "/t/lakeside/reports",
    ],
)
def test_unauthenticated_requests_redirect_to_login(client: TestClient, path: str) -> None:
    assert _no_redirect_get(client, path) == (303, "/t/lakeside/login")


def test_unauthenticated_post_redirects_to_login(client: TestClient) -> None:
    response = client.post("/t/lakeside/review", data={"MBR_NO": "10001"}, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/t/lakeside/login")


def test_session_does_not_cross_tenants(sign_on: SignOn) -> None:
    client = sign_on("lakeside")
    assert _no_redirect_get(client, "/t/prairie/inquiry") == (303, "/t/prairie/login")


def test_sign_off_ends_session(sign_on: SignOn) -> None:
    client = sign_on()
    assert _no_redirect_get(client, "/t/lakeside/logout") == (303, "/t/lakeside/login")
    assert _no_redirect_get(client, "/t/lakeside/inquiry") == (303, "/t/lakeside/login")


@pytest.mark.parametrize(
    ("path", "location"),
    [("/", "/t/lakeside/login"), ("/t/prairie", "/t/prairie/login")],
)
def test_root_paths_redirect_to_login(client: TestClient, path: str, location: str) -> None:
    assert _no_redirect_get(client, path) == (303, location)


def test_unknown_tenant_is_404(client: TestClient) -> None:
    assert client.get("/t/nowhere/login").status_code == 404


# --- frameset shell ------------------------------------------------------------------------------


def test_main_is_a_frameset_with_named_frames(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/main").text
    assert "<frameset" in html
    for frame_name, source in (("top", "/top"), ("nav", "/nav"), ("content", "/inquiry")):
        assert f'<frame name="{frame_name}" src="/t/lakeside{source}"' in html


def test_top_frame_shows_brand_user_and_sign_off(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/top").text
    assert "Lakeside Community CU" in html
    assert "Signed on as teller1" in html
    assert "Sign Off" in html and 'target="_top"' in html


def test_nav_frame_links_target_content(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/nav").text
    for link_text in ("Member Inquiry", "Open Share Account", "Reports"):
        assert f">{link_text}</a>" in html
    assert html.count('target="content"') == 3


def test_reports_page(sign_on: SignOn) -> None:
    assert "No reports are available" in sign_on().get("/t/lakeside/reports").text


# --- member inquiry outcomes ---------------------------------------------------------------------


def test_inquiry_page_has_adjacent_td_label(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/inquiry").text
    assert re.search(r"<td[^>]*><font[^>]*>Member Number</font></td><td><input", html)
    assert 'value="Search"' in html and "<label" not in html


def test_inquiry_submit_redirects_to_member(sign_on: SignOn) -> None:
    response = sign_on().post(
        "/t/lakeside/inquiry", data={"MBR_NO": " 10001 "}, follow_redirects=False
    )
    assert (response.status_code, response.headers["location"]) == (303, "/t/lakeside/member/10001")


@pytest.mark.parametrize("raw_value", ["abc", "", "10 01", "12a"])
def test_inquiry_non_numeric_stays_on_inquiry(sign_on: SignOn, raw_value: str) -> None:
    response = sign_on().post("/t/lakeside/inquiry", data={"MBR_NO": raw_value})
    assert response.status_code == 200
    assert "Member number must be numeric." in response.text
    assert "Member Inquiry" in response.text


def test_member_path_non_numeric_shows_validation(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/member/abc").text
    assert "Member number must be numeric." in html


def test_member_10001_detail(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/member/10001").text
    assert "Avery Quinn" in html and "Active" in html and "Shares" in html
    for amount in ("1,250.00", "310.45", "85.00"):
        assert amount in html
    assert "Regular Savings" in html and "Checking" in html and "Holiday Club" in html
    assert 'value="Open Share Account"' in html and "onclick=" in html


def test_member_10002_detail(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/member/10002").text
    assert "Jordan Lee" in html and "9,870.12" in html and "0.00" in html


def test_member_restricted(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/member/40300").text
    assert "ACCESS DENIED: Member record is restricted (code 403-R)" in html
    assert "Shares" not in html


def test_member_not_found_is_red(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/member/55555").text
    assert (
        '<font face="Arial" size="2" color="#FF0000">No member found for number 55555.</font>'
        in html
    )


# --- open share flow -----------------------------------------------------------------------------

SHARE_FORM = {"MBR_NO": "10001", "SHR_TYPE": "savings", "INIT_DEP": "250", "NICK": "Rainy Day"}


def test_open_share_form_fields(sign_on: SignOn) -> None:
    html = sign_on().get("/t/lakeside/member/10001/open-share").text
    for label in ("Share Type", "Initial Deposit", "Nickname"):
        assert re.search(rf"<td[^>]*><font[^>]*>{label}</font></td><td>", html)
    for option in ("Regular Savings", "Money Market", "Share Certificate"):
        assert f">{option}</option>" in html
    assert 'value="Continue"' in html and " id=" not in html


@pytest.mark.parametrize(
    ("member_number", "expected"),
    [
        ("40300", "ACCESS DENIED"),
        ("55555", "No member found for number 55555."),
        ("abc", "Member number must be numeric."),
    ],
)
def test_open_share_for_unusable_member(sign_on: SignOn, member_number: str, expected: str) -> None:
    html = sign_on().get(f"/t/lakeside/member/{member_number}/open-share").text
    assert expected in html and 'value="Continue"' not in html


def test_open_share_happy_path_to_confirmation(sign_on: SignOn) -> None:
    client = sign_on()
    review = client.post("/t/lakeside/review", data=SHARE_FORM)
    assert "Confirm New Share" in review.text
    assert 'value="Submit"' in review.text and 'value="Cancel"' in review.text
    assert "250.00" in review.text and "Rainy Day" in review.text
    hidden_fields = dict(re.findall(r'type="hidden" name="(\w+)" value="([^"]*)"', review.text))
    assert hidden_fields == {
        "MBR_NO": "10001",
        "SHR_TYPE": "savings",
        "INIT_DEP": "250.00",
        "NICK": "Rainy Day",
    }
    confirmation = client.post("/t/lakeside/submit", data=hidden_fields)
    assert confirmation.status_code == 200
    assert "Share 0007 opened for member 10001." in confirmation.text


@pytest.mark.parametrize("deposit", ["", "0", "-10", "ten", "0.001"])
def test_review_rejects_bad_deposit(sign_on: SignOn, deposit: str) -> None:
    html = sign_on().post("/t/lakeside/review", data={**SHARE_FORM, "INIT_DEP": deposit}).text
    assert "Initial deposit must be a positive amount." in html
    assert "Confirm New Share" not in html and 'value="Continue"' in html
    assert f'name="INIT_DEP" size="14" maxlength="15" value="{deposit}"' in html


def test_review_rejects_bad_share_type(sign_on: SignOn) -> None:
    html = sign_on().post("/t/lakeside/review", data={**SHARE_FORM, "SHR_TYPE": "checking"}).text
    assert "Select a valid share type." in html


def test_submit_revalidates_tampered_deposit(sign_on: SignOn) -> None:
    html = sign_on().post("/t/lakeside/submit", data={**SHARE_FORM, "INIT_DEP": "-1"}).text
    assert "Initial deposit must be a positive amount." in html
    assert "opened for member" not in html


@pytest.mark.parametrize(
    ("member_number", "expected"),
    [("40300", "ACCESS DENIED"), ("abc", "Member number must be numeric.")],
)
def test_submit_for_unusable_member(sign_on: SignOn, member_number: str, expected: str) -> None:
    html = sign_on().post("/t/lakeside/submit", data={**SHARE_FORM, "MBR_NO": member_number}).text
    assert expected in html and "opened for member" not in html


# --- tenant differences --------------------------------------------------------------------------


def test_prairie_labels_and_column_order(sign_on: SignOn) -> None:
    client = sign_on("prairie")
    inquiry = client.get("/t/prairie/inquiry").text
    assert "Account Number" in inquiry and 'value="Find"' in inquiry
    assert "Member Number" not in inquiry
    member = client.get("/t/prairie/member/10001").text
    assert "Prairie Federal CU" in client.get("/t/prairie/top").text
    headers = _share_headers(member)
    assert headers == ["Share ID", "Balance", "Description", "Available"]
    assert "Share Savings" in member and "Regular Savings" not in member
    open_share = client.get("/t/prairie/member/10001/open-share").text
    assert ">Share Savings</option>" in open_share


def test_lakeside_column_order(sign_on: SignOn) -> None:
    member = sign_on().get("/t/lakeside/member/10001").text
    headers = _share_headers(member)
    assert headers == ["Share ID", "Description", "Balance", "Available"]


# --- health and identity verify ------------------------------------------------------------------


def test_health_endpoint(client: TestClient) -> None:
    body = client.get("/t/prairie/_health").json()
    assert body == {
        "status": "ok",
        "tenant": "prairie",
        "brand": "Prairie Federal CU",
        "vendor": "Northwind Core Systems",
        "product": "CoreOne",
        "version": "7.4",
    }


def test_health_unknown_tenant(client: TestClient) -> None:
    assert client.get("/t/nowhere/_health").status_code == 404


@pytest.mark.parametrize("answer", ["", "Lincoln Elementary", "SUPERVISOR-OVERRIDE"])
def test_identity_verify_rejects_answers(sign_on: SignOn, answer: str) -> None:
    body = sign_on().post("/t/lakeside/identity/verify", data={"SEC_ANS": answer}).json()
    assert body == {
        "verified": False,
        "message": "Answer not recognized. Supervisor override required.",
    }


def test_identity_verify_accepts_supervisor_override(sign_on: SignOn) -> None:
    body = (
        sign_on()
        .post("/t/lakeside/identity/verify", data={"SEC_ANS": "supervisor-override"})
        .json()
    )
    assert body["verified"] is True


def test_identity_verify_requires_session(client: TestClient) -> None:
    response = client.post(
        "/t/lakeside/identity/verify", data={"SEC_ANS": "x"}, follow_redirects=False
    )
    assert response.status_code == 303
