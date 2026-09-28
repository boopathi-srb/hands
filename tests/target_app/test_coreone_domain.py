"""Unit tests for pure domain modules: tenants, members, forms, open share, sessions, config."""

from __future__ import annotations

from decimal import Decimal

import pytest

from target_app.__main__ import parse_args
from target_app.config import DEFAULT_DEMO_PASSWORD, AppConfig
from target_app.forms import (
    DEPOSIT_NOT_POSITIVE,
    clean_nickname,
    parse_deposit,
    parse_form_body,
    parse_member_number,
)
from target_app.members import (
    MEMBERS,
    LookupStatus,
    Product,
    find_member,
    format_amount,
    openable_product_options,
    parse_openable_product,
    product_display_name,
    share_table_rows,
)
from target_app.open_share import (
    SHARE_TYPE_INVALID,
    DraftRejected,
    ShareDraft,
    validate_share_draft,
)
from target_app.sessions import SessionStore, answer_matches, credentials_match
from target_app.tenants import LAKESIDE, PRAIRIE, ShareColumn, get_tenant, tenant_slugs

# --- tenants -------------------------------------------------------------------------------------


def test_get_tenant_known_slugs() -> None:
    assert get_tenant("lakeside") is LAKESIDE
    assert get_tenant("prairie") is PRAIRIE


@pytest.mark.parametrize("slug", [None, "", "LAKESIDE", "unknown"])
def test_get_tenant_unknown_or_missing(slug: str | None) -> None:
    assert get_tenant(slug) is None


def test_tenant_slugs_lists_both_tenants() -> None:
    assert tenant_slugs() == ["lakeside", "prairie"]


def test_tenant_differences_match_plan() -> None:
    assert (LAKESIDE.brand, PRAIRIE.brand) == ("Lakeside Community CU", "Prairie Federal CU")
    assert (LAKESIDE.member_number_label, PRAIRIE.member_number_label) == (
        "Member Number",
        "Account Number",
    )
    assert (LAKESIDE.search_button_label, PRAIRIE.search_button_label) == ("Search", "Find")
    assert (LAKESIDE.savings_product_name, PRAIRIE.savings_product_name) == (
        "Regular Savings",
        "Share Savings",
    )
    assert [column.value for column in PRAIRIE.share_columns] == [
        "Share ID",
        "Balance",
        "Description",
        "Available",
    ]


# --- members -------------------------------------------------------------------------------------


def test_find_member_found() -> None:
    lookup = find_member("10001")
    assert lookup.status is LookupStatus.FOUND
    assert lookup.member is not None and lookup.member.name == "Avery Quinn"


def test_find_member_restricted_has_no_record() -> None:
    lookup = find_member("40300")
    assert lookup.status is LookupStatus.RESTRICTED
    assert lookup.member is None


@pytest.mark.parametrize("member_number", ["", "0", "99999", "100010"])
def test_find_member_not_found(member_number: str) -> None:
    lookup = find_member(member_number)
    assert lookup.status is LookupStatus.NOT_FOUND
    assert lookup.member_number == member_number


@pytest.mark.parametrize(
    ("amount", "rendered"),
    [
        ("0", "0.00"),
        ("0.00", "0.00"),
        ("85", "85.00"),
        ("999.99", "999.99"),
        ("1000", "1,000.00"),
        ("1250.00", "1,250.00"),
        ("9870.12", "9,870.12"),
        ("1234567.8", "1,234,567.80"),
    ],
)
def test_format_amount(amount: str, rendered: str) -> None:
    assert format_amount(Decimal(amount)) == rendered


def test_product_display_name_renames_only_savings() -> None:
    assert product_display_name(Product.SAVINGS, LAKESIDE) == "Regular Savings"
    assert product_display_name(Product.SAVINGS, PRAIRIE) == "Share Savings"
    assert product_display_name(Product.CHECKING, PRAIRIE) == "Checking"


def test_openable_product_options_per_tenant() -> None:
    assert openable_product_options(LAKESIDE) == [
        ("savings", "Regular Savings"),
        ("money_market", "Money Market"),
        ("certificate", "Share Certificate"),
    ]
    assert openable_product_options(PRAIRIE)[0] == ("savings", "Share Savings")


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("savings", Product.SAVINGS),
        ("certificate", Product.CERTIFICATE),
        ("checking", None),
        ("", None),
        (None, None),
        ("SAVINGS", None),
    ],
)
def test_parse_openable_product(raw_value: str | None, expected: Product | None) -> None:
    assert parse_openable_product(raw_value) is expected


def test_share_table_rows_follow_tenant_column_order() -> None:
    member = MEMBERS["10001"]
    assert share_table_rows(member, LAKESIDE)[0] == [
        "0001",
        "Regular Savings",
        "1,250.00",
        "1,250.00",
    ]
    assert share_table_rows(member, PRAIRIE)[0] == ["0001", "1,250.00", "Share Savings", "1,250.00"]


def test_share_table_rows_for_second_member() -> None:
    rows = share_table_rows(MEMBERS["10002"], LAKESIDE)
    assert rows == [
        ["0001", "Regular Savings", "9,870.12", "9,870.12"],
        ["0009", "Checking", "0.00", "0.00"],
    ]
    assert ShareColumn.SHARE_ID in LAKESIDE.share_columns


# --- forms ---------------------------------------------------------------------------------------


def test_parse_form_body_empty() -> None:
    assert parse_form_body(b"") == {}


def test_parse_form_body_keeps_first_value_and_blanks() -> None:
    parsed = parse_form_body(b"A=1&A=2&B=&C=x+y%2Cz")
    assert parsed == {"A": "1", "B": "", "C": "x y,z"}


def test_parse_form_body_tolerates_bad_utf8() -> None:
    assert parse_form_body(b"NICK=%FF")["NICK"] == "�"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("10001", "10001"),
        ("  10002 ", "10002"),
        ("0", "0"),
        ("123456789012", "123456789012"),
        ("1234567890123", None),
        ("", None),
        ("   ", None),
        (None, None),
        ("abc", None),
        ("10-01", None),
        ("-1", None),
        ("1.5", None),
        ("١٢٣", None),
    ],
)
def test_parse_member_number(raw_value: str | None, expected: str | None) -> None:
    assert parse_member_number(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("100", Decimal("100.00")),
        (" 1,250.5 ", Decimal("1250.50")),
        ("0.01", Decimal("0.01")),
        ("1e3", Decimal("1000.00")),
        ("999999999.99", Decimal("999999999.99")),
    ],
)
def test_parse_deposit_accepts_positive_amounts(raw_value: str, expected: Decimal) -> None:
    assert parse_deposit(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    [None, "", "  ", "0", "0.00", "0.001", "-5", "abc", "NaN", "Infinity", "1e40", "1000000000"],
)
def test_parse_deposit_rejects_non_positive_or_invalid(raw_value: str | None) -> None:
    assert parse_deposit(raw_value) is None


def test_clean_nickname() -> None:
    assert clean_nickname(None) == ""
    assert clean_nickname("  Rainy Day  ") == "Rainy Day"
    assert len(clean_nickname("x" * 50)) == 30


# --- open share ----------------------------------------------------------------------------------


def test_validate_share_draft_happy_path() -> None:
    fields = {"SHR_TYPE": "money_market", "INIT_DEP": "500", "NICK": " Rainy "}
    draft = validate_share_draft(MEMBERS["10001"], fields)
    assert isinstance(draft, ShareDraft)
    assert (draft.product, draft.deposit, draft.nickname) == (
        Product.MONEY_MARKET,
        Decimal("500.00"),
        "Rainy",
    )


def test_validate_share_draft_rejects_bad_deposit() -> None:
    draft = validate_share_draft(MEMBERS["10001"], {"SHR_TYPE": "savings", "INIT_DEP": "-1"})
    assert draft == DraftRejected(error=DEPOSIT_NOT_POSITIVE)


def test_validate_share_draft_rejects_bad_share_type() -> None:
    draft = validate_share_draft(MEMBERS["10001"], {"INIT_DEP": "10"})
    assert draft == DraftRejected(error=SHARE_TYPE_INVALID)


# --- sessions ------------------------------------------------------------------------------------


def test_session_store_create_get_revoke() -> None:
    store = SessionStore()
    session = store.create("teller1", "lakeside")
    assert store.get(session.token, "lakeside") == session
    assert store.get(session.token, "prairie") is None
    assert store.revoke(session.token) is True
    assert store.get(session.token, "lakeside") is None
    assert store.revoke(session.token) is False


@pytest.mark.parametrize("token", [None, "", "not-a-token"])
def test_session_store_get_missing_token(token: str | None) -> None:
    assert SessionStore().get(token, "lakeside") is None


def test_session_store_revoke_empty_token() -> None:
    assert SessionStore().revoke(None) is False


@pytest.mark.parametrize(
    ("user_id", "password", "expected"),
    [
        ("teller1", "secret", True),
        ("teller1", "wrong", False),
        ("teller2", "secret", False),
        ("", "", False),
    ],
)
def test_credentials_match(user_id: str, password: str, expected: bool) -> None:
    assert credentials_match(user_id, password, "teller1", "secret") is expected


def test_answer_matches() -> None:
    assert answer_matches("supervisor-override", "supervisor-override") is True
    assert answer_matches("Supervisor-Override", "supervisor-override") is False
    assert answer_matches("", "supervisor-override") is False


# --- config and entry point ----------------------------------------------------------------------


def test_app_config_from_env_defaults() -> None:
    config = AppConfig.from_env({})
    assert config.teller_password == DEFAULT_DEMO_PASSWORD
    assert config.seeded_faults == ""
    assert config.default_slow_delay_ms == 4000


def test_app_config_from_env_reads_values() -> None:
    config = AppConfig.from_env(
        {"HANDS_DEMO_PASSWORD": "other-password", "COREONE_FAULTS": "slow:2"}
    )
    assert config.teller_password == "other-password"
    assert config.seeded_faults == "slow:2"


def test_app_config_from_env_blank_password_falls_back() -> None:
    assert AppConfig.from_env({"HANDS_DEMO_PASSWORD": ""}).teller_password == DEFAULT_DEMO_PASSWORD


def test_parse_args_defaults_and_override() -> None:
    assert parse_args([]).port == 8700
    arguments = parse_args(["--port", "8123", "--host", "0.0.0.0"])
    assert (arguments.port, arguments.host) == (8123, "0.0.0.0")
