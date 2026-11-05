"""Unit tests: reading a run directory (events paging, file index, path safety, JSON and mtimes)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hands.api.run_files import (
    first_event_time,
    is_valid_run_id,
    list_run_files,
    media_type_for,
    modified_time,
    parse_event_line,
    read_events_after,
    read_json_object,
    run_dir_for,
    safe_run_file,
)


def event_line(seq: int, kind: str = "observation") -> str:
    return json.dumps({"seq": seq, "ts": f"2026-01-01T00:00:{seq:02d}+00:00", "kind": kind, "data": {"n": seq}})


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "replay-abc"
    (directory / "screenshots").mkdir(parents=True)
    (directory / "snapshots").mkdir()
    (directory / "events.jsonl").write_text("\n".join([event_line(1), "garbage", event_line(3), event_line(5)]) + "\n")
    (directory / "screenshots" / "004-x.png").write_bytes(b"\x89PNG")
    (directory / "screenshots" / "002-a.png").write_bytes(b"\x89PNG")
    (directory / "screenshots" / "notes.txt").write_text("not listed")
    (directory / "snapshots" / "003-obs.json").write_text("{}")
    (directory / "result.json").write_text('{"status": "success"}')
    (directory / "summary.md").write_text("# summary")
    return directory


@pytest.mark.parametrize(("run_id", "expected"), [("replay-ab12", True), ("disc-1.2_3", True), ("", False),
                                                  ("../x", False), ("-x", False), ("a/b", False)])
def test_is_valid_run_id(run_id: str, expected: bool) -> None:
    assert is_valid_run_id(run_id) is expected


def test_run_dir_for(run_dir: Path) -> None:
    assert run_dir_for(run_dir.parent, "replay-abc") == run_dir
    assert run_dir_for(run_dir.parent, "replay-missing") is None
    assert run_dir_for(run_dir.parent, "..") is None


def test_read_events_after_pages_and_skips_garbage(run_dir: Path) -> None:
    everything = read_events_after(run_dir, 0)
    later = read_events_after(run_dir, 3)
    none_left = read_events_after(run_dir, 5)

    assert [event["seq"] for event in everything.events] == [1, 3, 5] and everything.last_seq == 5
    assert [event["seq"] for event in later.events] == [5]
    assert none_left.events == [] and none_left.last_seq == 5


def test_read_events_on_missing_or_empty_file(tmp_path: Path) -> None:
    assert read_events_after(tmp_path, 7).events == [] and read_events_after(tmp_path, 7).last_seq == 7
    (tmp_path / "events.jsonl").write_text("")
    assert read_events_after(tmp_path, 0).last_seq == 0


@pytest.mark.parametrize("line", ["", "   ", "{", "[1]", '{"seq": "1"}', '{"kind": "x"}'])
def test_parse_event_line_rejects_non_events(line: str) -> None:
    assert parse_event_line(line) is None


def test_parse_event_line_keeps_the_four_fields() -> None:
    parsed = parse_event_line('{"seq": 2, "ts": "t", "kind": "k", "data": {"a": 1}, "extra": true}')
    assert parsed == {"seq": 2, "ts": "t", "kind": "k", "data": {"a": 1}}
    assert parse_event_line('{"seq": 2}') == {"seq": 2, "ts": None, "kind": None, "data": {}}


def test_first_event_time(run_dir: Path, tmp_path: Path) -> None:
    assert first_event_time(run_dir) == "2026-01-01T00:00:01+00:00"
    assert first_event_time(tmp_path) is None


def test_list_run_files_sorted_and_filtered(run_dir: Path, tmp_path: Path) -> None:
    assert list_run_files(run_dir) == {"screenshots": ["screenshots/002-a.png", "screenshots/004-x.png"],
                                       "snapshots": ["snapshots/003-obs.json"]}
    assert list_run_files(tmp_path / "nothing") == {"screenshots": [], "snapshots": []}


def test_safe_run_file_allows_png_and_json_inside(run_dir: Path) -> None:
    assert safe_run_file(run_dir, "screenshots/002-a.png") == (run_dir / "screenshots" / "002-a.png").resolve()
    assert safe_run_file(run_dir, "result.json") == (run_dir / "result.json").resolve()


@pytest.mark.parametrize("bad_path", ["summary.md", "events.jsonl", "../replay-abc/result.json/../../x.json",
                                      "../../etc/passwd", "/etc/hosts", "screenshots/missing.png", "",
                                      "screenshots/notes.txt"])
def test_safe_run_file_refuses(run_dir: Path, bad_path: str) -> None:
    assert safe_run_file(run_dir, bad_path) is None


def test_safe_run_file_refuses_a_sibling_run(run_dir: Path) -> None:
    sibling = run_dir.parent / "replay-abc2"
    sibling.mkdir()
    (sibling / "result.json").write_text("{}")
    assert safe_run_file(run_dir, "../replay-abc2/result.json") is None


def test_media_type_for() -> None:
    assert media_type_for(Path("a.png")) == "image/png"
    assert media_type_for(Path("a.json")) == "application/json"
    assert media_type_for(Path("a.md")) == "application/octet-stream"


def test_read_json_object(tmp_path: Path) -> None:
    (tmp_path / "ok.json").write_text('{"a": 1}')
    (tmp_path / "list.json").write_text("[1]")
    (tmp_path / "bad.json").write_text("{nope")
    assert read_json_object(tmp_path / "ok.json") == {"a": 1}
    assert read_json_object(tmp_path / "list.json") is None
    assert read_json_object(tmp_path / "bad.json") is None
    assert read_json_object(tmp_path / "absent.json") is None


def test_modified_time(run_dir: Path, tmp_path: Path) -> None:
    stamp = modified_time(run_dir / "result.json")
    assert stamp is not None and stamp.endswith("+00:00")
    assert modified_time(tmp_path / "absent.json") is None
