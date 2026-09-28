"""Validation of the Open Share Account form into a typed draft."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from target_app.forms import (
    DEPOSIT_NOT_POSITIVE,
    FIELD_DEPOSIT,
    FIELD_NICKNAME,
    FIELD_SHARE_TYPE,
    clean_nickname,
    parse_deposit,
)
from target_app.members import Member, Product, parse_openable_product

SHARE_TYPE_INVALID = "Select a valid share type."


@dataclass(frozen=True)
class ShareDraft:
    member: Member
    product: Product
    deposit: Decimal
    nickname: str


@dataclass(frozen=True)
class DraftRejected:
    error: str


def validate_share_draft(member: Member, fields: Mapping[str, str]) -> ShareDraft | DraftRejected:
    """Check share type and deposit; the nickname is optional and only trimmed."""
    product = parse_openable_product(fields.get(FIELD_SHARE_TYPE))
    if product is None:
        return DraftRejected(error=SHARE_TYPE_INVALID)
    deposit = parse_deposit(fields.get(FIELD_DEPOSIT))
    if deposit is None:
        return DraftRejected(error=DEPOSIT_NOT_POSITIVE)
    return ShareDraft(
        member=member,
        product=product,
        deposit=deposit,
        nickname=clean_nickname(fields.get(FIELD_NICKNAME)),
    )
