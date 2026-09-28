from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from evidence_helpers import START, login_observation, make_recorder, white_png

from hands.evidence import (
    EVENT_KIND_DESCRIPTIONS,
    STANDARD_EVENT_KINDS,
    EventKind,
    RecordedEvent,
    RecordedFile,
    render_summary,
)
from hands.evidence.summary import (
    MAX_CELL_CHARS,
    action_cell,
    decision_cell,
    escape_cell,
    outcome_cell,
    reason_cell,
    step_cell,
)

# ---------------------------------------------------------------- event kinds


def test_standard_event_kinds() -> None:
    assert STANDARD_EVENT_KINDS == (
        "run_started",
        "observation",
        "decision",
        "policy_decision",
        "action",
        "action_result",
        "recovery_applied",
        "outcome_detected",
        "checkpoint",
        "escalation_raised",
        "control_transferred",
        "human_action",
        "run_finished",
        "error",
    )
    assert set(EVENT_KIND_DESCRIPTIONS) == set(STANDARD_EVENT_KINDS)
    assert EventKind.POLICY_DECISION == "policy_decision"


# ---------------------------------------------------------------- cells


def test_step_cell() -> None:
    assert step_cell({"step_id": "search"}) == "search"
    assert step_cell({"step": "open"}) == "open"
    assert step_cell({}) == ""


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"action": {"kind": "click"}}, "click"),
        ({"action": {"kind": "type", "text": "10001", "clear_first": True}}, "type '10001'"),
        (
            {"action": {"kind": "open", "entry_point": "http://127.0.0.1:8700/t/lakeside"}},
            "open 'http://127.0.0.1:8700/t/lakeside'",
        ),
        ({"action": {"kind": "press", "key": "Enter"}}, "press 'Enter'"),
        ({"action": "click"}, "click"),
        ({"action_kind": "scroll"}, "scroll"),
        ({}, ""),
    ],
)
def test_action_cell(data: dict, expected: str) -> None:  # type: ignore[type-arg]
    assert action_cell(data) == expected


def test_reason_cell_prefers_reason_then_rationale() -> None:
    assert reason_cell({"reason": "r", "rationale": "x"}) == "r"
    assert reason_cell({"rationale": "because"}) == "because"
    assert reason_cell({"reason": ""}) == ""


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"verdict": "deny", "rule": "risk.handling.replay"}, "deny (risk.handling.replay)"),
        ({"verdict": "allow"}, "allow"),
        ({"rule": "x"}, "x"),
        ({"decision": "resume"}, "resume"),
        ({}, ""),
    ],
)
def test_decision_cell(data: dict, expected: str) -> None:  # type: ignore[type-arg]
    assert decision_cell(data) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"status": "success"}, "success"),
        ({"code": "MEMBER_NOT_FOUND"}, "MEMBER_NOT_FOUND"),
        ({"ok": True}, "ok"),
        ({"ok": False, "error": "target not found"}, "failed: target not found"),
        ({"ok": False}, "failed"),
        ({"error": "boom"}, "boom"),
        ({}, ""),
    ],
)
def test_outcome_cell(data: dict, expected: str) -> None:  # type: ignore[type-arg]
    assert outcome_cell(data) == expected


def test_escape_cell() -> None:
    assert escape_cell("a | b\nc") == "a \\| b c"
    assert escape_cell("") == ""
    long_cell = escape_cell("x" * 500)
    assert len(long_cell) == MAX_CELL_CHARS and long_cell.endswith("…")


# ---------------------------------------------------------------- render_summary


def test_render_summary_empty_run() -> None:
    markdown = render_summary("run-empty", [], [])
    assert markdown.startswith("# Run run-empty")
    assert "- Events: 0" in markdown
    assert "_No events recorded._" in markdown
    assert "_No files written._" in markdown


def test_render_summary_timeline() -> None:
    events = [
        RecordedEvent(seq=1, ts=START, kind="run_started", data={"mode": "replay"}),
        RecordedEvent(
            seq=3,
            ts=START + timedelta(seconds=1.5),
            kind="policy_decision",
            data={
                "step_id": "submit",
                "action": {"kind": "click"},
                "verdict": "deny",
                "rule": "risk.handling.replay",
                "reason": "risky | not confirmed",
            },
        ),
        RecordedEvent(
            seq=4, ts=START + timedelta(seconds=2), kind="my_custom", data={"status": "failed"}
        ),
    ]
    files = [RecordedFile(seq=2, category="screenshot", relative_path="screenshots/002-login.png")]
    markdown = render_summary("run-1", events, files)
    assert (
        "| 3 | +1.500s | policy_decision | submit | click | risky \\| not confirmed | deny (risk.handling.replay) |  |"
        in markdown
    )
    assert "- Events: 3 (run_started 1, policy_decision 1, my_custom 1)" in markdown
    assert "- `screenshots/002-login.png` (screenshot, seq 2)" in markdown
    assert "- `my_custom`: custom event kind" in markdown
    assert "- `policy_decision`: policy gate verdict" in markdown


# ---------------------------------------------------------------- recorder.summary


def test_recorder_summary_writes_summary_md(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    recorder.event(EventKind.RUN_STARTED, mode="replay")
    recorder.snapshot("login", login_observation("pw"))
    recorder.screenshot("login", white_png())
    recorder.event(
        EventKind.ACTION,
        step_id="sign_on",
        action={"kind": "click"},
        rationale="submit the login form",
    )
    recorder.event(EventKind.ACTION_RESULT, step_id="sign_on", ok=True)
    recorder.event(EventKind.RUN_FINISHED, status="success")
    assert recorder.summary() == "summary.md"
    markdown = (Path(recorder.run_dir) / "summary.md").read_text(encoding="utf-8")
    assert "# Run run-abc" in markdown
    assert "| sign_on | click | submit the login form |" in markdown
    assert "| run_finished |" in markdown and "success" in markdown
    assert "`snapshots/002-login.json`" in markdown
    assert "`screenshots/003-login.png`" in markdown


def test_recorder_summary_for_an_empty_run(tmp_path: Path) -> None:
    recorder = make_recorder(tmp_path)
    assert recorder.summary() == "summary.md"
    markdown = (Path(recorder.run_dir) / "summary.md").read_text(encoding="utf-8")
    assert "_No events recorded._" in markdown
