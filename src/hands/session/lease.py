"""Control lease: exactly one answer to "who is in control of this live session".

State machine (holder, holder_id):

    nobody     --grant_automation(run_id)-->  automation(run_id)
    automation --release(reason)---------->   nobody
    nobody     --take_human(operator_id)-->   human(operator_id)   only while an intervention is open
    human      --hand_back(operator_id)--->   nobody               only by the operator who holds it
    human      --release(reason)---------->   nobody               forced (timeout, abort, shutdown)

There is no direct automation <-> human edge: control always passes through `nobody`, so an audit
trail never shows two holders overlapping. Re-granting to the current holder is an idempotent no-op.
Invalid transitions return a `LeaseRefused` result (never raise), are logged, and change nothing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from hands.core.control import ControlLease, Holder
from hands.core.log import get_logger, log_failure
from hands.core.ports import EvidenceSink
from hands.session.support import Clock, utc_now, wait_for_event

_logger: logging.Logger = get_logger(__name__)

LeaseRefusalCode = Literal[
    "invalid_identity",
    "held_by_automation",
    "held_by_other_run",
    "held_by_human",
    "not_held",
    "not_holder",
    "no_open_intervention",
]


class LeaseTransition(BaseModel):
    """One audited change of holder."""

    session_id: str
    from_holder: Holder
    from_holder_id: str | None
    to_holder: Holder
    to_holder_id: str | None
    reason: str
    at: datetime


class LeaseChanged(BaseModel):
    """The requested state holds. `transition` is None when it already held (idempotent)."""

    ok: Literal[True] = True
    lease: ControlLease
    transition: LeaseTransition | None = None


class LeaseRefused(BaseModel):
    """The transition was not allowed; `lease` is the unchanged current lease."""

    ok: Literal[False] = False
    code: LeaseRefusalCode
    message: str
    lease: ControlLease


LeaseResult = LeaseChanged | LeaseRefused


class OpenInterventionLookup(Protocol):
    """Answers whether a session currently has an open intervention (the InterventionBoard does)."""

    def has_open(self, session_id: str) -> bool: ...


class LeaseManager:
    """Holds the control lease for one live session."""

    def __init__(
        self,
        session_id: str,
        interventions: OpenInterventionLookup | None = None,
        evidence: EvidenceSink | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._session_id = session_id
        self._interventions = interventions
        self._evidence = evidence
        self._clock = clock
        self._lease = ControlLease(
            session_id=session_id, holder="nobody", since=clock(), reason="session created"
        )
        self._audit: list[LeaseTransition] = []
        self._changed = asyncio.Event()

    @property
    def session_id(self) -> str:
        return self._session_id

    def current(self) -> ControlLease:
        """A copy of the current lease."""
        return self._lease.model_copy()

    def audit_trail(self) -> list[LeaseTransition]:
        """Every transition so far, oldest first."""
        return list(self._audit)

    def is_held_by(self, holder: Holder, holder_id: str | None = None) -> bool:
        """True when `holder` holds the lease (and, if given, with this exact holder id)."""
        if self._lease.holder != holder:
            return False
        return holder_id is None or self._lease.holder_id == holder_id

    # ------------------------------------------------------------ transitions

    def grant_automation(self, run_id: str, reason: str = "automation granted") -> LeaseResult:
        """nobody -> automation(run_id)."""
        if not run_id:
            return self._refuse("grant_automation", "invalid_identity", "run_id must not be empty")
        if self.is_held_by("automation", run_id):
            return LeaseChanged(lease=self.current())
        if self._lease.holder == "automation":
            return self._refuse(
                "grant_automation", "held_by_other_run", "another run holds control"
            )
        if self._lease.holder == "human":
            return self._refuse("grant_automation", "held_by_human", "a human holds control")
        return self._transfer("automation", run_id, reason)

    def release(self, reason: str, to: Literal["nobody"] = "nobody") -> LeaseResult:
        """automation|human -> nobody. Used by the escalator and for forced release on timeout."""
        if self._lease.holder == "nobody":
            return self._refuse("release", "not_held", "nobody holds control")
        return self._transfer(to, None, reason)

    def take_human(self, operator_id: str, reason: str = "operator took control") -> LeaseResult:
        """nobody -> human(operator_id), only while this session has an open intervention."""
        if not operator_id:
            return self._refuse("take_human", "invalid_identity", "operator_id must not be empty")
        if self.is_held_by("human", operator_id):
            return LeaseChanged(lease=self.current())
        if self._lease.holder == "human":
            return self._refuse("take_human", "held_by_human", "another operator holds control")
        if self._lease.holder == "automation":
            return self._refuse("take_human", "held_by_automation", "automation holds control")
        if not self._has_open_intervention():
            return self._refuse("take_human", "no_open_intervention", "no open intervention")
        return self._transfer("human", operator_id, reason)

    def hand_back(
        self, operator_id: str, reason: str = "operator handed back control"
    ) -> LeaseResult:
        """human(operator_id) -> nobody. Only the operator who holds control can hand it back."""
        if not self.is_held_by("human", operator_id):
            return self._refuse("hand_back", "not_holder", "operator does not hold control")
        return self._transfer("nobody", None, reason)

    # ------------------------------------------------------------ waiting

    async def wait_for_holder(self, holder: Holder, timeout: float | None = None) -> bool:
        """Wait until `holder` holds the lease. `timeout` is in seconds; returns False on timeout."""
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while self._lease.holder != holder:
            remaining = None if deadline is None else deadline - loop.time()
            if remaining is not None and remaining <= 0:
                return False
            if not await wait_for_event(self._changed, remaining):
                return False
        return True

    async def wait_for_change(self, timeout: float | None = None) -> bool:
        """Wait for the next transition of any kind. Returns False on timeout."""
        return await wait_for_event(self._changed, timeout)

    # ------------------------------------------------------------ internals

    def _has_open_intervention(self) -> bool:
        return self._interventions is not None and self._interventions.has_open(self._session_id)

    def _transfer(self, holder: Holder, holder_id: str | None, reason: str) -> LeaseChanged:
        now = self._clock()
        transition = LeaseTransition(
            session_id=self._session_id,
            from_holder=self._lease.holder,
            from_holder_id=self._lease.holder_id,
            to_holder=holder,
            to_holder_id=holder_id,
            reason=reason,
            at=now,
        )
        self._lease = ControlLease(
            session_id=self._session_id,
            holder=holder,
            holder_id=holder_id,
            since=now,
            reason=reason,
        )
        self._audit.append(transition)
        self._emit(transition)
        self._notify_waiters()
        return LeaseChanged(lease=self.current(), transition=transition)

    def _emit(self, transition: LeaseTransition) -> None:
        _logger.info(
            "control %s: %s(%s) -> %s(%s) [%s]",
            transition.session_id,
            transition.from_holder,
            transition.from_holder_id,
            transition.to_holder,
            transition.to_holder_id,
            transition.reason,
        )
        if self._evidence is not None:
            self._evidence.event("control_transferred", **transition.model_dump(mode="json"))

    def _notify_waiters(self) -> None:
        fired = self._changed
        self._changed = asyncio.Event()
        fired.set()

    def _refuse(self, function_name: str, code: LeaseRefusalCode, message: str) -> LeaseRefused:
        log_failure(
            _logger,
            f"LeaseManager.{function_name}",
            f"{code}: {message}",
            session_id=self._session_id,
            holder=self._lease.holder,
            holder_id=self._lease.holder_id,
        )
        return LeaseRefused(code=code, message=message, lease=self.current())
