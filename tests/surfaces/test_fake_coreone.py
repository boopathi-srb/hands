"""coreone_fake: the CoreOne Member Services flow from PLAN.md, end to end without a browser."""

from __future__ import annotations

import pytest
from surface_test_helpers import act_on, find_node, texts_of

from hands.core.actions import ClickAction, OpenAction, PressAction, SelectAction, TypeAction
from hands.core.observation import Observation, Rect
from hands.surfaces.fake import (
    CONTENT_CONTAINER,
    NAV_CONTAINER,
    TOP_CONTAINER,
    FakeSurface,
    coreone_fake,
)

PASSWORD = "unit-test-password"
BASE = "http://coreone.test"


async def signed_on(tenant: str = "lakeside") -> FakeSurface:
    surface = coreone_fake(tenant, password=PASSWORD)
    await surface.act(None, OpenAction(entry_point=f"{BASE}/t/{tenant}/login"))
    await act_on(surface, TypeAction(text="teller1"), "textbox", label="User ID")
    await act_on(surface, TypeAction(text=PASSWORD), "textbox", label="Password")
    await act_on(surface, ClickAction(), "button", name="Sign On")
    return surface


async def inquire(surface: FakeSurface, member_number: str, *, label: str = "Member Number",
                  button: str = "Search") -> Observation:
    await act_on(surface, ClickAction(), "link", name="Member Inquiry")
    await act_on(surface, TypeAction(text=member_number), "textbox", label=label)
    await act_on(surface, ClickAction(), "button", name=button)
    return await surface.observe()


def column_texts(observation: Observation, table_path: str, row: int) -> list[str]:
    prefix = f"{table_path}/row[{row}]/"
    return [node.text for node in observation.nodes
            if node.structural_path.startswith(prefix) and node.structural_path.count("/") == prefix.count("/")]


def inside(bounds: Rect | None, frame: Rect) -> bool:
    return bounds is not None and frame.x <= bounds.x and bounds.x + bounds.width <= frame.x + frame.width + 1


# ---------------------------------------------------------------- sign on


async def test_starts_blank_and_opens_login() -> None:
    surface = coreone_fake(password=PASSWORD)
    blank = await surface.observe()
    assert blank.location.value == "about:blank" and blank.nodes == []

    assert (await surface.act(None, OpenAction(entry_point=f"{BASE}/t/lakeside/login"))).ok
    login = await surface.observe()
    assert login.location.value == f"{BASE}/t/lakeside/login"
    assert find_node(login, "textbox", label="User ID").structural_path == "table[1]/row[1]/cell[2]/textbox[1]"
    assert "Lakeside Community CU" in texts_of(login)


async def test_sign_on_reaches_the_frameset() -> None:
    surface = await signed_on()
    main = await surface.observe()

    assert surface.current_screen == "main"
    assert main.location.value == f"{BASE}/t/lakeside/main"
    assert find_node(main, "link", name="Sign Off").container_path == TOP_CONTAINER
    assert find_node(main, "link", name="Member Inquiry").container_path == NAV_CONTAINER
    assert find_node(main, "text", name="Select a function from the menu.").container_path == CONTENT_CONTAINER


async def test_wrong_password_shows_error_and_masks_input() -> None:
    surface = coreone_fake(password=PASSWORD)
    await surface.act(None, OpenAction(entry_point=f"{BASE}/t/lakeside/login"))
    await act_on(surface, TypeAction(text="teller1"), "textbox", label="User ID")
    await act_on(surface, TypeAction(text="wrong"), "textbox", label="Password")
    login = await surface.observe()
    assert find_node(login, "textbox", label="Password").value == "•" * 5

    await act_on(surface, PressAction(key="Enter"), "textbox", label="Password")
    assert surface.current_screen == "login_failed"
    assert "Invalid User ID or Password." in texts_of(await surface.observe())


async def test_password_defaults_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANDS_DEMO_PASSWORD", "from-env")
    surface = coreone_fake()
    await surface.act(None, OpenAction(entry_point=f"{BASE}/t/lakeside/login"))
    await act_on(surface, TypeAction(text="teller1"), "textbox", label="User ID")
    await act_on(surface, TypeAction(text="from-env"), "textbox", label="Password")
    await act_on(surface, ClickAction(), "button", name="Sign On")
    assert surface.current_screen == "main"


def test_unknown_tenant_raises() -> None:
    with pytest.raises(ValueError, match="unknown CoreOne tenant"):
        coreone_fake("nowhere")


# ---------------------------------------------------------------- member inquiry


async def test_member_detail_with_shares_table() -> None:
    surface = await signed_on()
    detail = await inquire(surface, "10001")

    assert surface.current_screen == "member_10001"
    assert detail.location.value == f"{BASE}/t/lakeside/main"  # frameset URL does not change
    assert column_texts(detail, "table[1]", 2) == ["Name", "Avery Quinn"]
    assert column_texts(detail, "table[2]", 1) == ["Share ID", "Description", "Balance", "Available"]
    assert column_texts(detail, "table[2]", 2) == ["0001", "Regular Savings", "1,250.00", "1,250.00"]
    assert find_node(detail, "cell", name="310.45", text="310.45").container_path == CONTENT_CONTAINER
    assert find_node(detail, "columnheader", name="Balance").structural_path == "table[2]/row[1]/columnheader[3]"


async def test_second_member() -> None:
    surface = await signed_on()
    detail = await inquire(surface, "10002")
    assert column_texts(detail, "table[1]", 2) == ["Name", "Jordan Lee"]
    assert column_texts(detail, "table[2]", 3) == ["0002", "Checking", "0.00", "0.00"]


async def test_unknown_member_is_not_found() -> None:
    surface = await signed_on()
    result = await inquire(surface, "99999")
    assert surface.current_screen == "member_not_found"
    assert "No member found for number 99999." in texts_of(result)


async def test_restricted_member() -> None:
    surface = await signed_on()
    result = await inquire(surface, "40300")
    assert "ACCESS DENIED: Member record is restricted (code 403-R)" in texts_of(result)


@pytest.mark.parametrize("typed", ["abc", "", "12a"])
async def test_non_numeric_input_stays_on_inquiry(typed: str) -> None:
    surface = await signed_on()
    result = await inquire(surface, typed)
    assert surface.current_screen == "inquiry_invalid"
    assert "Member number must be numeric." in texts_of(result)
    assert find_node(result, "textbox", label="Member Number").value == typed


async def test_enter_in_member_number_searches() -> None:
    surface = await signed_on()
    await act_on(surface, ClickAction(), "link", name="Member Inquiry")
    await act_on(surface, TypeAction(text="10001"), "textbox", label="Member Number")
    await act_on(surface, PressAction(key="Enter"), "textbox", label="Member Number")
    assert surface.current_screen == "member_10001"


async def test_prairie_tenant_variant() -> None:
    surface = await signed_on("prairie")
    detail = await inquire(surface, "10001", label="Account Number", button="Find")

    assert column_texts(detail, "table[2]", 1) == ["Share ID", "Balance", "Description", "Available"]
    assert column_texts(detail, "table[2]", 2) == ["0001", "1,250.00", "Share Savings", "1,250.00"]
    assert detail.location.value == f"{BASE}/t/prairie/main"


async def test_layout_is_page_level_inside_frames() -> None:
    surface = await signed_on()
    detail = await inquire(surface, "10001")
    content_frame = Rect(x=180, y=60, width=1100, height=740)
    nav_frame = Rect(x=0, y=60, width=180, height=740)

    assert all(inside(node.bounds, content_frame) for node in detail.nodes if node.container_path == CONTENT_CONTAINER)
    assert all(inside(node.bounds, nav_frame) for node in detail.nodes if node.container_path == NAV_CONTAINER)


# ---------------------------------------------------------------- open share


async def test_open_share_review_and_submit() -> None:
    surface = await signed_on()
    await inquire(surface, "10001")
    await act_on(surface, ClickAction(), "button", name="Open Share")
    assert (await act_on(surface, SelectAction(option="Money Market"), "combobox", label="Share Type")).ok
    await act_on(surface, TypeAction(text="500.00"), "textbox", label="Initial Deposit")
    await act_on(surface, TypeAction(text="Rainy Day"), "textbox", label="Nickname")
    await act_on(surface, ClickAction(), "button", name="Continue")

    review = await surface.observe()
    assert "Confirm New Share" in texts_of(review)
    assert column_texts(review, "table[1]", 2) == ["Share Type", "Money Market"]
    await act_on(surface, ClickAction(), "button", name="Submit")
    assert "Share 0007 opened for member 10001." in texts_of(await surface.observe())


async def test_open_share_rejects_unknown_type() -> None:
    surface = await signed_on()
    await inquire(surface, "10002")
    await act_on(surface, ClickAction(), "button", name="Open Share")
    result = await act_on(surface, SelectAction(option="Crypto"), "combobox", label="Share Type")
    assert not result.ok and "Regular Savings" in (result.error or "")


# ---------------------------------------------------------------- faults


async def test_session_expired_recovers_through_sign_on() -> None:
    surface = await signed_on()
    surface.inject_next("session_expired")
    expired = await surface.observe()
    assert "Your session has expired. Please sign on again." in texts_of(expired)

    await act_on(surface, ClickAction(), "link", name="Sign On")
    assert surface.current_screen == "login"


async def test_maintenance_notice_overlays_current_page() -> None:
    surface = await signed_on()
    surface.inject_next("maintenance_notice", trigger="act")
    await act_on(surface, ClickAction(), "link", name="Member Inquiry")
    notice = await surface.observe()

    assert [dialog.title for dialog in notice.dialogs] == ["System Notice"]
    assert find_node(notice, "textbox", label="Member Number")  # inquiry page is underneath
    assert find_node(notice, "cell", name="System Notice").structural_path == "table[51]/row[1]/cell[1]"
    await act_on(surface, ClickAction(), "button", name="Acknowledge")
    assert surface.current_screen == "inquiry"


async def test_native_alert_fault() -> None:
    surface = await signed_on()
    surface.inject_next("native_alert")
    alert = await surface.observe()
    assert alert.dialogs[0].native and alert.dialogs[0].text == "Printer queue offline"
    await act_on(surface, ClickAction(), "button", name="OK")
    assert surface.current_screen == "main"


async def test_identity_check_needs_an_answer() -> None:
    surface = await signed_on()
    surface.inject_next("identity_check")
    await act_on(surface, ClickAction(), "button", name="Verify")
    assert surface.current_screen == "identity_check"

    await act_on(surface, TypeAction(text="an answer only a human knows"), "textbox", label="Answer")
    await act_on(surface, ClickAction(), "button", name="Verify")
    assert surface.current_screen == "main"


async def test_app_error_and_slow_load() -> None:
    surface = await signed_on()
    surface.delay_observations(1)
    loading = await surface.observe()
    assert "Loading..." in texts_of(loading)
    assert find_node(loading, "link", name="Sign Off")  # frames around the content still render

    surface.inject_next("app_error")
    assert "Internal Error. Reference ID ERR-5521." in texts_of(await surface.observe())
