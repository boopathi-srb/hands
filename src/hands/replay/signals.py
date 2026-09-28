"""Internal typed control flow of a replay run. Nothing here is raised; every function returns one of these.

Terminal ends (become the public RunResult):
    SuccessEnd, OutcomeEnd, FailureEnd, EscalatedEnd
Flow signals (absorbed inside the engine):
    RetryStep       re-run the current step from its wait phase (after a subflow recovery or a human resume)
    RestartRun      start again from step 0 (a subflow recovery with then='restart')
    HumanCompleted  an operator performed the current step; mark it 'human' and move on
    Continue        a monitor handled an interruption in place; keep polling
Wait results:
    Ready           the awaited state holds on this observation
    TimedOut        the wait deadline passed; carries the last observation and readiness detail
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hands.core.observation import Observation
from hands.core.results import FailureCode
from hands.locate import Resolution

WaitPhase = Literal["precondition", "target", "postcondition", "until", "checkpoint"]


@dataclass(frozen=True)
class SuccessEnd:
    pass


@dataclass(frozen=True)
class OutcomeEnd:
    code: str
    message: str | None
    step_id: str | None


@dataclass(frozen=True)
class FailureEnd:
    code: FailureCode
    step_id: str | None
    message: str
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True)
class EscalatedEnd:
    intervention_id: str
    reason: str
    operator_note: str | None


RunEnd = OutcomeEnd | FailureEnd | EscalatedEnd


@dataclass(frozen=True)
class RetryStep:
    reason: str


@dataclass(frozen=True)
class RestartRun:
    reason: str


@dataclass(frozen=True)
class HumanCompleted:
    intervention_id: str


@dataclass(frozen=True)
class Continue:
    reason: str


StepFlow = RetryStep | RestartRun | HumanCompleted


@dataclass(frozen=True)
class Readiness:
    """Whether the awaited state holds, which phase was checked, and a readable account of it."""

    ready: bool
    phase: WaitPhase
    detail: str
    resolution: Resolution | None = None


@dataclass(frozen=True)
class Ready:
    observation: Observation
    resolution: Resolution | None


@dataclass(frozen=True)
class TimedOut:
    observation: Observation
    readiness: Readiness


WaitResult = Ready | TimedOut | StepFlow | RunEnd


@dataclass(frozen=True)
class StepCompleted:
    pass


@dataclass(frozen=True)
class SequenceCompleted:
    pass


SequenceResult = SequenceCompleted | RestartRun | RunEnd
