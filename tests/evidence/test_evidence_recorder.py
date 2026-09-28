from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from evidence_helpers import (
    black_pixel_count,
    login_observation,
    make_recorder,
    read_events,
    stepping_clock,
    white_png,
)
from pydantic import BaseModel

from hands.core.ports import EvidenceSink
from hands.evidence import EventKind, EvidenceRecorder, RecorderCreateFailed, RecorderReady
from hands.evidence.recorder import json_relative_path, safe_file_stem
from hands.redact import Redactor

# ---------------------------------------------------------------- create and layout


def test_create_makes_the_run_directory_layout(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path, run_id="run-001")
    run_dir = Path(recorder.run_dir)
    assert run_dir == tmp_path / "run-001"
    assert (run_dir / "events.jsonl").is_file()
    assert (run_dir / "screenshots").is_dir()
    assert (run_dir / "snapshots").is_dir()
    assert recorder.run_id == "run-001"
    assert recorder.events == [] and recorder.files == []


def test_recorder_satisfies_the_core_port(tmp_path: Path) -> None:
    sink: EvidenceSink = make_recorder(tmp_path)
    sink.event(EventKind.RUN_STARTED, mode="replay")
    assert sink.run_dir.endswith("run-abc")


@pytest.mark.parametrize("run_id", ["", "../escape", "a/b", ".hidden", "with space", "x" * 200])
def test_create_rejects_unsafe_run_ids(tmp_path: Path, run_id: str) -> None:
    result = EvidenceRecorder.create(tmp_path, run_id, Redactor())
    assert isinstance(result, RecorderCreateFailed)
    assert result.ok is False
    assert "not a safe directory name" in result.message


def test_create_refuses_a_non_empty_existing_run_dir(tmp_path: Path) -> None:
    (tmp_path / "run-abc").mkdir()
    (tmp_path / "run-abc" / "events.jsonl").write_text("{}\n", encoding="utf-8")
    result = EvidenceRecorder.create(tmp_path, "run-abc", Redactor())
    assert isinstance(result, RecorderCreateFailed) and "not empty" in result.message


def test_create_accepts_an_empty_existing_run_dir(tmp_path: Path) -> None:
    (tmp_path / "run-abc").mkdir()
    assert isinstance(EvidenceRecorder.create(tmp_path, "run-abc", Redactor()), RecorderReady)


def test_create_reports_io_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    blocking_file = tmp_path / "root"
    blocking_file.write_text("not a directory", encoding="utf-8")
    result = EvidenceRecorder.create(blocking_file, "run-abc", Redactor())
    assert isinstance(result, RecorderCreateFailed)
    assert "cannot create run directory" in result.message
    assert "EvidenceRecorder.create failed" in caplog.text


# ---------------------------------------------------------------- events and sequencing


def test_event_writes_one_json_line_per_event(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.event(EventKind.RUN_STARTED, mode="replay", capability_id="lookup_member")
    recorder.event("custom_kind", note="free form")
    lines = read_events(recorder)
    assert [line["seq"] for line in lines] == [1, 2]
    assert [line["kind"] for line in lines] == ["run_started", "custom_kind"]
    assert lines[0]["data"] == {"mode": "replay", "capability_id": "lookup_member"}
    assert lines[0]["ts"] == "2026-09-28T12:00:00+00:00"
    assert lines[1]["ts"] == "2026-09-28T12:00:00.250000+00:00"
    assert set(lines[0]) == {"seq", "ts", "kind", "data"}


def test_event_with_no_data(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.event(EventKind.RUN_FINISHED)
    assert read_events(recorder)[0]["data"] == {}


def test_sequence_is_shared_by_events_and_numbered_files(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.event(EventKind.RUN_STARTED)
    snapshot_path = recorder.snapshot("login", login_observation("pw"))
    screenshot_path = recorder.screenshot("login", white_png())
    recorder.event(EventKind.RUN_FINISHED)
    assert snapshot_path == "snapshots/002-login.json"
    assert screenshot_path == "screenshots/003-login.png"
    assert [line["seq"] for line in read_events(recorder)] == [1, 4]
    assert [recorded.seq for recorded in recorder.files] == [2, 3]


def test_sequence_is_thread_safe(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)

    def emit_events() -> None:
        for index in range(50):
            recorder.event(EventKind.ACTION, index=index)

    threads = [threading.Thread(target=emit_events) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    seqs = [line["seq"] for line in read_events(recorder)]
    assert sorted(seqs) == list(range(1, 401))
    assert seqs == sorted(seqs)


def test_events_property_returns_a_copy(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.event(EventKind.ERROR, where="x")
    recorder.events.clear()
    assert len(recorder.events) == 1


# ---------------------------------------------------------------- files


def test_snapshot_is_redacted_json_without_screenshot(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    relative_path = recorder.snapshot(
        "login page", login_observation("hunter2", screenshot_png=white_png())
    )
    content = json.loads((Path(recorder.run_dir) / relative_path).read_text(encoding="utf-8"))
    assert relative_path == "snapshots/001-login-page.json"
    assert "screenshot_png" not in content
    password_node = next(node for node in content["nodes"] if node["name"] == "Password")
    assert password_node["value"] == "[REDACTED:password]"
    assert content["fingerprint"] == "fp-login"


def test_screenshot_is_masked_with_the_last_snapshot(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.snapshot("login", login_observation("pw"))
    relative_path = recorder.screenshot("login", white_png())
    written = (Path(recorder.run_dir) / relative_path).read_bytes()
    assert black_pixel_count(written) > 0


def test_screenshot_prefers_an_explicit_observation(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    relative_path = recorder.screenshot("login", white_png(), observation=login_observation("pw"))
    assert black_pixel_count((Path(recorder.run_dir) / relative_path).read_bytes()) > 0


def test_screenshot_without_any_observation_is_written_as_is(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    png = white_png()
    relative_path = recorder.screenshot("start", png)
    assert (Path(recorder.run_dir) / relative_path).read_bytes() == png


def test_screenshot_scale_is_applied(tmp_path: Path) -> None:
    result = EvidenceRecorder.create(tmp_path, "scaled", Redactor(), screenshot_scale=2.0)
    assert isinstance(result, RecorderReady)
    recorder = result.recorder
    relative_path = recorder.screenshot(
        "x", white_png(120, 80), observation=login_observation("pw")
    )
    unscaled = make_recorder(tmp_path, run_id="unscaled").screenshot(
        "x", white_png(120, 80), observation=login_observation("pw")
    )
    scaled_black = black_pixel_count((Path(recorder.run_dir) / relative_path).read_bytes())
    unscaled_black = black_pixel_count((tmp_path / "unscaled" / unscaled).read_bytes())
    assert scaled_black > unscaled_black


class ResultPayload(BaseModel):
    status: str
    note: str


def test_write_json_accepts_models_and_dicts(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    result_path = recorder.write_json(
        "result", ResultPayload(status="success", note="SSN 123-45-6789")
    )
    artifact_path = recorder.write_json("artifacts/Capability.json", {"id": "lookup_member"})
    run_dir = Path(recorder.run_dir)
    assert result_path == "result.json"
    assert artifact_path == "artifacts/capability.json"
    assert json.loads((run_dir / result_path).read_text(encoding="utf-8")) == {
        "status": "success",
        "note": "SSN [REDACTED:ssn]",
    }
    assert json.loads((run_dir / artifact_path).read_text(encoding="utf-8")) == {
        "id": "lookup_member"
    }


def test_write_json_last_write_wins(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.write_json("result", {"attempt": 1})
    recorder.write_json("result", {"attempt": 2})
    assert json.loads((Path(recorder.run_dir) / "result.json").read_text(encoding="utf-8")) == {
        "attempt": 2
    }


def test_write_failures_are_logged_counted_and_return_empty_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    recorder = make_recorder(tmp_path)

    def refuse(self: Path, content: bytes) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", refuse)
    assert recorder.write_json("result", {"a": 1}) == ""
    assert recorder.screenshot("x", white_png()) == ""
    assert recorder.summary() == ""
    assert recorder.write_failures == 3
    assert recorder.files == []
    assert "cannot write evidence: disk full" in caplog.text


def test_event_write_failure_is_logged_and_counted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    recorder = make_recorder(tmp_path)
    events_file = Path(recorder.run_dir) / "events.jsonl"
    events_file.unlink()
    events_file.mkdir()
    recorder.event(EventKind.ERROR, where="test")
    assert recorder.write_failures == 1
    assert len(recorder.events) == 1
    assert "_append_text failed" in caplog.text


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Login Page", "login-page"),
        ("../../etc/passwd", "etc-passwd"),
        ("", "unnamed"),
        ("...", "unnamed"),
        ("step_03.after", "step_03.after"),
        ("x" * 100, "x" * 60),
        ("[REDACTED:ssn]", "redacted-ssn"),
    ],
)
def test_safe_file_stem(name: str, expected: str) -> None:
    assert safe_file_stem(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("result", "result.json"),
        ("result.json", "result.json"),
        ("artifacts/Capability", "artifacts/capability.json"),
        ("../../outside", "outside.json"),
        ("", "unnamed.json"),
    ],
)
def test_json_relative_path(name: str, expected: str) -> None:
    assert json_relative_path(name) == expected


def test_file_names_are_redacted(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    relative_path = recorder.snapshot("member 123-45-6789", login_observation("pw"))
    assert "6789" not in relative_path
    assert relative_path == "snapshots/001-member-redacted-ssn.json"


def test_clock_defaults_to_utc_now(tmp_path: Path) -> None:
    result = EvidenceRecorder.create(tmp_path, "real-clock", Redactor())
    assert isinstance(result, RecorderReady)
    result.recorder.event(EventKind.RUN_STARTED)
    assert read_events(result.recorder)[0]["ts"].endswith("+00:00")


def test_stepping_clock_helper_is_monotonic() -> None:
    clock = stepping_clock(10)
    assert clock() < clock()
