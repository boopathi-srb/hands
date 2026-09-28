"""apply_overlay / load_for_tenant: overrides how steps find things, never which steps exist."""

from __future__ import annotations

from pathlib import Path

import pytest

from hands.catalog import ArtifactStore, apply_overlay, load_for_tenant
from hands.core.artifact import OpenStep, iter_all_steps
from hands.core.targets import TargetSpec

from .fixtures import PRAIRIE_BALANCE_TARGET, PRAIRIE_LOGIN, balance_capability, prairie_overlay


def test_prairie_overlay_overrides_targets_entry_points_outcomes_and_carries_aliases() -> None:
    base = balance_capability()
    result = apply_overlay(base, prairie_overlay())

    assert result.ok and result.error is None
    effective = result.capability
    assert effective is not None
    steps = {step.id: step for step in iter_all_steps(effective)}
    assert steps["read_balance"].target == TargetSpec.model_validate(PRAIRIE_BALANCE_TARGET)  # type: ignore[union-attr]
    login_open = steps["login_open"]
    assert isinstance(login_open, OpenStep) and login_open.entry_point == PRAIRIE_LOGIN
    assert effective.outcomes[0].when.pattern == "No account found"  # type: ignore[union-attr]
    assert result.aliases == {"Member Number": "Account Number", "Search": "Find", "Regular Savings": "Share Savings"}
    assert result.tenant_id == "prairie"


def test_overlay_never_changes_the_step_list_or_the_base() -> None:
    base = balance_capability()
    effective = apply_overlay(base, prairie_overlay()).capability

    assert effective is not None
    assert [step.id for step in iter_all_steps(effective)] == [step.id for step in iter_all_steps(base)]
    assert base.steps[3].target.description == "Regular Savings balance"  # type: ignore[union-attr]
    unchanged = {step.id: step for step in effective.steps}
    assert unchanged["search"] == base.steps[2]


def test_empty_overlay_yields_the_base_capability() -> None:
    base = balance_capability()
    empty = prairie_overlay(entry_point_overrides={}, target_overrides={}, text_aliases={}, outcome_overrides={})

    result = apply_overlay(base, empty)

    assert result.capability == base
    assert result.aliases == {}


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"capability_id": "coreone.other"}, "not 'coreone.member_balance'"),
        ({"base_version_range": ">=2.0.0"}, "outside the overlay's base_version_range"),
        ({"base_version_range": ">=1.0.0,<1.2.0"}, "outside"),
        ({"base_version_range": "~>1.0"}, "is invalid"),
        ({"target_overrides": {"no_such_step": PRAIRIE_BALANCE_TARGET}}, "unknown step id 'no_such_step'"),
        ({"entry_point_overrides": {"no_such_step": PRAIRIE_LOGIN}}, "unknown step id 'no_such_step'"),
        ({"entry_point_overrides": {"search": PRAIRIE_LOGIN}}, "not 'open'"),
        ({"target_overrides": {"sign_in": PRAIRIE_BALANCE_TARGET}}, "without a target"),
        ({"outcome_overrides": {"NO_SUCH_CODE": {"kind": "text_visible", "pattern": "x"}}}, "unknown outcome code"),
    ],
)
def test_invalid_overlays_are_error_results(overrides: dict[str, object], expected_error: str) -> None:
    result = apply_overlay(balance_capability(), prairie_overlay(**overrides))

    assert result.capability is None
    assert not result.ok
    assert expected_error in (result.error or "")


def test_version_range_boundaries() -> None:
    inside = apply_overlay(balance_capability("1.0.0"), prairie_overlay(base_version_range=">=1.0.0,<2.0.0"))
    at_upper = apply_overlay(balance_capability("2.0.0"), prairie_overlay(base_version_range=">=1.0.0,<2.0.0"))

    assert inside.ok
    assert not at_upper.ok


def test_load_for_tenant_combinations(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.save(balance_capability())
    store.save_overlay(prairie_overlay())

    base_only = load_for_tenant(store, "coreone.member_balance", None)
    without_overlay = load_for_tenant(store, "coreone.member_balance", "lakeside")
    with_overlay = load_for_tenant(store, "coreone.member_balance", "prairie")
    missing = load_for_tenant(store, "coreone.missing", "prairie")

    assert base_only.capability == balance_capability() and base_only.aliases == {}
    assert without_overlay.capability == balance_capability() and without_overlay.tenant_id == "lakeside"
    assert with_overlay.ok and with_overlay.aliases["Search"] == "Find"
    assert not missing.ok and missing.error


def test_load_for_tenant_with_corrupted_overlay_is_an_error(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.save(balance_capability())
    overlay_dir = tmp_path / "coreone.member_balance" / "overlays"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "prairie.json").write_text("{}", encoding="utf-8")

    result = load_for_tenant(store, "coreone.member_balance", "prairie")

    assert not result.ok and "failed validation" in (result.error or "")
