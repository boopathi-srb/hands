"""Fictional member records and the lookup outcomes the inquiry screen can produce."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from target_app.tenants import ShareColumn, TenantConfig

RESTRICTED_MEMBER_NUMBER = "40300"
NEW_SHARE_ID = "0007"


class Product(StrEnum):
    SAVINGS = "savings"
    CHECKING = "checking"
    HOLIDAY_CLUB = "holiday_club"
    MONEY_MARKET = "money_market"
    CERTIFICATE = "certificate"


_FIXED_PRODUCT_NAMES: dict[Product, str] = {
    Product.CHECKING: "Checking",
    Product.HOLIDAY_CLUB: "Holiday Club",
    Product.MONEY_MARKET: "Money Market",
    Product.CERTIFICATE: "Share Certificate",
}

OPENABLE_PRODUCTS: tuple[Product, ...] = (
    Product.SAVINGS,
    Product.MONEY_MARKET,
    Product.CERTIFICATE,
)


class Share(BaseModel):
    model_config = ConfigDict(frozen=True)

    share_id: str
    product: Product
    balance: Decimal
    available: Decimal


class Member(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_number: str
    name: str
    status: str
    shares: tuple[Share, ...]


def _share(share_id: str, product: Product, balance: str, available: str) -> Share:
    return Share(
        share_id=share_id, product=product, balance=Decimal(balance), available=Decimal(available)
    )


MEMBERS: dict[str, Member] = {
    "10001": Member(
        member_number="10001",
        name="Avery Quinn",
        status="Active",
        shares=(
            _share("0001", Product.SAVINGS, "1250.00", "1250.00"),
            _share("0009", Product.CHECKING, "310.45", "310.45"),
            _share("0060", Product.HOLIDAY_CLUB, "85.00", "0.00"),
        ),
    ),
    "10002": Member(
        member_number="10002",
        name="Jordan Lee",
        status="Active",
        shares=(
            _share("0001", Product.SAVINGS, "9870.12", "9870.12"),
            _share("0009", Product.CHECKING, "0.00", "0.00"),
        ),
    ),
}


class LookupStatus(StrEnum):
    FOUND = "found"
    RESTRICTED = "restricted"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class MemberLookup:
    status: LookupStatus
    member_number: str
    member: Member | None = None


def find_member(member_number: str) -> MemberLookup:
    """Look up a (already validated, numeric) member number."""
    if member_number == RESTRICTED_MEMBER_NUMBER:
        return MemberLookup(status=LookupStatus.RESTRICTED, member_number=member_number)
    member = MEMBERS.get(member_number)
    if member is None:
        return MemberLookup(status=LookupStatus.NOT_FOUND, member_number=member_number)
    return MemberLookup(status=LookupStatus.FOUND, member_number=member_number, member=member)


def format_amount(amount: Decimal) -> str:
    """Render an amount the way the legacy core does: thousands separators, two decimals."""
    return f"{amount:,.2f}"


def product_display_name(product: Product, tenant: TenantConfig) -> str:
    """Tenant-specific display name for a product (only savings is renamed per tenant)."""
    if product is Product.SAVINGS:
        return tenant.savings_product_name
    return _FIXED_PRODUCT_NAMES[product]


def openable_product_options(tenant: TenantConfig) -> list[tuple[str, str]]:
    """(value, label) pairs for the Share Type select."""
    return [(product.value, product_display_name(product, tenant)) for product in OPENABLE_PRODUCTS]


def parse_openable_product(raw_value: str | None) -> Product | None:
    """Map a submitted Share Type value back to a product that may be opened, else None."""
    for product in OPENABLE_PRODUCTS:
        if product.value == raw_value:
            return product
    return None


def _share_cell(share: Share, column: ShareColumn, tenant: TenantConfig) -> str:
    if column is ShareColumn.SHARE_ID:
        return share.share_id
    if column is ShareColumn.DESCRIPTION:
        return product_display_name(share.product, tenant)
    if column is ShareColumn.BALANCE:
        return format_amount(share.balance)
    return format_amount(share.available)


def share_table_rows(member: Member, tenant: TenantConfig) -> list[list[str]]:
    """Share rows as display strings, in the tenant's column order."""
    return [
        [_share_cell(share, column, tenant) for column in tenant.share_columns]
        for share in member.shares
    ]
