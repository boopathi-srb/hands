"""RunRecord: what the API knows about one run, from memory (this process) or from its evidence directory.

`state` is the lifecycle (running / waiting_for_operator / finished / error); `status` is the run's own
verdict (replay: success, business_outcome, escalated, failed; discovery: completed, stuck, escalated_abort,
budget_exhausted, error). `headline` is a one-line human summary for lists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from hands.api.run_files import first_event_time, modified_time, read_json_object
from hands.core.log import get_logger

_logger: logging.Logger = get_logger(__name__)

RunState = Literal["running", "waiting_for_operator", "finished", "error"]
RunMode = Literal["replay", "discovery"]
REPLAY_RESULT_FILE = "result.json"
DISCOVERY_RESULT_FILE = "discovery_result.json"
MAX_HEADLINE_CHARS = 140


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    mode: RunMode
    started_at: str
    capability_id: str | None = None
    tenant: str | None = None
    state: RunState = "running"
    status: str | None = None
    finished_at: str | None = None
    headline: str = ""
    result: dict[str, Any] | None = None

    def list_item(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "mode": self.mode, "state": self.state, "status": self.status,
            "capability_id": self.capability_id, "tenant": self.tenant, "started_at": self.started_at,
            "finished_at": self.finished_at, "headline": self.headline,
        }


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_running_record(run_id: str, mode: RunMode, capability_id: str | None, tenant: str | None) -> RunRecord:
    verb = "replaying" if mode == "replay" else "discovering"
    return RunRecord(run_id=run_id, mode=mode, started_at=utc_now_iso(), capability_id=capability_id,
                     tenant=tenant, headline=f"{verb} {capability_id or ''}".strip())


def finished_record(record: RunRecord, summary: dict[str, Any]) -> RunRecord:
    """The record after its command returned. A command-level error (no run happened) is state `error`."""
    status = summary.get("status")
    state: RunState = "error" if status == "error" and "command" in summary else "finished"
    return replace(record, state=state, status=str(status) if status else None, result=summary,
                   finished_at=str(summary.get("finished_at") or utc_now_iso()),
                   headline=build_headline(record.mode, summary))


def crashed_record(record: RunRecord, message: str) -> RunRecord:
    return replace(record, state="error", status="error", finished_at=utc_now_iso(),
                   headline=truncate(f"error: {message}"), result={"status": "error", "message": message})


def with_live_state(record: RunRecord, intervention_reason: str | None) -> RunRecord:
    """A running record waiting on an open intervention reads as `waiting_for_operator`."""
    if record.state != "running" or intervention_reason is None:
        return record
    return replace(record, state="waiting_for_operator",
                   headline=truncate(f"waiting for operator: {intervention_reason}"))


# ---------------------------------------------------------------- headlines


def build_headline(mode: RunMode, summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""
    if summary.get("status") == "error":
        return truncate(f"error: {summary.get('message') or summary.get('reason') or 'run failed'}")
    if mode == "discovery":
        return truncate(discovery_headline(summary))
    return truncate(replay_headline(summary))


def replay_headline(summary: dict[str, Any]) -> str:
    """'savings_balance 9870.12', 'MEMBER_NOT_FOUND', 'escalated: ...', 'failed: invalid_input at step'."""
    status = summary.get("status")
    if status == "success":
        outputs = summary.get("outputs") or {}
        return ", ".join(f"{name} {value}" for name, value in outputs.items()) or "success"
    if status == "business_outcome":
        return str(summary.get("code") or "business outcome")
    if status == "escalated":
        return f"escalated: {summary.get('operator_note') or summary.get('reason') or 'operator ended the run'}"
    if status == "failed":
        return _failure_headline(summary.get("failure") or {})
    return str(status or "")


def _failure_headline(failure: dict[str, Any]) -> str:
    step_id = failure.get("step_id")
    location = f" at {step_id}" if step_id else ""
    return f"failed: {failure.get('code') or 'unknown'}{location}"


def discovery_headline(summary: dict[str, Any]) -> str:
    """'recorded coreone.member_balance@1.0.0' or '<status>: <reason>'."""
    if summary.get("status") == "completed" and summary.get("capability"):
        return f"recorded {summary['capability']}"
    reason = summary.get("record_error") or summary.get("reason") or ""
    return f"{summary.get('status') or 'unknown'}: {reason}".rstrip(": ")


def truncate(text: str, limit: int = MAX_HEADLINE_CHARS) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}…"


# ---------------------------------------------------------------- runs on disk


def record_from_run_dir(run_dir: Path) -> RunRecord | None:
    """A finished record from result.json or discovery_result.json; None when neither parses."""
    replay_summary = summary_with_status(run_dir / REPLAY_RESULT_FILE)
    if replay_summary is not None:
        return _replay_record(run_dir, replay_summary)
    discovery_summary = summary_with_status(run_dir / DISCOVERY_RESULT_FILE)
    if discovery_summary is not None:
        return _discovery_record(run_dir, discovery_summary)
    return None


def summary_with_status(path: Path) -> dict[str, Any] | None:
    """The JSON object at `path` when it has a string `status`; otherwise None (warned if present)."""
    summary = read_json_object(path)
    if summary is None:
        return None
    if isinstance(summary.get("status"), str):
        return summary
    _logger.warning("ignoring %s: no status", path)
    return None


def _replay_record(run_dir: Path, summary: dict[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=run_dir.name, mode="replay", state="finished", status=summary["status"],
        capability_id=summary.get("capability_id"), tenant=summary.get("tenant_id"),
        started_at=str(summary.get("started_at") or first_event_time(run_dir) or ""),
        finished_at=summary.get("finished_at") or modified_time(run_dir / REPLAY_RESULT_FILE),
        headline=build_headline("replay", summary), result=summary,
    )


def _discovery_record(run_dir: Path, summary: dict[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=run_dir.name, mode="discovery", state="finished", status=summary["status"],
        capability_id=summary.get("capability_id") or _capability_id_from(summary.get("capability")),
        tenant=summary.get("tenant"),
        started_at=str(summary.get("started_at") or first_event_time(run_dir) or ""),
        finished_at=summary.get("finished_at") or modified_time(run_dir / DISCOVERY_RESULT_FILE),
        headline=build_headline("discovery", summary), result=summary,
    )


def _capability_id_from(capability_ref: object) -> str | None:
    """'coreone.member_balance@1.0.0' -> 'coreone.member_balance'."""
    if not isinstance(capability_ref, str) or not capability_ref:
        return None
    return capability_ref.partition("@")[0]


def scan_run_records(evidence_root: Path) -> list[RunRecord]:
    """Every finished run found under the evidence root (from this or earlier processes)."""
    if not evidence_root.is_dir():
        return []
    records = (record_from_run_dir(path) for path in sorted(evidence_root.iterdir()) if path.is_dir())
    return [record for record in records if record is not None]


def newest_first(records: list[RunRecord]) -> list[RunRecord]:
    return sorted(records, key=lambda record: _sortable_time(record.started_at), reverse=True)


def _sortable_time(timestamp: str) -> datetime:
    """Parse ISO 8601 (Python 3.11 accepts 'Z'); unparseable or empty sorts oldest."""
    try:  # untrusted timestamp text boundary
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
