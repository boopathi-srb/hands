"""CassettePlanner: record planner responses to JSONL, replay them offline with no network.

Each line is `{"key", "planner", "response"}` where `key` hashes the PlannerContext (goal, inputs,
placeholders, rendered screen, history, extracted values, steps left, feedback). The screenshot is
not part of the key, and clock-like text (times, dates) in the rendered screen is normalized, so a
rerun against the same app state hits the same entries. Identical contexts seen several times are
served in recorded order.

Modes: `record` calls the inner planner and appends (the file is started fresh on the first write),
`replay` only reads the file (a miss is an error response, never a network call), `passthrough`
just delegates.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from hands.core.log import get_logger, log_failure
from hands.discovery.planner import Planner, PlannerContext, PlannerResponse

_logger = get_logger(__name__)

CassetteMode = Literal["record", "replay", "passthrough"]
_VOLATILE_TEXT = (
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\s?([AaPp][Mm])?\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}(T[\d:.+-]+Z?)?\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
)


class CassetteEntry(BaseModel):
    key: str
    planner: str | None = None
    response: PlannerResponse


def context_key(context: PlannerContext) -> str:
    """Stable hash of what the planner saw, ignoring the screenshot and clock-like text."""
    payload = context.model_dump(mode="json")
    payload["observation_text"] = _normalize_volatile(context.observation_text)
    payload["has_screenshot"] = context.screenshot_png is not None
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _normalize_volatile(text: str) -> str:
    for pattern in _VOLATILE_TEXT:
        text = pattern.sub("<volatile>", text)
    return text


class CassettePlanner:
    """Implements the Planner port by recording or replaying another planner's responses."""

    def __init__(self, inner: Planner | None, path: str | Path, mode: CassetteMode) -> None:
        self._inner = inner
        self._path = Path(path)
        self._mode: CassetteMode = mode
        self._entries_by_key: dict[str, list[PlannerResponse]] | None = None
        self._served_by_key: dict[str, int] = {}
        self._started_recording = False
        self.name = getattr(inner, "name", "cassette")
        self.model = getattr(inner, "model", None)
        self.hits = 0
        self.misses = 0

    async def decide(self, context: PlannerContext) -> PlannerResponse:
        if self._mode == "replay":
            return self._replay(context_key(context))
        if self._inner is None:
            log_failure(_logger, "CassettePlanner.decide", "no inner planner", mode=self._mode)
            return PlannerResponse(error=f"cassette mode '{self._mode}' needs an inner planner")
        response = await self._inner.decide(context)
        if self._mode == "record":
            self._append(CassetteEntry(key=context_key(context), planner=self.name, response=response))
        return response

    # ------------------------------------------------------------ replay

    def _replay(self, key: str) -> PlannerResponse:
        entries = self._loaded_entries().get(key)
        if not entries:
            self.misses += 1
            log_failure(_logger, "CassettePlanner._replay", "no recorded response for context",
                        key=key, path=str(self._path))
            return PlannerResponse(error=f"cassette miss: no recorded response for context {key}")
        served = self._served_by_key.get(key, 0)
        self._served_by_key[key] = served + 1
        self.hits += 1
        return entries[min(served, len(entries) - 1)]

    def _loaded_entries(self) -> dict[str, list[PlannerResponse]]:
        if self._entries_by_key is None:
            self._entries_by_key = load_cassette(self._path)
        return self._entries_by_key

    # ------------------------------------------------------------ record

    def _append(self, entry: CassetteEntry) -> None:
        write_mode = "a" if self._started_recording else "w"
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open(write_mode, encoding="utf-8") as cassette_file:
                cassette_file.write(entry.model_dump_json() + "\n")
        except OSError as write_error:
            log_failure(_logger, "CassettePlanner._append", str(write_error), path=str(self._path),
                        key=entry.key)
            return
        self._started_recording = True


def load_cassette(path: str | Path) -> dict[str, list[PlannerResponse]]:
    """Entries grouped by key in file order. A missing file or bad lines are logged, never raised."""
    cassette_path = Path(path)
    try:
        lines = cassette_path.read_text(encoding="utf-8").splitlines()
    except OSError as read_error:
        log_failure(_logger, "load_cassette", str(read_error), path=str(cassette_path))
        return {}
    entries_by_key: dict[str, list[PlannerResponse]] = {}
    for line_number, line in enumerate(lines, start=1):
        entry = _parse_line(line, line_number, cassette_path)
        if entry is not None:
            entries_by_key.setdefault(entry.key, []).append(entry.response)
    return entries_by_key


def _parse_line(line: str, line_number: int, cassette_path: Path) -> CassetteEntry | None:
    if not line.strip():
        return None
    try:
        return CassetteEntry.model_validate_json(line)
    except ValidationError as validation_error:
        log_failure(_logger, "load_cassette", f"invalid entry: {validation_error.error_count()} errors",
                    path=str(cassette_path), line=line_number)
        return None
