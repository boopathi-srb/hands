"""Build one live, guarded session for a discovery or replay run, and tear it down cleanly.

Everything a run touches is created here, so the discovery agent and replay engine only ever see ports:
Surface (guarded), PolicyGate, EvidenceSink, Escalator, CredentialProvider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hands.console.app import create_console_app
from hands.console.server import ConsoleServer
from hands.core.log import get_logger, log_failure
from hands.core.ports import Escalator, Surface
from hands.evidence import EvidenceRecorder
from hands.policy import YamlPolicyGate, load_policy
from hands.redact import Redactor
from hands.runtime.shared_console import SharedConsole
from hands.session.board import InterventionBoard
from hands.session.escalation import ConsoleEscalator, ScriptedEscalator
from hands.session.guarded import GuardedSurface
from hands.session.lease import LeaseManager

logger = get_logger(__name__)

EscalationMode = Literal["console", "scripted-resume", "scripted-abort", "none"]
SurfaceChoice = Literal["web", "fake"]
RunMode = Literal["discovery", "replay"]


@dataclass(frozen=True)
class SessionOptions:
    mode: RunMode
    run_id: str
    evidence_root: Path
    policy_path: Path
    surface: SurfaceChoice = "web"
    headless: bool = True
    escalation: EscalationMode = "console"
    console_port: int = 8765
    escalation_timeout_s: float | None = 900.0
    capability_status: Literal["draft", "approved", "deprecated"] | None = None
    risky_confirmed: bool = False
    fake_tenant: str = "lakeside"
    # Playwright traces capture typed text verbatim and bypass the redactor, so they are opt-in and local-only.
    record_trace: bool = False
    fake_base_url: str = "http://127.0.0.1:8700"
    # Set by a long-lived host (`hands serve`): the run joins its board and console instead of starting its own.
    shared_console: SharedConsole | None = field(default=None, compare=False, repr=False)


@dataclass
class RunSession:
    options: SessionOptions
    redactor: Redactor
    evidence: EvidenceRecorder
    policy: YamlPolicyGate
    lease: LeaseManager
    board: InterventionBoard
    raw_surface: Surface
    surface: GuardedSurface
    escalator: Escalator | None
    console: ConsoleServer | None = None
    shared_console: SharedConsole | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def session_id(self) -> str:
        return self.options.run_id

    async def close(self) -> None:
        """Stop or leave the console, close the surface (flushing the trace), and write the evidence summary."""
        if self.console is not None:
            await self.console.stop()
        if self.shared_console is not None:
            self.shared_console.unregister(self.session_id)
        await self.raw_surface.close()
        self.evidence.summary()


@dataclass(frozen=True)
class SessionBuild:
    session: RunSession | None = None
    error: str | None = None


async def build_session(options: SessionOptions) -> SessionBuild:
    """Create redactor, evidence, policy, surface, lease, guard, escalator, and console, in that order."""
    redactor = Redactor()
    evidence_or_error = _create_evidence(options, redactor)
    if isinstance(evidence_or_error, str):
        return SessionBuild(error=evidence_or_error)
    policy_or_error = _load_policy_gate(options.policy_path)
    if isinstance(policy_or_error, str):
        return SessionBuild(error=policy_or_error)
    raw_surface = await _launch_surface(options, evidence_or_error)
    if isinstance(raw_surface, str):
        return SessionBuild(error=raw_surface)
    session = _assemble(options, redactor, evidence_or_error, policy_or_error, raw_surface)
    console_error = await _start_console_if_needed(session)
    if console_error is not None:
        await session.close()
        return SessionBuild(error=console_error)
    return SessionBuild(session=session)


def _create_evidence(options: SessionOptions, redactor: Redactor) -> EvidenceRecorder | str:
    created = EvidenceRecorder.create(options.evidence_root, options.run_id, redactor)
    if not created.ok:
        log_failure(logger, "_create_evidence", created.message, run_id=options.run_id)
        return f"cannot create evidence directory: {created.message}"
    return created.recorder


def _load_policy_gate(policy_path: Path) -> YamlPolicyGate | str:
    loaded = load_policy(policy_path)
    if not loaded.ok:
        return f"cannot load policy {policy_path}: {loaded.message}"
    return YamlPolicyGate(loaded.config)


async def _launch_surface(options: SessionOptions, evidence: EvidenceRecorder) -> Surface | str:
    if options.surface == "fake":
        from hands.surfaces.fake import coreone_fake

        return coreone_fake(options.fake_tenant, base_url=options.fake_base_url)
    return await _launch_browser(options, evidence)


async def _launch_browser(options: SessionOptions, evidence: EvidenceRecorder) -> Surface | str:
    from hands.surfaces.browser.surface import BrowserSurface, SurfaceLaunchError

    trace_dir = str(Path(evidence.run_dir) / "trace") if options.record_trace else None
    try:
        return await BrowserSurface.launch(headless=options.headless, record_trace_dir=trace_dir)
    except SurfaceLaunchError as launch_error:
        log_failure(logger, "_launch_browser", str(launch_error), headless=options.headless)
        return f"cannot launch browser: {launch_error}"


def _assemble(
    options: SessionOptions,
    redactor: Redactor,
    evidence: EvidenceRecorder,
    policy: YamlPolicyGate,
    raw_surface: Surface,
) -> RunSession:
    board = options.shared_console.board if options.shared_console is not None else InterventionBoard()
    lease = LeaseManager(options.run_id, interventions=board, evidence=evidence)
    lease.grant_automation(options.run_id, reason=f"{options.mode} run started")
    guarded = GuardedSurface(
        raw_surface, lease, policy, evidence, options.mode, options.run_id,
        capability_status=options.capability_status, risky_confirmed=options.risky_confirmed,
    )
    session = RunSession(options, redactor, evidence, policy, lease, board, raw_surface, guarded, None)
    session.escalator = _build_escalator(session)
    return session


def _build_escalator(session: RunSession) -> Escalator | None:
    mode = session.options.escalation
    if mode == "none":
        return None
    if mode in ("scripted-resume", "scripted-abort"):
        outcome = "resume" if mode == "scripted-resume" else "abort"
        return ScriptedEscalator(
            session.board, session.lease, session.evidence, outcome=outcome,
            note=f"scripted operator chose {outcome}", surface=session.surface,
        )
    return ConsoleEscalator(
        session.board, session.lease, session.evidence, _console_url(session.options),
        timeout_s=session.options.escalation_timeout_s,
    )


def _console_url(options: SessionOptions) -> str:
    if options.shared_console is not None:
        return options.shared_console.operator_url()
    return f"http://127.0.0.1:{options.console_port}"


async def _start_console_if_needed(session: RunSession) -> str | None:
    if session.options.escalation != "console":
        return None
    if session.options.shared_console is not None:
        return _join_shared_console(session, session.options.shared_console)
    session_id = session.session_id
    app = create_console_app(
        session.board, {session_id: session.lease}, {session_id: session.surface}, {session_id: session.evidence}
    )
    session.console = ConsoleServer(app, port=session.options.console_port)
    started = await session.console.start()
    if not started.ok:
        log_failure(logger, "_start_console_if_needed", started.message, port=session.options.console_port)
        return f"cannot start operator console: {started.message}"
    logger.info("operator console listening at %s", started.url)
    return None


def _join_shared_console(session: RunSession, shared_console: SharedConsole) -> str | None:
    """Register on the host's console instead of starting a server; the host already serves it."""
    registered = shared_console.register(session.session_id, session.lease, session.surface, session.evidence)
    if not registered:
        return f"session {session.session_id} is already registered on the shared console"
    session.shared_console = shared_console
    return None
