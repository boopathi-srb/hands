"""Tenant configuration: two institutions on the same vendor product, differing only by data."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

VENDOR_NAME = "Northwind Core Systems"
PRODUCT_NAME = "CoreOne"
PRODUCT_VERSION = "7.4"


class ShareColumn(StrEnum):
    SHARE_ID = "Share ID"
    DESCRIPTION = "Description"
    BALANCE = "Balance"
    AVAILABLE = "Available"


class TenantConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    brand: str
    member_number_label: str
    search_button_label: str
    savings_product_name: str
    share_columns: tuple[ShareColumn, ...]


LAKESIDE = TenantConfig(
    slug="lakeside",
    brand="Lakeside Community CU",
    member_number_label="Member Number",
    search_button_label="Search",
    savings_product_name="Regular Savings",
    share_columns=(
        ShareColumn.SHARE_ID,
        ShareColumn.DESCRIPTION,
        ShareColumn.BALANCE,
        ShareColumn.AVAILABLE,
    ),
)

PRAIRIE = TenantConfig(
    slug="prairie",
    brand="Prairie Federal CU",
    member_number_label="Account Number",
    search_button_label="Find",
    savings_product_name="Share Savings",
    share_columns=(
        ShareColumn.SHARE_ID,
        ShareColumn.BALANCE,
        ShareColumn.DESCRIPTION,
        ShareColumn.AVAILABLE,
    ),
)

TENANTS: dict[str, TenantConfig] = {tenant.slug: tenant for tenant in (LAKESIDE, PRAIRIE)}


def get_tenant(slug: str | None) -> TenantConfig | None:
    """Return the tenant for a URL slug, or None when the slug is unknown or missing."""
    if not slug:
        return None
    return TENANTS.get(slug)


def tenant_slugs() -> list[str]:
    """All configured tenant slugs, in declaration order."""
    return list(TENANTS)
