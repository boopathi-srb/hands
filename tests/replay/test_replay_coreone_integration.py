"""Integration: the replay engine against the CoreOne FakeSurface with the real policy gate, evidence
recorder + redactor, vendor profile, tenant overlay, and scripted escalator. Only the app is simulated."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hands.catalog import ArtifactStore, apply_overlay, load_for_tenant, merge_profile
from hands.core.artifact import Capability, TenantOverlay
from hands.core.ports import KeyEvent, PointerEvent
from hands.core.results import BusinessOutcomeResult, EscalatedResult, FailedResult, SuccessResult
from hands.evidence import EvidenceRecorder, RecorderReady
from hands.policy import YamlPolicyGate, load_policy
from hands.profiles import AppProfile, load_profile
from hands.redact import Redactor
from hands.replay import ReplayEngine
from hands.session.board import InterventionBoard
from hands.session.escalation import ScriptedEscalator
from hands.session.lease import LeaseManager
from hands.surfaces.fake import FakeSurface, coreone_fake

from .fakes import FakeClock, FakeCredentials

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:8700"
TEST_PASSWORD = "integration-test-password"
SESSION_ID = "session-int"


# ---------------------------------------------------------------- the capability, as the recorder would save it


def profile() -> AppProfile:
    loaded = load_profile(REPO_ROOT / "profiles" / "coreone.yaml")
    assert loaded.profile is not None, loaded.error
    return loaded.profile


def cand(kind: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, "confidence": 0.8, "reason": "integration", **fields}


def target(description: str, *candidates: dict[str, Any]) -> dict[str, Any]:
    return {"description": description, "candidates": list(candidates)}


def balance_capability(recoveries_first: tuple[str, ...] = ()) -> Capability:
    coreone = profile()
    data = {
        "id": "coreone.member_balance",
        "version": "1.0.0",
        "status": "approved",
        "title": "Member savings balance",
        "description": "Look up a member by number and return the savings balance.",
        "app": {"vendor": "Northwind Core Systems", "product": "CoreOne", "product_version": "7.4",
                "surface": "web"},
        "inputs": {"member_number": {"type": "string", "description": "Member number", "pattern": r"^\d+$"}},
        "outputs": {"balance": {"type": "decimal", "description": "Savings balance"}},
        "credentials": {name: spec.model_dump() for name, spec in coreone.credentials.items()},
        "subflows": {"login": [step.model_dump() for step in coreone.subflows["login"]]},
        "steps": [
            {"id": "sign_in", "action": "subflow", "description": "Sign on", "subflow": "login"},
            {"id": "open_inquiry", "action": "click", "description": "Open Member Inquiry",
             "target": target("Member Inquiry link", cand("role_name", role="link", name="Member Inquiry")),
             "postcondition": {"kind": "node_present", "target": target(
                 "Member number field", cand("label", label="Member Number", role="textbox"))}},
            {"id": "type_member", "action": "type", "description": "Enter the member number",
             "value": "{{member_number}}",
             "target": target("Member number field", cand("label", label="Member Number", role="textbox"))},
            {"id": "search", "action": "click", "description": "Search",
             "target": target("Search button", cand("role_name", role="button", name="Search")),
             "postcondition": {"kind": "text_visible", "pattern": "Member Detail"}},
            {"id": "read_balance", "action": "extract", "description": "Read the savings balance",
             "output": "balance",
             "target": target("Regular Savings balance",
                              cand("text_anchor", anchor_text="Regular Savings", relation="right_of", role="cell"),
                              cand("structural", container_path=["frame:content"],
                                   structural_path="table[2]/row[2]/cell[3]"))},
        ],
        "checkpoint": {"kind": "text_visible", "pattern": "Member Detail"},
        "provenance": {"discovery_run_id": "disc-int", "recorded_at": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
                       "planner": "scripted", "goal": "read a member's savings balance",
                       "recorded_on_tenant": "lakeside"},
    }
    merged = merge_profile(Capability.model_validate(data), coreone)
    return _prioritise(merged, recoveries_first)


def _prioritise(capability: Capability, names: tuple[str, ...]) -> Capability:
    first = [rule for rule in capability.recoveries if rule.name in names]
    rest = [rule for rule in capability.recoveries if rule.name not in names]
    return capability.model_copy(update={"recoveries": [*first, *rest]})


def prairie_overlay() -> TenantOverlay:
    return TenantOverlay.model_validate({
        "tenant_id": "prairie",
        "capability_id": "coreone.member_balance",
        "base_version_range": ">=1.0.0,<2.0.0",
        "entry_point_overrides": {"login_open": f"{BASE_URL}/t/prairie/login"},
        "target_overrides": {"read_balance": target(
            "Share Savings balance (prairie column order)",
            cand("text_anchor", anchor_text="Share Savings", relation="same_row", role="cell", ordinal=1),
            cand("structural", container_path=["frame:content"], structural_path="table[2]/row[2]/cell[2]"))},
        "text_aliases": {"Member Number": "Account Number", "Search": "Find", "Regular Savings": "Share Savings"},
    })


# ---------------------------------------------------------------- wiring


class Wiring:
    def __init__(self, tmp_path: Path, tenant: str = "lakeside", run_id: str = "run-int") -> None:
        self.surface: FakeSurface = coreone_fake(tenant, base_url=BASE_URL, password=TEST_PASSWORD)
        loaded_policy = load_policy(REPO_ROOT / "policies" / "coreone.yaml")
        assert loaded_policy.ok
        self.policy = YamlPolicyGate(loaded_policy.config)
        self.redactor = Redactor()
        created = EvidenceRecorder.create(tmp_path / "evidence", run_id, self.redactor)
        assert isinstance(created, RecorderReady)
        self.recorder = created.recorder
        self.board = InterventionBoard()
        self.lease = LeaseManager(SESSION_ID, interventions=self.board, evidence=self.recorder)
        self.lease.grant_automation(run_id)
        self.clock = FakeClock()
        self.credentials = FakeCredentials({("teller", "username"): "teller1", ("teller", "password"): TEST_PASSWORD})
        self.run_id = run_id

    def engine(self, escalator: ScriptedEscalator | None = None) -> ReplayEngine:
        return ReplayEngine(
            self.surface, self.policy, self.recorder, self.credentials,
            escalator=escalator, secret_registrar=self.redactor.register_secret,
            monotonic=self.clock.monotonic, sleep=self.clock.sleep, now=self.clock.now,
        )

    def scripted_escalator(self, outcome: str, script: list[PointerEvent | KeyEvent], note: str = "") -> ScriptedEscalator:
        return ScriptedEscalator(
            self.board, self.lease, self.recorder, outcome=outcome,  # type: ignore[arg-type]
            operator_id="operator-7", note=note, script=script, surface=self.surface,
        )

    async def run(self, capability: Capability, member_number: str, **options: Any) -> Any:
        escalator = options.pop("escalator", None)
        return await self.engine(escalator).run(
            capability, {"member_number": member_number}, run_id=self.run_id, session_id=SESSION_ID, **options
        )

    def evidence_text(self) -> str:
        return "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                         for path in Path(self.recorder.run_dir).rglob("*") if path.is_file()
                         and path.suffix in (".json", ".jsonl", ".md"))


# ---------------------------------------------------------------- lakeside


async def test_lakeside_happy_path_with_real_policy_and_evidence(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    result = await wiring.run(balance_capability(), "10001")

    assert isinstance(result, SuccessResult), result
    assert result.outputs == {"balance": "1250.00"}
    assert result.drift.fallback_steps == []
    written = json.loads((Path(wiring.recorder.run_dir) / "result.json").read_text(encoding="utf-8"))
    assert written["status"] == "success"
    assert TEST_PASSWORD not in wiring.evidence_text()


async def test_lakeside_member_not_found_and_restricted(tmp_path: Path) -> None:
    not_found = await Wiring(tmp_path / "a").run(balance_capability(), "55555")
    restricted = await Wiring(tmp_path / "b").run(balance_capability(), "40300")

    assert isinstance(not_found, BusinessOutcomeResult)
    assert not_found.code == "MEMBER_NOT_FOUND"
    assert not_found.message == "No member found for number 55555."
    assert isinstance(restricted, BusinessOutcomeResult)
    assert restricted.code == "MEMBER_RESTRICTED"
    assert restricted.message is not None and "403-R" in restricted.message


async def test_maintenance_notice_is_absorbed(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    wiring.surface.inject_next("maintenance_notice", trigger="act")
    result = await wiring.run(balance_capability(), "10001")

    assert isinstance(result, SuccessResult)
    recovered = [trace for trace in result.steps if trace.recoveries_applied]
    assert recovered and recovered[0].recoveries_applied == ["maintenance_notice"]


async def test_native_alert_is_accepted(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    capability = balance_capability()
    engine = wiring.engine()
    wiring.surface.inject_next("native_alert", trigger="act")
    result = await engine.run(capability, {"member_number": "10001"}, run_id=wiring.run_id, session_id=SESSION_ID)

    assert isinstance(result, SuccessResult)
    assert any("native_alert" in trace.recoveries_applied for trace in result.steps)


async def test_session_expired_signs_on_again_and_restarts(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    original_perform = wiring.surface.perform
    armed = {"done": False}

    def perform_with_expiry(target: Any, action: Any, source: Any = "automation") -> Any:
        result = original_perform(target, action, source)
        if not armed["done"] and wiring.surface.current_screen == "member_10001":
            armed["done"] = True
            wiring.surface.set_screen("session_expired")
        return result

    wiring.surface.perform = perform_with_expiry  # type: ignore[method-assign]
    result = await wiring.run(balance_capability(), "10001")

    assert isinstance(result, SuccessResult), result
    assert result.outputs == {"balance": "1250.00"}
    search_traces = [trace for trace in result.steps if trace.step_id == "search"]
    assert search_traces[0].recoveries_applied == ["session_expired"]
    assert len(search_traces) == 2


async def test_persistent_app_error_exhausts_retry(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    capability = balance_capability()
    engine = wiring.engine()
    original_perform = wiring.surface.perform

    def perform_into_error(target: Any, action: Any, source: Any = "automation") -> Any:
        result = original_perform(target, action, source)
        if wiring.surface.current_screen == "member_10001":
            wiring.surface.set_screen("app_error")
        return result

    wiring.surface.perform = perform_into_error  # type: ignore[method-assign]
    result = await engine.run(capability, {"member_number": "10001"}, run_id=wiring.run_id, session_id=SESSION_ID)

    assert isinstance(result, FailedResult)
    assert result.failure.code == "recovery_exhausted"
    assert result.failure.step_id == "search"
    assert len(result.failure.evidence) == 2
    for relative_path in result.failure.evidence:
        assert (Path(wiring.recorder.run_dir) / relative_path).is_file()


# ---------------------------------------------------------------- escalation with the real session package


def identity_answer_script() -> list[PointerEvent | KeyEvent]:
    return [
        PointerEvent(type="click", x=482, y=250),  # the Answer textbox
        *[KeyEvent(type="char", key=letter, text=letter) for letter in "Quinn"],
        PointerEvent(type="click", x=423, y=301),  # Verify
    ]


async def test_identity_check_is_handed_to_a_human_who_answers_it(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    escalator = wiring.scripted_escalator("resume", identity_answer_script())
    wiring.surface.inject_next("identity_check", trigger="act")
    capability = balance_capability(recoveries_first=("identity_verification",))
    # The modal appears after the first act (opening sign-on); the operator answers it and hands back.
    result = await wiring.run(capability, "10001", escalator=escalator)

    assert isinstance(result, SuccessResult), result
    assert len(result.interventions) == 1
    assert wiring.lease.current().holder == "automation"


async def test_identity_check_abort_returns_escalated(tmp_path: Path) -> None:
    wiring = Wiring(tmp_path)
    escalator = wiring.scripted_escalator("abort", [], note="member could not be verified")
    wiring.surface.inject_next("identity_check", trigger="act")
    capability = balance_capability(recoveries_first=("identity_verification",))
    result = await wiring.run(capability, "10001", escalator=escalator)

    assert isinstance(result, EscalatedResult)
    assert result.operator_note == "member could not be verified"


async def test_identity_modal_is_not_shadowed_by_native_alert_rule(tmp_path: Path) -> None:
    """`native_alert` only matches native dialogs, so the in-page identity modal reaches its escalate rule."""
    wiring = Wiring(tmp_path)
    wiring.surface.inject_next("identity_check", trigger="act")
    result = await wiring.run(balance_capability(), "10001")

    assert isinstance(result, FailedResult)
    assert result.failure.code == "unexpected_state"
    assert "identity_verification" in result.failure.message


# ---------------------------------------------------------------- tenant variant through the catalog


async def test_prairie_needs_its_overlay(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    store.save(balance_capability())
    store.save_overlay(prairie_overlay())

    without_overlay = await Wiring(tmp_path / "base", tenant="prairie").run(balance_capability(), "10001")
    effective = load_for_tenant(store, "coreone.member_balance", "prairie")
    assert effective.capability is not None, effective.error
    with_overlay = await Wiring(tmp_path / "overlay", tenant="prairie").run(
        effective.capability, "10001", tenant_id="prairie", aliases=effective.aliases
    )

    assert isinstance(without_overlay, FailedResult)
    assert isinstance(with_overlay, SuccessResult), with_overlay
    assert with_overlay.outputs == {"balance": "1250.00"}
    assert with_overlay.tenant_id == "prairie"
    stats = store.record_run("coreone.member_balance", "1.0.0", with_overlay).stats
    assert stats is not None and stats.successes == 1


async def test_overlay_for_wrong_version_range_is_rejected() -> None:
    overlay = prairie_overlay().model_copy(update={"base_version_range": ">=2.0.0,<3.0.0"})
    result = apply_overlay(balance_capability(), overlay)

    assert not result.ok
    assert "outside" in (result.error or "")


@pytest.mark.parametrize("member_number", ["12AB", "", " "])
async def test_bad_member_numbers_never_reach_the_app(tmp_path: Path, member_number: str) -> None:
    wiring = Wiring(tmp_path)
    result = await wiring.run(balance_capability(), member_number)

    assert isinstance(result, FailedResult)
    assert result.failure.code == "invalid_input"
    assert wiring.surface.actions == []
