"""Unit tests for the in-memory FaultBook, the fault spec parser, and overlay mapping."""

from __future__ import annotations

import pytest

from target_app.app import seed_faults
from target_app.faults import (
    ANY_TENANT,
    FaultArmRequest,
    FaultBook,
    FaultName,
    FiredFaults,
    parse_fault_spec,
)
from target_app.rendering import Overlays

TENANTS = ["lakeside", "prairie"]


@pytest.fixture
def book() -> FaultBook:
    return FaultBook(default_slow_delay_ms=4000)


def _request(
    fault: FaultName, count: int = 1, tenant: str = "lakeside", **extra: int
) -> FaultArmRequest:
    return FaultArmRequest(fault=fault, count=count, tenant=tenant, **extra)


def test_empty_book_fires_nothing(book: FaultBook) -> None:
    assert book.list_armed() == []
    assert book.consume("lakeside") == FiredFaults()


def test_fault_fires_count_times_then_disarms(book: FaultBook) -> None:
    book.arm(_request(FaultName.APP_ERROR, count=2))
    assert book.consume("lakeside").has(FaultName.APP_ERROR)
    assert book.list_armed()[0].remaining == 1
    assert book.consume("lakeside").has(FaultName.APP_ERROR)
    assert book.list_armed() == []
    assert not book.consume("lakeside").names


def test_fault_is_scoped_to_its_tenant(book: FaultBook) -> None:
    book.arm(_request(FaultName.NATIVE_ALERT, tenant="prairie"))
    assert not book.consume("lakeside").names
    assert book.consume("prairie").has(FaultName.NATIVE_ALERT)


def test_any_tenant_fault_fires_for_first_tenant(book: FaultBook) -> None:
    book.arm(_request(FaultName.MAINTENANCE_NOTICE, tenant=ANY_TENANT))
    assert book.consume("prairie").has(FaultName.MAINTENANCE_NOTICE)
    assert not book.consume("lakeside").names


def test_rearming_replaces_remaining_count(book: FaultBook) -> None:
    book.arm(_request(FaultName.SLOW, count=5))
    book.arm(_request(FaultName.SLOW, count=1))
    assert [armed.remaining for armed in book.list_armed()] == [1]


def test_multiple_faults_fire_together(book: FaultBook) -> None:
    book.arm(_request(FaultName.MAINTENANCE_NOTICE))
    book.arm(_request(FaultName.NATIVE_ALERT))
    fired = book.consume("lakeside")
    assert fired.names == {FaultName.MAINTENANCE_NOTICE, FaultName.NATIVE_ALERT}
    assert fired.delay_ms == 0


def test_slow_uses_default_delay(book: FaultBook) -> None:
    book.arm(_request(FaultName.SLOW))
    assert book.consume("lakeside").delay_ms == 4000


def test_slow_uses_requested_delay_including_zero(book: FaultBook) -> None:
    book.arm(_request(FaultName.SLOW, delay_ms=0))
    assert book.consume("lakeside").delay_ms == 0
    book.arm(_request(FaultName.SLOW, delay_ms=250))
    assert book.consume("lakeside").delay_ms == 250


def test_clear_all_and_by_tenant(book: FaultBook) -> None:
    book.arm(_request(FaultName.SLOW, tenant="lakeside"))
    book.arm(_request(FaultName.SLOW, tenant="prairie"))
    assert book.clear("prairie") == 1
    assert [armed.tenant for armed in book.list_armed()] == ["lakeside"]
    assert book.clear() == 1
    assert book.clear() == 0


def test_arm_all_and_list_returns_copies(book: FaultBook) -> None:
    armed = book.arm_all([_request(FaultName.SLOW), _request(FaultName.APP_ERROR)])
    assert len(armed) == 2
    listed = book.list_armed()
    listed[0].remaining = 99
    assert book.list_armed()[0].remaining == 1


@pytest.mark.parametrize("count", [0, -1, 1001])
def test_arm_request_rejects_out_of_range_count(count: int) -> None:
    with pytest.raises(ValueError):
        FaultArmRequest(fault=FaultName.SLOW, count=count)


@pytest.mark.parametrize("spec", [None, "", " , ,"])
def test_parse_fault_spec_empty(spec: str | None) -> None:
    parsed = parse_fault_spec(spec, TENANTS)
    assert parsed.requests == [] and parsed.errors == []


def test_parse_fault_spec_valid_entries() -> None:
    parsed = parse_fault_spec("slow:2, identity_check:1 ,app_error,native_alert:3:prairie", TENANTS)
    assert parsed.errors == []
    assert [(r.fault.value, r.count, r.tenant) for r in parsed.requests] == [
        ("slow", 2, ANY_TENANT),
        ("identity_check", 1, ANY_TENANT),
        ("app_error", 1, ANY_TENANT),
        ("native_alert", 3, "prairie"),
    ]


@pytest.mark.parametrize(
    ("spec", "error_fragment"),
    [
        ("explode:1", "unknown fault"),
        ("slow:x", "count must be"),
        ("slow:0", "count must be"),
        ("slow:1001", "count must be"),
        ("slow:1:mars", "unknown tenant"),
        ("slow:1:lakeside:extra", "too many"),
    ],
)
def test_parse_fault_spec_reports_bad_entries(spec: str, error_fragment: str) -> None:
    parsed = parse_fault_spec(f"{spec},app_error:1", TENANTS)
    assert len(parsed.errors) == 1 and error_fragment in parsed.errors[0]
    assert [r.fault for r in parsed.requests] == [FaultName.APP_ERROR]


def test_seed_faults_arms_valid_and_skips_invalid(
    book: FaultBook, caplog: pytest.LogCaptureFixture
) -> None:
    assert seed_faults(book, "slow:2,bogus:1") == 1
    assert [armed.fault for armed in book.list_armed()] == [FaultName.SLOW]
    assert "seed_faults failed" in caplog.text


def test_seed_faults_empty_spec(book: FaultBook) -> None:
    assert seed_faults(book, "") == 0


def test_overlays_from_fired() -> None:
    assert Overlays.from_fired(FiredFaults()) == Overlays()
    fired = FiredFaults(names=frozenset({FaultName.IDENTITY_CHECK, FaultName.SLOW}), delay_ms=10)
    assert Overlays.from_fired(fired) == Overlays(identity_check=True)
