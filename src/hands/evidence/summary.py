"""Render `summary.md`: a reviewer-facing timeline of a run. Pure: works on already-redacted records."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from hands.evidence.events import EVENT_KIND_DESCRIPTIONS

FileCategory = Literal["screenshot", "snapshot", "json"]
MAX_CELL_CHARS = 140
EMPTY_CELL = ""


@dataclass(frozen=True)
class RecordedEvent:
    seq: int
    ts: datetime
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True)
class RecordedFile:
    seq: int
    category: FileCategory
    relative_path: str


def render_summary(run_id: str, events: list[RecordedEvent], files: list[RecordedFile]) -> str:
    sections = [
        f"# Run {run_id}",
        _render_overview(events, files),
        "## Timeline",
        _render_timeline(events),
        "## Files",
        _render_files(files),
        "## Event kinds",
        _render_legend(events),
    ]
    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------- sections


def _render_overview(events: list[RecordedEvent], files: list[RecordedFile]) -> str:
    if not events:
        return "- Events: 0"
    kind_counts = Counter(event.kind for event in events)
    counts_text = ", ".join(f"{kind} {count}" for kind, count in kind_counts.items())
    file_counts = Counter(recorded_file.category for recorded_file in files)
    files_text = (
        ", ".join(f"{category} {count}" for category, count in file_counts.items()) or "none"
    )
    return "\n".join(
        [
            f"- Started: {events[0].ts.isoformat()}",
            f"- Last event: {events[-1].ts.isoformat()}",
            f"- Events: {len(events)} ({counts_text})",
            f"- Files: {files_text}",
        ]
    )


def _render_timeline(events: list[RecordedEvent]) -> str:
    if not events:
        return "_No events recorded._"
    header = "| Seq | +Time | Event | Step | Action | Reason | Decision | Outcome |"
    divider = "|---:|---:|---|---|---|---|---|---|"
    started_at = events[0].ts
    rows = [_render_row(event, started_at) for event in events]
    return "\n".join([header, divider, *rows])


def _render_row(event: RecordedEvent, started_at: datetime) -> str:
    elapsed_seconds = (event.ts - started_at).total_seconds()
    cells = [
        str(event.seq),
        f"+{elapsed_seconds:.3f}s",
        event.kind,
        step_cell(event.data),
        action_cell(event.data),
        reason_cell(event.data),
        decision_cell(event.data),
        outcome_cell(event.data),
    ]
    return "| " + " | ".join(escape_cell(cell) for cell in cells) + " |"


def _render_files(files: list[RecordedFile]) -> str:
    if not files:
        return "_No files written._"
    return "\n".join(
        f"- `{recorded_file.relative_path}` ({recorded_file.category}, seq {recorded_file.seq})"
        for recorded_file in files
    )


def _render_legend(events: list[RecordedEvent]) -> str:
    kinds_seen = list(dict.fromkeys(event.kind for event in events))
    if not kinds_seen:
        return "_None._"
    return "\n".join(
        f"- `{kind}`: {EVENT_KIND_DESCRIPTIONS.get(kind, 'custom event kind')}"
        for kind in kinds_seen
    )


# ---------------------------------------------------------------- cells


def step_cell(data: dict[str, Any]) -> str:
    return _first_text(data, "step_id", "step")


def action_cell(data: dict[str, Any]) -> str:
    action = data.get("action")
    if isinstance(action, dict):
        return _describe_action(action)
    return _text(action) if action is not None else _first_text(data, "action_kind")


def reason_cell(data: dict[str, Any]) -> str:
    return _first_text(data, "reason", "rationale", "message", "note")


def decision_cell(data: dict[str, Any]) -> str:
    verdict = _first_text(data, "verdict", "decision")
    rule = _first_text(data, "rule")
    return f"{verdict} ({rule})" if verdict and rule else verdict or rule


def outcome_cell(data: dict[str, Any]) -> str:
    outcome = _first_text(data, "outcome", "status", "code")
    if outcome:
        return outcome
    if "ok" not in data:
        return _first_text(data, "error")
    if data["ok"] is True:
        return "ok"
    error = _first_text(data, "error")
    return f"failed: {error}" if error else "failed"


def escape_cell(text: str) -> str:
    single_line = " ".join(text.split())
    truncated = (
        single_line
        if len(single_line) <= MAX_CELL_CHARS
        else single_line[: MAX_CELL_CHARS - 1] + "…"
    )
    return truncated.replace("|", "\\|")


def _describe_action(action: dict[str, Any]) -> str:
    kind = _text(action.get("kind", "?"))
    argument_keys = ("entry_point", "key", "option", "text", "direction")
    argument = next(
        (_text(action[key]) for key in argument_keys if action.get(key) not in (None, "")), ""
    )
    return f"{kind} '{argument}'" if argument else kind


def _first_text(data: dict[str, Any], *keys: str) -> str:
    return next((_text(data[key]) for key in keys if data.get(key) not in (None, "")), EMPTY_CELL)


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={_text(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value)
    return str(value)
