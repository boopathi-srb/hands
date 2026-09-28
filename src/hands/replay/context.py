"""Everything one replay run needs, in one place: ports, timing, the invocation, and mutable run state.

`RunContext` also owns the small helpers every module shares (evidence events, templating with params and
tenant aliases, deadlines), so the step, wait, and monitor modules stay free of duplicated plumbing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from hands.core.artifact import Capability
from hands.core.conditions import Condition
from hands.core.log import get_logger, log_failure
from hands.core.observation import Observation
from hands.core.ports import CredentialProvider, Escalator, EvidenceSink, PolicyGate, Surface
from hands.core.results import StepTrace
from hands.core.targets import CandidateKind, TargetSpec
from hands.locate import Resolution, apply_aliases, fill_condition, fill_placeholders, fill_target
from hands.replay.signals import FailureEnd, SequenceResult

_logger = get_logger(__name__)

SecretRegistrar = Callable[[str, str], object]
"""Called as registrar(value, label), matching hands.redact.Redactor.register_secret."""

SubflowRunner = Callable[[str], Awaitable[SequenceResult]]
StepStatus = Literal["ok", "recovered", "failed", "skipped", "human"]


@dataclass(frozen=True)
class ReplayPorts:
    surface: Surface
    policy: PolicyGate
    evidence: EvidenceSink
    credentials: CredentialProvider
    escalator: Escalator | None = None
    secret_registrar: SecretRegistrar | None = None


@dataclass(frozen=True)
class ReplayTiming:
    monotonic: Callable[[], float]
    sleep: Callable[[float], Awaitable[None]]
    now: Callable[[], datetime]
    poll_interval_ms: int
    checkpoint_timeout_ms: int


@dataclass(frozen=True)
class RunInvocation:
    capability: Capability
    params: dict[str, str]
    aliases: dict[str, str]
    tenant_id: str | None
    session_id: str
    run_id: str
    risky_confirmed: bool
    started_at: datetime
    run_deadline: float | None
    run_timeout_ms: int | None


@dataclass
class StepTracker:
    """Accumulates what happened to one step until its StepTrace is written."""

    step_id: str
    started: float
    recoveries_applied: list[str] = field(default_factory=list)
    matched_candidate_rank: int | None = None
    matched_candidate_kind: CandidateKind | None = None
    fingerprint: str | None = None
    completed_by_human: bool = False

    def record_resolution(self, resolution: Resolution | None, observation: Observation) -> None:
        self.fingerprint = observation.fingerprint
        if resolution is not None:
            self.matched_candidate_rank = resolution.rank
            self.matched_candidate_kind = resolution.candidate_kind

    def default_status(self) -> StepStatus:
        if self.completed_by_human:
            return "human"
        return "recovered" if self.recoveries_applied else "ok"

    def to_trace(self, status: StepStatus, finished: float) -> StepTrace:
        return StepTrace(
            step_id=self.step_id,
            status=status,
            matched_candidate_rank=self.matched_candidate_rank,
            matched_candidate_kind=self.matched_candidate_kind,
            recoveries_applied=list(self.recoveries_applied),
            duration_ms=max(0, int((finished - self.started) * 1000)),
            fingerprint=self.fingerprint,
        )


@dataclass
class RunState:
    traces: list[StepTrace] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    recovery_counts: dict[str, int] = field(default_factory=dict)
    interventions: list[str] = field(default_factory=list)
    fallback_steps: list[str] = field(default_factory=list)
    escalated_step_ids: list[str] = field(default_factory=list)
    active_recoveries: list[str] = field(default_factory=list)
    restarts: int = 0
    last_observation: Observation | None = None

    def count_recovery(self, rule_name: str) -> int:
        self.recovery_counts[rule_name] = self.recovery_counts.get(rule_name, 0) + 1
        return self.recovery_counts[rule_name]

    def note_fallback(self, step_id: str) -> None:
        if step_id not in self.fallback_steps:
            self.fallback_steps.append(step_id)


class RunContext:
    """Shared by every replay module for the duration of one run."""

    def __init__(
        self,
        ports: ReplayPorts,
        timing: ReplayTiming,
        invocation: RunInvocation,
    ) -> None:
        self.ports = ports
        self.timing = timing
        self.invocation = invocation
        self.state = RunState()
        self.subflow_runner: SubflowRunner | None = None

    async def run_subflow(self, name: str) -> SequenceResult:
        """Run a named subflow inline with the same monitors (bound by the engine to avoid import cycles)."""
        if self.subflow_runner is None or name not in self.capability.subflows:
            log_failure(_logger, "RunContext.run_subflow", "subflow unavailable", subflow=name)
            return FailureEnd(
                code="unexpected_state",
                step_id=None,
                message=f"subflow '{name}' is not available to this run",
            )
        return await self.subflow_runner(name)

    @property
    def capability(self) -> Capability:
        return self.invocation.capability

    # ------------------------------------------------------------ evidence

    def emit(self, event_kind: str, **data: Any) -> None:
        self.ports.evidence.event(event_kind, run_id=self.invocation.run_id, **data)

    # ------------------------------------------------------------ templating

    def condition(self, condition: Condition) -> Condition:
        """Aliases applied to recorded text, then caller inputs and credentials filled."""
        return fill_condition(condition, self.invocation.params, self.invocation.aliases)

    def target(self, spec: TargetSpec) -> TargetSpec:
        return fill_target(spec, self.invocation.params, self.invocation.aliases)

    def ui_text(self, text: str) -> str:
        """Recorded UI text (e.g. a select option): alias first, then fill placeholders."""
        aliased = apply_aliases(text, self.invocation.aliases)
        return fill_placeholders(aliased, self.invocation.params).text

    def data_text(self, text: str) -> str:
        """Data the step enters (typed value, entry point): placeholders only, never aliased."""
        return fill_placeholders(text, self.invocation.params).text

    # ------------------------------------------------------------ time

    def deadline_after(self, timeout_ms: int) -> float:
        step_deadline = self.timing.monotonic() + timeout_ms / 1000
        run_deadline = self.invocation.run_deadline
        return step_deadline if run_deadline is None else min(step_deadline, run_deadline)

    def run_timed_out(self) -> bool:
        run_deadline = self.invocation.run_deadline
        return run_deadline is not None and self.timing.monotonic() >= run_deadline

    def start_tracker(self, step_id: str) -> StepTracker:
        return StepTracker(step_id=step_id, started=self.timing.monotonic())

    def finish_tracker(self, tracker: StepTracker, status: StepStatus) -> StepTrace:
        trace = tracker.to_trace(status, self.timing.monotonic())
        self.state.traces.append(trace)
        return trace
