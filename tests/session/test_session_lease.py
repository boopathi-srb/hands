"""LeaseManager: valid and invalid transitions, audit trail, evidence, waiting."""

from __future__ import annotations

import asyncio

from hands.session.doubles import InMemoryEvidence
from hands.session.lease import LeaseChanged, LeaseManager, LeaseRefused

SESSION = "session-1"


class OpenInterventions:
    """Minimal OpenInterventionLookup: a set of sessions that have an open intervention."""

    def __init__(self, *session_ids: str) -> None:
        self.session_ids = set(session_ids)

    def has_open(self, session_id: str) -> bool:
        return session_id in self.session_ids


def make_lease(open_intervention: bool = True) -> tuple[LeaseManager, InMemoryEvidence]:
    evidence = InMemoryEvidence()
    lookup = OpenInterventions(SESSION) if open_intervention else OpenInterventions()
    return LeaseManager(SESSION, interventions=lookup, evidence=evidence), evidence


def test_new_lease_is_held_by_nobody_with_empty_audit() -> None:
    lease, _ = make_lease()
    assert lease.current().holder == "nobody"
    assert lease.current().holder_id is None
    assert lease.audit_trail() == []


def test_full_handoff_cycle_is_audited_in_order() -> None:
    lease, evidence = make_lease()
    assert lease.grant_automation("run-1").ok
    assert lease.release(reason="escalating").ok
    assert lease.take_human("alice").ok
    assert lease.hand_back("alice").ok
    assert lease.grant_automation("run-1").ok

    holders = [(t.to_holder, t.to_holder_id) for t in lease.audit_trail()]
    assert holders == [
        ("automation", "run-1"),
        ("nobody", None),
        ("human", "alice"),
        ("nobody", None),
        ("automation", "run-1"),
    ]
    assert evidence.kinds() == ["control_transferred"] * 5
    assert evidence.of_kind("control_transferred")[2]["to_holder_id"] == "alice"


def test_regrant_to_same_run_is_idempotent_and_not_audited() -> None:
    lease, _ = make_lease()
    lease.grant_automation("run-1")
    result = lease.grant_automation("run-1")
    assert isinstance(result, LeaseChanged)
    assert result.transition is None
    assert len(lease.audit_trail()) == 1


def test_grant_to_other_run_is_refused_without_change() -> None:
    lease, _ = make_lease()
    lease.grant_automation("run-1")
    result = lease.grant_automation("run-2")
    assert isinstance(result, LeaseRefused)
    assert result.code == "held_by_other_run"
    assert lease.current().holder_id == "run-1"


def test_grant_while_human_holds_is_refused() -> None:
    lease, _ = make_lease()
    lease.take_human("alice")
    result = lease.grant_automation("run-1")
    assert isinstance(result, LeaseRefused)
    assert result.code == "held_by_human"
    assert lease.is_held_by("human", "alice")


def test_empty_identities_are_refused() -> None:
    lease, _ = make_lease()
    grant = lease.grant_automation("")
    take = lease.take_human("")
    assert isinstance(grant, LeaseRefused) and grant.code == "invalid_identity"
    assert isinstance(take, LeaseRefused) and take.code == "invalid_identity"


def test_take_human_requires_open_intervention() -> None:
    lease, _ = make_lease(open_intervention=False)
    result = lease.take_human("alice")
    assert isinstance(result, LeaseRefused)
    assert result.code == "no_open_intervention"


def test_take_human_without_lookup_is_refused() -> None:
    lease = LeaseManager(SESSION)
    result = lease.take_human("alice")
    assert isinstance(result, LeaseRefused)
    assert result.code == "no_open_intervention"


def test_take_human_while_automation_holds_is_refused() -> None:
    lease, _ = make_lease()
    lease.grant_automation("run-1")
    result = lease.take_human("alice")
    assert isinstance(result, LeaseRefused)
    assert result.code == "held_by_automation"


def test_second_operator_cannot_take_and_same_operator_is_idempotent() -> None:
    lease, _ = make_lease()
    lease.take_human("alice")
    other = lease.take_human("bob")
    same = lease.take_human("alice")
    assert isinstance(other, LeaseRefused) and other.code == "held_by_human"
    assert isinstance(same, LeaseChanged) and same.transition is None


def test_hand_back_only_by_holding_operator() -> None:
    lease, _ = make_lease()
    lease.take_human("alice")
    wrong = lease.hand_back("bob")
    assert isinstance(wrong, LeaseRefused) and wrong.code == "not_holder"
    assert lease.hand_back("alice").ok
    assert lease.current().holder == "nobody"


def test_hand_back_when_automation_holds_is_refused() -> None:
    lease, _ = make_lease()
    lease.grant_automation("run-1")
    result = lease.hand_back("alice")
    assert isinstance(result, LeaseRefused)
    assert result.code == "not_holder"


def test_release_when_nobody_holds_is_refused_and_not_audited() -> None:
    lease, evidence = make_lease()
    result = lease.release(reason="nothing to release")
    assert isinstance(result, LeaseRefused)
    assert result.code == "not_held"
    assert lease.audit_trail() == []
    assert evidence.events == []


def test_forced_release_from_human_is_allowed() -> None:
    lease, _ = make_lease()
    lease.take_human("alice")
    result = lease.release(reason="timeout")
    assert isinstance(result, LeaseChanged)
    assert result.lease.holder == "nobody"
    assert lease.audit_trail()[-1].reason == "timeout"


def test_current_returns_a_copy() -> None:
    lease, _ = make_lease()
    snapshot = lease.current()
    lease.grant_automation("run-1")
    assert snapshot.holder == "nobody"


async def test_wait_for_holder_returns_true_immediately_when_already_held() -> None:
    lease, _ = make_lease()
    assert await lease.wait_for_holder("nobody", timeout=0)


async def test_wait_for_holder_times_out() -> None:
    lease, _ = make_lease()
    assert not await lease.wait_for_holder("human", timeout=0.02)


async def test_wait_for_holder_wakes_on_transition() -> None:
    lease, _ = make_lease()
    waiter = asyncio.create_task(lease.wait_for_holder("automation", timeout=1.0))
    await asyncio.sleep(0)
    lease.grant_automation("run-1")
    assert await waiter


async def test_wait_for_holder_skips_intermediate_holders() -> None:
    lease, _ = make_lease()
    waiter = asyncio.create_task(lease.wait_for_holder("nobody", timeout=1.0))
    lease.grant_automation("run-1")
    await asyncio.sleep(0)
    assert not waiter.done()
    lease.release(reason="done")
    assert await waiter


async def test_wait_for_change_times_out_and_wakes() -> None:
    lease, _ = make_lease()
    assert not await lease.wait_for_change(timeout=0.01)
    waiter = asyncio.create_task(lease.wait_for_change(timeout=1.0))
    await asyncio.sleep(0)
    lease.grant_automation("run-1")
    assert await waiter
