"""Reading one run's evidence directory: events after a seq, the file index, and path-safe file lookup.

Only the evidence recorder writes these directories, and everything in them is already redacted.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hands.core.log import get_logger, log_failure
from hands.evidence.recorder import EVENTS_FILE, RUN_ID_PATTERN, SCREENSHOTS_DIR, SNAPSHOTS_DIR

_logger: logging.Logger = get_logger(__name__)

SERVABLE_SUFFIXES = {".png": "image/png", ".json": "application/json"}


def is_valid_run_id(run_id: str) -> bool:
    return RUN_ID_PATTERN.fullmatch(run_id) is not None


def run_dir_for(evidence_root: Path, run_id: str) -> Path | None:
    """The run's directory when the id is safe and the directory exists, else None."""
    if not is_valid_run_id(run_id):
        return None
    run_dir = evidence_root / run_id
    return run_dir if run_dir.is_dir() else None


@dataclass(frozen=True)
class EventPage:
    events: list[dict[str, Any]] = field(default_factory=list)
    last_seq: int = 0


def read_events_after(run_dir: Path, after: int) -> EventPage:
    """Events with seq > after, in file order. `last_seq` is the highest seq returned (or `after`)."""
    lines = _read_lines(run_dir / EVENTS_FILE)
    events = [event for event in _parse_event_lines(lines, run_dir) if event["seq"] > after]
    last_seq = max((event["seq"] for event in events), default=after)
    return EventPage(events=events, last_seq=last_seq)


def first_event_time(run_dir: Path) -> str | None:
    """`ts` of the first event, the best start time for runs whose result has none."""
    for event in _parse_event_lines(_read_lines(run_dir / EVENTS_FILE)[:1], run_dir):
        return str(event.get("ts")) if event.get("ts") else None
    return None


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:  # file I/O boundary
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as read_error:
        log_failure(_logger, "_read_lines", repr(read_error), path=str(path))
        return []


def _parse_event_lines(lines: list[str], run_dir: Path) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        event = parse_event_line(line)
        if event is not None:
            parsed.append(event)
        elif line.strip() and index < len(lines) - 1:  # a torn last line is a write in progress
            _logger.warning("skipping unparseable event line %s in %s", index + 1, run_dir)
    return parsed


def parse_event_line(line: str) -> dict[str, Any] | None:
    """One events.jsonl line as {seq, ts, kind, data}, or None when it is not a valid event."""
    if not line.strip():
        return None
    try:  # untrusted file content boundary
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or not isinstance(event.get("seq"), int):
        return None
    return {"seq": event["seq"], "ts": event.get("ts"), "kind": event.get("kind"), "data": event.get("data", {})}


def list_run_files(run_dir: Path) -> dict[str, list[str]]:
    """Relative paths of screenshots and snapshots, in seq order (their names start with the seq)."""
    return {
        "screenshots": _relative_files(run_dir, SCREENSHOTS_DIR, ".png"),
        "snapshots": _relative_files(run_dir, SNAPSHOTS_DIR, ".json"),
    }


def _relative_files(run_dir: Path, directory: str, suffix: str) -> list[str]:
    folder = run_dir / directory
    if not folder.is_dir():
        return []
    return sorted(f"{directory}/{path.name}" for path in folder.iterdir() if path.suffix == suffix)


def safe_run_file(run_dir: Path, relative_path: str) -> Path | None:
    """The file when it stays inside the run dir, is a png or json, and exists; else None (logged)."""
    candidate = (run_dir / relative_path).resolve()
    inside = candidate.is_relative_to(run_dir.resolve())
    if not inside or candidate.suffix not in SERVABLE_SUFFIXES or not candidate.is_file():
        log_failure(_logger, "safe_run_file", "file refused", run_dir=str(run_dir), path=relative_path)
        return None
    return candidate


def media_type_for(path: Path) -> str:
    return SERVABLE_SUFFIXES.get(path.suffix, "application/octet-stream")


def read_json_object(path: Path) -> dict[str, Any] | None:
    """A JSON object from disk; None when absent. Unparseable files are logged as warnings and skipped."""
    if not path.is_file():
        return None
    try:  # file I/O and untrusted content boundary
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as read_error:
        _logger.warning("ignoring unparseable %s: %s", path, read_error)
        return None
    if not isinstance(document, dict):
        _logger.warning("ignoring %s: not a JSON object", path)
        return None
    return document


def modified_time(path: Path) -> str | None:
    """File mtime as ISO 8601 UTC, or None when it cannot be read."""
    try:  # file I/O boundary
        timestamp = path.stat().st_mtime
    except OSError as stat_error:
        log_failure(_logger, "modified_time", repr(stat_error), path=str(path))
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat()
