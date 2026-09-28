"""Evidence: an append-only, redacted record of every run (events, screenshots, snapshots, results, summary)."""

from hands.evidence.events import EVENT_KIND_DESCRIPTIONS, STANDARD_EVENT_KINDS, EventKind
from hands.evidence.recorder import (
    EvidenceRecorder,
    RecorderCreateFailed,
    RecorderCreateResult,
    RecorderReady,
)
from hands.evidence.summary import RecordedEvent, RecordedFile, render_summary

__all__ = [
    "EVENT_KIND_DESCRIPTIONS",
    "STANDARD_EVENT_KINDS",
    "EventKind",
    "EvidenceRecorder",
    "RecordedEvent",
    "RecordedFile",
    "RecorderCreateFailed",
    "RecorderCreateResult",
    "RecorderReady",
    "render_summary",
]
