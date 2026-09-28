"""Shared state the console routes read; the run holds the same objects by reference."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from hands.core.ports import EvidenceSink, Surface
from hands.session.board import InterventionBoard
from hands.session.lease import LeaseManager


@dataclass
class ConsoleState:
    board: InterventionBoard
    leases: Mapping[str, LeaseManager]
    surfaces: Mapping[str, Surface]
    evidence: Mapping[str, EvidenceSink]
    streaming_sessions: set[str] = field(default_factory=set)
