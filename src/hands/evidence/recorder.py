"""EvidenceRecorder: the EvidenceSink that writes a run's evidence directory, redacting everything first.

Layout of `<root>/<run_id>/`::

    events.jsonl                  one JSON object per line: {"seq", "ts", "kind", "data"} (data redacted)
    screenshots/NNN-<name>.png    masked screenshots
    snapshots/NNN-<name>.json     redacted Observation JSON (the screenshot is never serialized)
    <name>.json                   write_json payloads, e.g. result.json, capability.json (redacted)
    summary.md                    reviewer timeline, written by summary()

`seq` is one monotonic counter shared by events and numbered files, so NNN orders files among events.
Every byte written goes through the Redactor: event data, file names, snapshots, JSON payloads and screenshots.
Write failures are logged with context and counted (`write_failures`); the file-returning methods then return
an empty string instead of a path.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.evidence.summary import FileCategory, RecordedEvent, RecordedFile, render_summary
from hands.redact import Redactor

EVENTS_FILE = "events.jsonl"
SCREENSHOTS_DIR = "screenshots"
SNAPSHOTS_DIR = "snapshots"
SUMMARY_FILE = "summary.md"
MAX_NAME_CHARS = 60
UNNAMED = "unnamed"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_NAME_UNSAFE = re.compile(r"[^a-z0-9_.-]+")

Clock = Callable[[], datetime]
_logger = get_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RecorderReady:
    recorder: EvidenceRecorder
    ok: Literal[True] = True


@dataclass(frozen=True)
class RecorderCreateFailed:
    message: str
    run_dir: str
    ok: Literal[False] = False


RecorderCreateResult = RecorderReady | RecorderCreateFailed


def safe_file_stem(name: str) -> str:
    """Lowercase, filesystem-safe stem: no separators, no traversal, bounded length."""
    stem = _NAME_UNSAFE.sub("-", name.strip().lower()).strip("-.")[:MAX_NAME_CHARS].strip("-.")
    return stem or UNNAMED


def json_relative_path(name: str) -> str:
    """'result' -> 'result.json'; 'artifacts/Capability' -> 'artifacts/capability.json'."""
    segments = [safe_file_stem(segment) for segment in name.split("/") if segment.strip(" .")]
    segments = segments or [UNNAMED]
    if not segments[-1].endswith(".json"):
        segments[-1] = f"{segments[-1]}.json"
    return "/".join(segments)


class EvidenceRecorder:
    """Append-only evidence for one run. Create it with `EvidenceRecorder.create(...)`."""

    def __init__(
        self, run_dir: Path, run_id: str, redactor: Redactor, clock: Clock, screenshot_scale: float
    ) -> None:
        self._run_dir = run_dir
        self._run_id = run_id
        self._redactor = redactor
        self._clock = clock
        self._screenshot_scale = screenshot_scale
        self._lock = threading.Lock()
        self._last_seq = 0
        self._events: list[RecordedEvent] = []
        self._files: list[RecordedFile] = []
        self._last_observation: Observation | None = None
        self._write_failures = 0

    @classmethod
    def create(
        cls,
        root_dir: str | Path,
        run_id: str,
        redactor: Redactor,
        *,
        clock: Clock = utc_now,
        screenshot_scale: float = 1.0,
    ) -> RecorderCreateResult:
        """Make `<root_dir>/<run_id>/` (must be new or empty). `screenshot_scale` = image px per CSS px."""
        run_dir = Path(root_dir) / run_id
        if RUN_ID_PATTERN.fullmatch(run_id) is None:
            return _create_failed(f"run id '{run_id}' is not a safe directory name", run_dir)
        preparation_error = _prepare_run_dir(run_dir)
        if preparation_error is not None:
            return _create_failed(preparation_error, run_dir)
        return RecorderReady(recorder=cls(run_dir, run_id, redactor, clock, screenshot_scale))

    # ------------------------------------------------------------ properties

    @property
    def run_dir(self) -> str:
        return str(self._run_dir)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def redactor(self) -> Redactor:
        return self._redactor

    @property
    def events(self) -> list[RecordedEvent]:
        with self._lock:
            return list(self._events)

    @property
    def files(self) -> list[RecordedFile]:
        with self._lock:
            return list(self._files)

    @property
    def write_failures(self) -> int:
        return self._write_failures

    # ------------------------------------------------------------ EvidenceSink

    def event(self, kind: str, **data: Any) -> None:
        redacted_kind = self._redactor.redact_text(str(kind))
        redacted_data = self._redactor.redact_value(data)
        with self._lock:
            recorded = RecordedEvent(
                seq=self._next_seq(), ts=self._clock(), kind=redacted_kind, data=redacted_data
            )
            self._events.append(recorded)
            self._append_text(EVENTS_FILE, _event_line(recorded))

    def screenshot(self, name: str, png: bytes, observation: Observation | None = None) -> str:
        """Write a masked screenshot. Masks using `observation`, else the last snapshot's observation.

        Limit: with no observation at all nothing can be located, so the image is written unmasked; always
        snapshot (or pass `observation`) before capturing screens that may show sensitive data.
        """
        mask_source = observation or self._last_observation
        masked_png = (
            self._redactor.mask_screenshot(png, mask_source, scale=self._screenshot_scale)
            if mask_source is not None
            else png
        )
        return self._write_numbered(SCREENSHOTS_DIR, name, ".png", masked_png, "screenshot")

    def snapshot(self, name: str, observation: Observation) -> str:
        """Write the redacted observation (without screenshot); remember it for masking later screenshots."""
        self._last_observation = observation
        without_screenshot = observation.model_copy(update={"screenshot_png": None})
        redacted = self._redactor.redact_observation(without_screenshot)
        content = redacted.model_dump_json(indent=2).encode("utf-8")
        return self._write_numbered(SNAPSHOTS_DIR, name, ".json", content, "snapshot")

    def write_json(self, name: str, payload: BaseModel | dict[str, Any]) -> str:
        """Write a redacted JSON document at the run root (e.g. 'result' -> result.json). Last write wins."""
        relative_path = json_relative_path(self._redactor.redact_text(name))
        content = _json_bytes(self._redactor.redact_value(payload))
        with self._lock:
            seq = self._next_seq()
            return self._write_file(relative_path, content, seq, "json")

    def summary(self) -> str:
        """Render and write summary.md from the (already redacted) records. Returns its relative path."""
        with self._lock:
            markdown = render_summary(self._run_id, list(self._events), list(self._files))
            written = self._write_bytes(SUMMARY_FILE, markdown.encode("utf-8"))
        return SUMMARY_FILE if written else ""

    # ------------------------------------------------------------ internals (call with the lock held)

    def _next_seq(self) -> int:
        self._last_seq += 1
        return self._last_seq

    def _write_numbered(
        self, directory: str, name: str, suffix: str, content: bytes, category: FileCategory
    ) -> str:
        stem = safe_file_stem(self._redactor.redact_text(name))
        with self._lock:
            seq = self._next_seq()
            relative_path = f"{directory}/{seq:03d}-{stem}{suffix}"
            return self._write_file(relative_path, content, seq, category)

    def _write_file(
        self, relative_path: str, content: bytes, seq: int, category: FileCategory
    ) -> str:
        if not self._write_bytes(relative_path, content):
            return ""
        self._files.append(RecordedFile(seq=seq, category=category, relative_path=relative_path))
        return relative_path

    def _write_bytes(self, relative_path: str, content: bytes) -> bool:
        target = self._run_dir / relative_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        except OSError as write_error:
            return self._record_write_failure("_write_bytes", relative_path, write_error)
        return True

    def _append_text(self, relative_path: str, line: str) -> bool:
        try:
            with (self._run_dir / relative_path).open("a", encoding="utf-8") as events_file:
                events_file.write(line)
        except OSError as write_error:
            return self._record_write_failure("_append_text", relative_path, write_error)
        return True

    def _record_write_failure(self, function_name: str, relative_path: str, error: OSError) -> bool:
        self._write_failures += 1
        log_failure(
            _logger,
            function_name,
            f"cannot write evidence: {error}",
            run_id=self._run_id,
            path=relative_path,
        )
        return False


def _prepare_run_dir(run_dir: Path) -> str | None:
    """Create the run directory tree; return an error message, or None on success."""
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        if any(run_dir.iterdir()):
            return f"run directory {run_dir} already exists and is not empty"
        (run_dir / SCREENSHOTS_DIR).mkdir()
        (run_dir / SNAPSHOTS_DIR).mkdir()
        (run_dir / EVENTS_FILE).touch()
    except OSError as os_error:
        return f"cannot create run directory: {os_error}"
    return None


def _create_failed(message: str, run_dir: Path) -> RecorderCreateFailed:
    log_failure(_logger, "EvidenceRecorder.create", message, run_dir=str(run_dir))
    return RecorderCreateFailed(message=message, run_dir=str(run_dir))


def _event_line(recorded: RecordedEvent) -> str:
    record = {
        "seq": recorded.seq,
        "ts": recorded.ts.isoformat(),
        "kind": recorded.kind,
        "data": recorded.data,
    }
    return json.dumps(record, ensure_ascii=False) + "\n"


def _json_bytes(redacted_payload: Any) -> bytes:
    return (json.dumps(redacted_payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
