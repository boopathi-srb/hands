"""Unit tests: run records, states, headlines, and runs read back from disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hands.api.run_records import (
    MAX_HEADLINE_CHARS,
    RunRecord,
    build_headline,
    crashed_record,
    discovery_headline,
    finished_record,
    new_running_record,
    newest_first,
    record_from_run_dir,
    replay_headline,
    scan_run_records,
    summary_with_status,
    truncate,
    utc_now_iso,
    with_live_state,
)


def running(run_id: str = "replay-a", mode: str = "replay") -> RunRecord:
    return new_running_record(run_id, mode, "coreone.member_balance", "lakeside")  # type: ignore[arg-type]


def test_utc_now_iso_is_utc() -> None:
    assert utc_now_iso().endswith("+00:00")


def test_new_running_record() -> None:
    record = running()
    assert record.state == "running" and record.status is None and record.finished_at is None
    assert record.headline == "replaying coreone.member_balance"
    assert new_running_record("disc-a", "discovery", None, None).headline == "discovering"


def test_list_item_has_the_contract_fields() -> None:
    assert set(running().list_item()) == {"run_id", "mode", "state", "status", "capability_id", "tenant",
                                          "started_at", "finished_at", "headline"}


def test_finished_record_from_a_replay_result() -> None:
    summary = {"status": "success", "outputs": {"savings_balance": "9870.12"}, "finished_at": "2026-01-01T00:00:00Z"}
    record = finished_record(running(), summary)
    assert record.state == "finished" and record.status == "success"
    assert record.finished_at == "2026-01-01T00:00:00Z" and record.result == summary
    assert record.headline == "savings_balance 9870.12"


def test_finished_record_from_a_command_error_is_state_error() -> None:
    record = finished_record(running(), {"status": "error", "command": "replay", "message": "no browser"})
    assert record.state == "error" and record.status == "error" and record.headline == "error: no browser"
    assert record.finished_at


def test_discovery_error_status_is_still_a_finished_run() -> None:
    record = finished_record(running("disc-a", "discovery"), {"status": "error", "reason": "planner failed"})
    assert record.state == "finished" and record.headline == "error: planner failed"


def test_crashed_record() -> None:
    record = crashed_record(running(), "RuntimeError('boom')")
    assert record.state == "error" and record.status == "error"
    assert record.headline == "error: RuntimeError('boom')" and record.result == {"status": "error",
                                                                                   "message": "RuntimeError('boom')"}


def test_with_live_state() -> None:
    waiting = with_live_state(running(), "Member identity verification requires a human operator.")
    assert waiting.state == "waiting_for_operator"
    assert waiting.headline.startswith("waiting for operator: Member identity")
    assert with_live_state(running(), None).state == "running"
    finished = finished_record(running(), {"status": "success", "outputs": {}})
    assert with_live_state(finished, "late").state == "finished"


@pytest.mark.parametrize(("summary", "expected"), [
    ({"status": "success", "outputs": {"a": "1", "b": "2"}}, "a 1, b 2"),
    ({"status": "success", "outputs": {}}, "success"),
    ({"status": "business_outcome", "code": "MEMBER_NOT_FOUND"}, "MEMBER_NOT_FOUND"),
    ({"status": "business_outcome"}, "business outcome"),
    ({"status": "escalated", "reason": "identity", "operator_note": "could not verify"}, "escalated: could not verify"),
    ({"status": "escalated", "reason": "identity"}, "escalated: identity"),
    ({"status": "failed", "failure": {"code": "target_not_found", "step_id": "search"}},
     "failed: target_not_found at search"),
    ({"status": "failed", "failure": {"code": "invalid_input", "step_id": None}}, "failed: invalid_input"),
    ({"status": "failed"}, "failed: unknown"),
    ({"status": "weird"}, "weird"),
    ({}, ""),
])
def test_replay_headline(summary: dict[str, Any], expected: str) -> None:
    assert replay_headline(summary) == expected


@pytest.mark.parametrize(("summary", "expected"), [
    ({"status": "completed", "capability": "c.x@1.0.0"}, "recorded c.x@1.0.0"),
    ({"status": "completed", "capability": None, "record_error": "no extract"}, "completed: no extract"),
    ({"status": "stuck", "reason": "no progress"}, "stuck: no progress"),
    ({"status": "budget_exhausted", "reason": ""}, "budget_exhausted"),
    ({}, "unknown"),
])
def test_discovery_headline(summary: dict[str, Any], expected: str) -> None:
    assert discovery_headline(summary) == expected


def test_build_headline_dispatch_and_empty() -> None:
    assert build_headline("replay", None) == "" and build_headline("replay", {}) == ""
    assert build_headline("discovery", {"status": "stuck", "reason": "r"}) == "stuck: r"
    assert len(build_headline("replay", {"status": "success", "outputs": {"x": "y" * 500}})) == MAX_HEADLINE_CHARS


def test_truncate() -> None:
    assert truncate("") == ""
    assert truncate("a\n  b") == "a b"
    assert truncate("x" * MAX_HEADLINE_CHARS) == "x" * MAX_HEADLINE_CHARS
    assert truncate("x" * (MAX_HEADLINE_CHARS + 1)).endswith("…")
    assert len(truncate("x" * 1000, limit=10)) == 10


def write_run(root: Path, run_id: str, file_name: str, payload: Any, first_event_ts: str | None = None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / file_name).write_text(payload if isinstance(payload, str) else json.dumps(payload))
    if first_event_ts:
        (run_dir / "events.jsonl").write_text(json.dumps({"seq": 1, "ts": first_event_ts, "kind": "k"}) + "\n")
    return run_dir


def test_record_from_replay_result(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, "replay-a", "result.json", {
        "status": "business_outcome", "code": "MEMBER_NOT_FOUND", "capability_id": "c.x", "tenant_id": "prairie",
        "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:05Z"})
    record = record_from_run_dir(run_dir)
    assert record is not None and record.mode == "replay" and record.state == "finished"
    assert (record.capability_id, record.tenant, record.headline) == ("c.x", "prairie", "MEMBER_NOT_FOUND")
    assert record.started_at == "2026-01-01T00:00:00Z" and record.finished_at == "2026-01-01T00:00:05Z"


def test_record_from_old_discovery_summary_uses_events_and_mtime(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, "disc-a", "discovery_result.json",
                        {"mode": "discovery", "status": "completed", "capability": "c.x@1.0.0"},
                        first_event_ts="2026-02-02T00:00:00+00:00")
    record = record_from_run_dir(run_dir)
    assert record is not None and record.mode == "discovery"
    assert record.capability_id == "c.x" and record.tenant is None
    assert record.started_at == "2026-02-02T00:00:00+00:00" and record.finished_at


def test_record_from_new_discovery_summary(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path, "disc-b", "discovery_result.json", {
        "status": "stuck", "reason": "r", "capability_id": "c.y", "tenant": "lakeside", "capability": None,
        "started_at": "2026-03-03T00:00:00+00:00", "finished_at": "2026-03-03T00:01:00+00:00"})
    record = record_from_run_dir(run_dir)
    assert record is not None and (record.capability_id, record.tenant) == ("c.y", "lakeside")


@pytest.mark.parametrize("payload", ["{broken", "[1, 2]", '{"no_status": true}', '{"status": 3}'])
def test_unparseable_results_are_ignored(tmp_path: Path, payload: str) -> None:
    assert record_from_run_dir(write_run(tmp_path, "replay-x", "result.json", payload)) is None


def test_run_dir_without_results_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "replay-empty").mkdir()
    assert record_from_run_dir(tmp_path / "replay-empty") is None


def test_summary_with_status(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"status": "x"}')
    (tmp_path / "b.json").write_text('{"status": null}')
    assert summary_with_status(tmp_path / "a.json") == {"status": "x"}
    assert summary_with_status(tmp_path / "b.json") is None
    assert summary_with_status(tmp_path / "absent.json") is None


def test_scan_run_records(tmp_path: Path) -> None:
    write_run(tmp_path, "replay-a", "result.json", {"status": "success", "outputs": {}})
    write_run(tmp_path, "replay-b", "result.json", "{bad")
    (tmp_path / "stray-file.txt").write_text("x")
    assert [record.run_id for record in scan_run_records(tmp_path)] == ["replay-a"]
    assert scan_run_records(tmp_path / "missing") == []


def test_newest_first_handles_bad_and_mixed_timestamps() -> None:
    records = [RunRecord("a", "replay", "2026-01-01T00:00:00Z"), RunRecord("b", "replay", ""),
               RunRecord("c", "replay", "2026-05-01T00:00:00+00:00"), RunRecord("d", "replay", "2026-03-01T00:00:00")]
    assert [record.run_id for record in newest_first(records)] == ["c", "d", "a", "b"]
    assert newest_first([]) == []
