"""RunManager: starts discovery and replay runs as background tasks, one at a time, and answers run queries.

- One active run (one Chromium): a second start while one runs is refused as `busy`.
- Each run is an asyncio task on the server's loop running the same runtime command the CLI uses, with a
  pre-generated run id and the process-wide SharedConsole, so its interventions show up at /console.
- State: `running` until the command returns, `waiting_for_operator` while the shared board holds an open
  intervention for that session, `finished` once a result exists, `error` if the command could not run or
  the task crashed. A crashed task is logged and always releases the run slot.
- Listing merges this process's runs with finished runs found on disk under the evidence root.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hands.api.models import DiscoveryStartBody, ReplayStartBody
from hands.api.run_files import (
    EventPage,
    list_run_files,
    read_events_after,
    run_dir_for,
    safe_run_file,
)
from hands.api.run_records import (
    RunMode,
    RunRecord,
    crashed_record,
    finished_record,
    new_running_record,
    newest_first,
    record_from_run_dir,
    scan_run_records,
    with_live_state,
)
from hands.api.run_requests import discover_request, replay_request
from hands.api.settings import ApiSettings
from hands.api.validation import ApiError
from hands.console.context import lease_view
from hands.core.log import get_logger, log_failure
from hands.runtime.commands import (
    CommandOutcome,
    DiscoverRequest,
    ReplayRequest,
    run_discover,
    run_replay,
)
from hands.runtime.run_ids import new_run_id
from hands.runtime.shared_console import SharedConsole

_logger: logging.Logger = get_logger(__name__)

ReplayRunner = Callable[[ReplayRequest], Awaitable[CommandOutcome]]
DiscoverRunner = Callable[[DiscoverRequest], Awaitable[CommandOutcome]]
RUN_ID_PREFIXES: dict[RunMode, str] = {"replay": "replay", "discovery": "disc"}


@dataclass(frozen=True)
class RunRunners:
    """The command functions a run executes; tests swap in failing or slow ones."""

    replay: ReplayRunner = run_replay
    discover: DiscoverRunner = run_discover


@dataclass(frozen=True)
class RunStarted:
    run_id: str


class RunManager:
    def __init__(
        self, settings: ApiSettings, shared_console: SharedConsole, runners: RunRunners | None = None
    ) -> None:
        self._settings = settings
        self._shared_console = shared_console
        self._runners = runners or RunRunners()
        self._records: dict[str, RunRecord] = {}
        self._active_run_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None

    @property
    def active_run_id(self) -> str | None:
        return self._active_run_id

    # ------------------------------------------------------------ starting runs

    def start_replay(self, body: ReplayStartBody) -> RunStarted | ApiError:
        run_id = new_run_id(RUN_ID_PREFIXES["replay"])
        request = replay_request(body, self._settings, run_id, self._shared_console)
        record = new_running_record(run_id, "replay", body.capability_id, body.tenant)
        return self._start(record, lambda: self._runners.replay(request))

    def start_discovery(self, body: DiscoveryStartBody) -> RunStarted | ApiError:
        run_id = new_run_id(RUN_ID_PREFIXES["discovery"])
        request = discover_request(body, self._settings, run_id, self._shared_console)
        record = new_running_record(run_id, "discovery", body.capability_id, body.tenant)
        return self._start(record, lambda: self._runners.discover(request))

    def _start(self, record: RunRecord, work: Callable[[], Awaitable[CommandOutcome]]) -> RunStarted | ApiError:
        if self._active_run_id is not None:
            log_failure(_logger, "RunManager.start", "a run is already active",
                        active_run_id=self._active_run_id, refused_run_id=record.run_id)
            return ApiError(409, "busy", f"run {self._active_run_id} is still active",
                            {"run_id": self._active_run_id})
        self._active_run_id = record.run_id
        self._records[record.run_id] = record
        self._active_task = asyncio.create_task(self._execute(record, work), name=f"run:{record.run_id}")
        _logger.info("started %s run %s", record.mode, record.run_id)
        return RunStarted(run_id=record.run_id)

    async def _execute(self, record: RunRecord, work: Callable[[], Awaitable[CommandOutcome]]) -> None:
        try:
            outcome = await work()
        except asyncio.CancelledError:
            self._records[record.run_id] = crashed_record(record, "run cancelled (server shutting down)")
            raise
        except Exception as error:  # noqa: BLE001 - task boundary: any crash must end the run, not the server
            log_failure(_logger, "RunManager._execute", repr(error), run_id=record.run_id, mode=record.mode)
            self._records[record.run_id] = crashed_record(record, repr(error))
        else:
            self._records[record.run_id] = finished_record(record, outcome.summary)
        finally:
            self._release(record.run_id)

    def _release(self, run_id: str) -> None:
        self._shared_console.unregister(run_id)
        if self._active_run_id == run_id:
            self._active_run_id = None
            self._active_task = None

    async def wait_for_active(self, timeout_s: float | None = None) -> bool:
        """Wait until no run is active. False on timeout."""
        task = self._active_task
        if task is None:
            return True
        done, _pending = await asyncio.wait({task}, timeout=timeout_s)
        return bool(done)

    async def shutdown(self) -> None:
        """Cancel the active run (server shutdown); its record ends as `error`."""
        task = self._active_task
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.wait({task}, timeout=10)

    # ------------------------------------------------------------ queries

    def find(self, run_id: str) -> RunRecord | None:
        """This process's record (with live state) or a finished run found on disk."""
        record = self._records.get(run_id)
        if record is not None:
            return self._live(record)
        run_dir = run_dir_for(self._settings.evidence_root, run_id)
        return None if run_dir is None else record_from_run_dir(run_dir)

    def list_runs(self, limit: int) -> list[dict[str, Any]]:
        on_disk = {record.run_id: record for record in scan_run_records(self._settings.evidence_root)}
        in_memory = {run_id: self._live(record) for run_id, record in self._records.items()}
        merged = list({**on_disk, **in_memory}.values())
        return [record.list_item() for record in newest_first(merged)[: max(limit, 0)]]

    def detail(self, run_id: str) -> dict[str, Any] | None:
        record = self.find(run_id)
        if record is None:
            return None
        run_dir = run_dir_for(self._settings.evidence_root, run_id)
        files = list_run_files(run_dir) if run_dir is not None else {"screenshots": [], "snapshots": []}
        return {**record.list_item(), "result": record.result, "intervention": self.open_intervention(run_id),
                "files": files}

    def events(self, run_id: str, after: int) -> dict[str, Any] | None:
        record = self.find(run_id)
        if record is None:
            return None
        run_dir = run_dir_for(self._settings.evidence_root, run_id)
        page = read_events_after(run_dir, after) if run_dir is not None else EventPage(last_seq=after)
        return {"events": page.events, "last_seq": page.last_seq, "state": record.state}

    def file(self, run_id: str, relative_path: str) -> Path | None:
        if self.find(run_id) is None:
            return None
        run_dir = run_dir_for(self._settings.evidence_root, run_id)
        return None if run_dir is None else safe_run_file(run_dir, relative_path)

    def open_intervention(self, run_id: str) -> dict[str, Any] | None:
        """The open InterventionRequest for this run plus its session's current lease, or None."""
        request = self._shared_console.open_intervention(run_id)
        if request is None:
            return None
        lease = self._shared_console.leases.get(run_id)
        return {**request.model_dump(mode="json"), "lease": lease_view(lease)}

    def _live(self, record: RunRecord) -> RunRecord:
        request = self._shared_console.open_intervention(record.run_id)
        return with_live_state(record, None if request is None else request.reason)
