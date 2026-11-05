"""ArtifactStore: file layout, latest-version selection, discovery listing, overlays, stats."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hands.catalog import ArtifactStore, updated_replay_stats
from hands.core.artifact import ReplayStats
from hands.core.results import (
    BusinessOutcomeResult,
    DriftReport,
    EscalatedResult,
    FailedResult,
    FailureDetail,
    RunResult,
    SuccessResult,
)

from .fixtures import balance_capability, prairie_overlay

WHEN = datetime(2026, 9, 28, tzinfo=UTC)


def result_base(**extra: object) -> dict[str, object]:
    return {"run_id": "r1", "capability_id": "coreone.member_balance", "capability_version": "1.2.0",
            "started_at": WHEN, "finished_at": WHEN, "evidence_dir": "evidence/r1", **extra}


def success(fallback_steps: list[str] | None = None) -> SuccessResult:
    return SuccessResult(**result_base(drift=DriftReport(fallback_steps=fallback_steps or [])), outputs={})


def test_save_and_load_round_trip_uses_the_documented_layout(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    capability = balance_capability()

    written = store.save(capability)
    loaded = store.load("coreone.member_balance", "1.2.0")

    assert written.ok
    assert Path(written.path or "") == tmp_path / "coreone.member_balance" / "1.2.0.json"
    assert loaded.capability == capability
    assert loaded.error is None


def test_load_without_version_picks_latest_by_semver(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    for version in ("1.2.0", "1.10.0", "1.9.3"):
        store.save(balance_capability(version))

    assert store.list_versions("coreone.member_balance") == ["1.2.0", "1.9.3", "1.10.0"]
    assert store.load("coreone.member_balance").capability.version == "1.10.0"  # type: ignore[union-attr]


def test_load_errors_are_results_not_exceptions(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.save(balance_capability())

    assert "no stored versions" in (store.load("coreone.unknown").error or "")
    assert "invalid capability id" in (store.load("../etc").error or "")
    assert "invalid version" in (store.load("coreone.member_balance", "1.0").error or "")
    assert "not found" in (store.load("coreone.member_balance", "9.9.9").error or "")
    assert store.list_versions("") == []


def test_corrupted_file_is_reported_and_skipped_in_listing(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.save(balance_capability("1.0.0"))
    (tmp_path / "coreone.member_balance" / "1.1.0.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "other.broken").mkdir()
    (tmp_path / "other.broken" / "1.0.0.json").write_text('{"id": "other.broken"}', encoding="utf-8")

    assert "could not read" in (store.load("coreone.member_balance").error or "")
    assert "failed validation" in (store.load("other.broken").error or "")
    assert store.list_capabilities() == []


def test_list_capabilities_describes_the_contract(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.save(balance_capability("1.0.0"))
    store.save(balance_capability("1.2.0"))

    entries = store.list_capabilities()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.id == "coreone.member_balance"
    assert entry.latest_version == "1.2.0"
    assert entry.versions == ["1.0.0", "1.2.0"]
    assert entry.status == "approved"
    assert entry.inputs["member_number"].pattern == r"^\d+$"
    assert entry.inputs["member_number"].required is True
    assert entry.outputs["balance"].type == "decimal"
    assert entry.outcome_codes == ["MEMBER_NOT_FOUND"]


def test_list_capabilities_on_missing_root_is_empty(tmp_path: Path) -> None:
    assert ArtifactStore(tmp_path / "nowhere").list_capabilities() == []


def test_overlay_round_trip_absent_and_invalid(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    overlay = prairie_overlay()

    written = store.save_overlay(overlay)
    found = store.load_overlay("coreone.member_balance", "prairie")
    absent = store.load_overlay("coreone.member_balance", "lakeside")
    invalid_id = store.load_overlay("coreone.member_balance", "../x")

    assert Path(written.path or "") == tmp_path / "coreone.member_balance" / "overlays" / "prairie.json"
    assert found.status == "found" and found.overlay == overlay
    assert absent.status == "absent" and absent.overlay is None and absent.error is None
    assert invalid_id.status == "invalid"


def test_corrupted_overlay_is_invalid(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    overlay_dir = tmp_path / "coreone.member_balance" / "overlays"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "prairie.json").write_text("[]", encoding="utf-8")

    loaded = store.load_overlay("coreone.member_balance", "prairie")

    assert loaded.status == "invalid" and "not a JSON object" in (loaded.error or "")


def test_record_run_updates_replay_stats(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    store.save(balance_capability())
    results: list[RunResult] = [
        success(fallback_steps=["read_balance"]),
        BusinessOutcomeResult(**result_base(), code="MEMBER_NOT_FOUND"),
        FailedResult(**result_base(), failure=FailureDetail(code="target_not_found", step_id="search", message="x")),
        EscalatedResult(**result_base(), intervention_id="i1", reason="human"),
    ]

    updates = [store.record_run("coreone.member_balance", "1.2.0", result) for result in results]

    assert updates[-1].stats == ReplayStats(runs=4, successes=1, business_outcomes=1, failures=1, fallback_matches=1)
    reloaded = store.load("coreone.member_balance", "1.2.0").capability
    assert reloaded is not None and reloaded.stats.runs == 4


def test_record_run_for_unknown_capability_is_an_error(tmp_path: Path) -> None:
    update = ArtifactStore(tmp_path).record_run("coreone.missing", "1.0.0", success())
    assert update.stats is None and update.error


def test_save_failure_is_reported(tmp_path: Path) -> None:
    blocking_file = tmp_path / "root-is-a-file"
    blocking_file.write_text("x", encoding="utf-8")

    written = ArtifactStore(blocking_file).save(balance_capability())

    assert not written.ok and "could not write" in (written.error or "")


def test_updated_replay_stats_from_zero() -> None:
    assert updated_replay_stats(ReplayStats(), success()) == ReplayStats(runs=1, successes=1)


def test_next_minor_bumps_minor_and_resets_patch() -> None:
    from hands.catalog.versions import next_minor

    assert next_minor("1.0.0") == "1.1.0"
    assert next_minor("2.3.4") == "2.4.0"
    assert next_minor("not-a-version") is None
    assert next_minor("") is None
