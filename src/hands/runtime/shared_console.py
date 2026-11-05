"""SharedConsole: one intervention board and one operator console shared by many runs in one process.

The CLI builds a private board and console server per run. A long-lived process (`hands serve`) instead
keeps one SharedConsole: every run registers its lease, guarded surface and evidence here under its
session id, its ConsoleEscalator opens interventions on the shared board, and a single console app
(mounted by the API) reads these maps live. Runs unregister when they close.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hands.core.control import InterventionRequest
from hands.core.log import get_logger, log_failure
from hands.core.ports import EvidenceSink, Surface
from hands.session.board import InterventionBoard
from hands.session.lease import LeaseManager

_logger: logging.Logger = get_logger(__name__)

DEFAULT_CONSOLE_BASE_PATH = "/console"


@dataclass
class SharedConsole:
    """Board plus per-session maps the console app reads. `public_base_path` is where the console lives."""

    board: InterventionBoard = field(default_factory=InterventionBoard)
    leases: dict[str, LeaseManager] = field(default_factory=dict)
    surfaces: dict[str, Surface] = field(default_factory=dict)
    evidence: dict[str, EvidenceSink] = field(default_factory=dict)
    public_base_path: str = DEFAULT_CONSOLE_BASE_PATH

    def register(
        self, session_id: str, lease: LeaseManager, surface: Surface, evidence: EvidenceSink
    ) -> bool:
        """Make a live session visible to the console. False (logged) when the id is already registered."""
        if session_id in self.leases:
            log_failure(_logger, "SharedConsole.register", "session already registered",
                        session_id=session_id)
            return False
        self.leases[session_id] = lease
        self.surfaces[session_id] = surface
        self.evidence[session_id] = evidence
        return True

    def unregister(self, session_id: str) -> bool:
        """Forget a session. False when it was not registered (nothing to do)."""
        was_registered = session_id in self.leases
        self.leases.pop(session_id, None)
        self.surfaces.pop(session_id, None)
        self.evidence.pop(session_id, None)
        return was_registered

    def is_registered(self, session_id: str) -> bool:
        return session_id in self.leases

    def open_intervention(self, session_id: str) -> InterventionRequest | None:
        """The open intervention for this session, if a human is needed right now."""
        return self.board.open_for_session(session_id)

    def operator_url(self) -> str:
        """Base the escalator puts into its announcement links (a path, relative to the API host)."""
        return self.public_base_path.rstrip("/") or "/"
