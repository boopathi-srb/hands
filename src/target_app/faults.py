"""Fault injection: the ways a real legacy core misbehaves, armed on demand per tenant.

A fault armed with count n fires on the next n eligible content-frame page loads, then disarms.
When several faults are armed they all fire on the same load (and all decrement). Page-replacing
faults take precedence in the order: session_expired, app_error.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, Field

ANY_TENANT = "*"
MAX_FAULT_COUNT = 1000
MAX_DELAY_MS = 120_000


class FaultName(StrEnum):
    SESSION_EXPIRED = "session_expired"
    SLOW = "slow"
    MAINTENANCE_NOTICE = "maintenance_notice"
    NATIVE_ALERT = "native_alert"
    IDENTITY_CHECK = "identity_check"
    APP_ERROR = "app_error"


class FaultArmRequest(BaseModel):
    """Body of POST /_admin/faults. tenant '*' (the default) means whichever tenant loads next."""

    fault: FaultName
    count: int = Field(default=1, ge=1, le=MAX_FAULT_COUNT)
    tenant: str = ANY_TENANT
    delay_ms: int | None = Field(default=None, ge=0, le=MAX_DELAY_MS)


class ArmedFault(BaseModel):
    fault: FaultName
    tenant: str
    remaining: int
    delay_ms: int | None = None


@dataclass(frozen=True)
class FiredFaults:
    """The faults that fired on one page load."""

    names: frozenset[FaultName] = frozenset()
    delay_ms: int = 0

    def has(self, fault: FaultName) -> bool:
        return fault in self.names


_FaultKey = tuple[str, FaultName]


class FaultBook:
    """In-memory registry of armed faults. Handlers are async, so access is single-threaded."""

    def __init__(self, default_slow_delay_ms: int) -> None:
        self._default_slow_delay_ms = default_slow_delay_ms
        self._armed: dict[_FaultKey, ArmedFault] = {}

    def arm(self, request: FaultArmRequest) -> ArmedFault:
        """Arm (or re-arm, replacing the remaining count) one fault for one tenant."""
        armed = ArmedFault(
            fault=request.fault,
            tenant=request.tenant,
            remaining=request.count,
            delay_ms=request.delay_ms,
        )
        self._armed[(request.tenant, request.fault)] = armed
        return armed

    def arm_all(self, requests: Iterable[FaultArmRequest]) -> list[ArmedFault]:
        return [self.arm(request) for request in requests]

    def list_armed(self) -> list[ArmedFault]:
        return [armed.model_copy() for armed in self._armed.values()]

    def clear(self, tenant: str | None = None) -> int:
        """Disarm all faults, or only those armed for one tenant key. Returns the number removed."""
        keys_to_remove = [key for key in self._armed if tenant is None or key[0] == tenant]
        for key in keys_to_remove:
            del self._armed[key]
        return len(keys_to_remove)

    def consume(self, tenant: str) -> FiredFaults:
        """Fire every fault armed for this tenant (or any tenant) once, decrementing counts."""
        fired = [self._fire(key) for key in self._keys_for(tenant)]
        if not fired:
            return FiredFaults()
        return FiredFaults(
            names=frozenset(armed.fault for armed in fired),
            delay_ms=self._slow_delay(fired),
        )

    def _keys_for(self, tenant: str) -> list[_FaultKey]:
        return [key for key in self._armed if key[0] in (tenant, ANY_TENANT)]

    def _fire(self, key: _FaultKey) -> ArmedFault:
        armed = self._armed[key]
        remaining = armed.remaining - 1
        if remaining <= 0:
            del self._armed[key]
        else:
            self._armed[key] = armed.model_copy(update={"remaining": remaining})
        return armed

    def _slow_delay(self, fired: list[ArmedFault]) -> int:
        delays = [
            armed.delay_ms if armed.delay_ms is not None else self._default_slow_delay_ms
            for armed in fired
            if armed.fault is FaultName.SLOW
        ]
        return max(delays, default=0)


@dataclass
class FaultSpecParse:
    requests: list[FaultArmRequest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _parse_count(raw_count: str) -> int | None:
    cleaned = raw_count.strip()
    if not (cleaned.isascii() and cleaned.isdigit()):
        return None
    count = int(cleaned)
    if count < 1 or count > MAX_FAULT_COUNT:
        return None
    return count


def _parse_fault_entry(entry: str, known_tenants: Iterable[str]) -> FaultArmRequest | str:
    """Parse 'fault[:count[:tenant]]'. Returns the request, or an error message."""
    parts = [part.strip() for part in entry.split(":")]
    if len(parts) > 3:
        return f"too many ':' separated parts in {entry!r}"
    fault_values = {fault.value for fault in FaultName}
    if parts[0] not in fault_values:
        return f"unknown fault {parts[0]!r}"
    count = _parse_count(parts[1]) if len(parts) > 1 else 1
    if count is None:
        return f"count must be an integer 1..{MAX_FAULT_COUNT} in {entry!r}"
    tenant = parts[2] if len(parts) > 2 else ANY_TENANT
    if tenant != ANY_TENANT and tenant not in set(known_tenants):
        return f"unknown tenant {tenant!r}"
    return FaultArmRequest(fault=FaultName(parts[0]), count=count, tenant=tenant)


def parse_fault_spec(spec: str | None, known_tenants: Iterable[str]) -> FaultSpecParse:
    """Parse the COREONE_FAULTS format 'fault:count,fault:count' (optional ':tenant' suffix)."""
    result = FaultSpecParse()
    if not spec:
        return result
    tenant_list = list(known_tenants)
    for raw_entry in spec.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        parsed = _parse_fault_entry(entry, tenant_list)
        if isinstance(parsed, str):
            result.errors.append(parsed)
        else:
            result.requests.append(parsed)
    return result
