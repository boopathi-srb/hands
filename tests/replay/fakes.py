"""Minimal in-test doubles for the replay engine's ports. No dependency on other adapter packages."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from hands.core.actions import (
    Action,
    ActResult,
    ActTarget,
    NodeRef,
    OpenAction,
    PressAction,
    TypeAction,
)
from hands.core.control import InterventionRequest, InterventionResolution
from hands.core.observation import Dialog, Location, Node, Observation, Rect
from hands.core.ports import PolicyDecision, PolicyRequest

FAKE_PNG = b"\x89PNG\r\n\x1a\nfake"
Route = str | list[str] | Callable[[Mapping[str, str]], str | list[str]]


# ---------------------------------------------------------------- clock


class FakeClock:
    """Deterministic time: sleeping advances monotonic time instantly."""

    def __init__(self) -> None:
        self.time = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.time

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.time += seconds

    def now(self) -> datetime:
        return datetime(2026, 9, 28, tzinfo=UTC) + timedelta(seconds=self.time)


# ---------------------------------------------------------------- nodes


_ROW_HEIGHT = 30.0


def text(content: str, row: int = 0) -> Node:
    return Node(ref="", role="text", name=content, text=content, bounds=_bounds(row, 0))


def button(name: str, row: int = 0) -> Node:
    return Node(ref="", role="button", name=name, text=name, bounds=_bounds(row, 1))


def textbox(label: str, row: int = 0, value: str | None = None) -> Node:
    return Node(ref="", role="textbox", name="", label=label, value=value, bounds=_bounds(row, 2))


def _bounds(row: int, column: int) -> Rect:
    return Rect(x=10 + column * 200, y=10 + row * _ROW_HEIGHT, width=180, height=24)


@dataclass
class Screen:
    name: str
    nodes: list[Node]
    location: str = "http://app.test/main"
    title: str = "App"
    dialogs: list[Dialog] = field(default_factory=list)


# ---------------------------------------------------------------- surface


class ScriptedSurface:
    """A tiny state machine: screens plus transitions keyed by (node name/label | 'open:<url>' | 'press:<key>',
    action kind). A route may be a screen name, a list (all but the last are shown on successive observations
    before the last one settles), or a function of the typed values."""

    kind: Literal["fake"] = "fake"

    def __init__(self, screens: list[Screen], initial: str, transitions: dict[tuple[str, str], Route]) -> None:
        self.screens = {screen.name: screen for screen in screens}
        self.current = initial
        self.transitions = transitions
        self.pending: list[str] = []
        self.values: dict[str, str] = {}
        self.actions: list[tuple[ActTarget, Action]] = []
        self.fail_next_acts = 0
        self.observe_error: Exception | None = None
        self.act_error: Exception | None = None
        self.observation_count = 0
        self._last_nodes: dict[str, Node] = {}

    def show(self, route: str | list[str]) -> None:
        names = [route] if isinstance(route, str) else list(route)
        self.pending = names[:-1]
        self.current = names[-1]

    async def observe(self, include_screenshot: bool = True) -> Observation:
        self.observation_count += 1
        if self.observe_error is not None:
            raise self.observe_error
        shown_name = self.pending.pop(0) if self.pending else self.current
        screen = self.screens[shown_name]
        nodes = [node.model_copy(update={"ref": f"n{index}"}) for index, node in enumerate(screen.nodes, start=1)]
        self._last_nodes = {node.ref: node for node in nodes}
        return Observation(
            observed_at=datetime(2026, 9, 28, tzinfo=UTC),
            location=Location(kind="url", value=screen.location, title=screen.title),
            nodes=nodes,
            dialogs=list(screen.dialogs),
            fingerprint=f"fp-{shown_name}",
            screenshot_png=FAKE_PNG if include_screenshot else None,
        )

    async def act(self, target: ActTarget, action: Action) -> ActResult:
        self.actions.append((target, action))
        if self.act_error is not None:
            raise self.act_error
        if self.fail_next_acts > 0:
            self.fail_next_acts -= 1
            return ActResult(ok=False, error="simulated act failure")
        key = self._transition_key(target, action)
        if isinstance(action, TypeAction):
            self.values[key] = action.text
        route = self.transitions.get((key, action.kind))
        if route is not None:
            self.show(route(self.values) if callable(route) else route)
        return ActResult(ok=True)

    async def close(self) -> None:
        return None

    def live_view(self) -> None:
        return None

    def _transition_key(self, target: ActTarget, action: Action) -> str:
        if isinstance(action, OpenAction):
            return f"open:{action.entry_point}"
        if isinstance(action, PressAction) and target is None:
            return f"press:{action.key}"
        if isinstance(target, NodeRef) and target.ref in self._last_nodes:
            node = self._last_nodes[target.ref]
            return node.label or node.name
        return "?"

    def acted_kinds(self) -> list[str]:
        return [action.kind for _target, action in self.actions]


# ---------------------------------------------------------------- policy, evidence, escalator, credentials


class FakePolicy:
    """Allows safe actions; risky ones only when approved and confirmed. `deny_kinds` forces denials."""

    def __init__(self, deny_kinds: tuple[str, ...] = (), escalate_risky: bool = False) -> None:
        self.deny_kinds = deny_kinds
        self.escalate_risky = escalate_risky
        self.requests: list[PolicyRequest] = []

    def check(self, request: PolicyRequest) -> PolicyDecision:
        self.requests.append(request)
        if request.action.kind in self.deny_kinds:
            return PolicyDecision(verdict="deny", risk="safe", reason="kind not allowed", rule="actions.allowed")
        if request.declared_risk != "risky":
            return PolicyDecision(verdict="allow", risk="safe", reason="safe", rule="default")
        if self.escalate_risky:
            return PolicyDecision(verdict="escalate", risk="risky", reason="needs a human", rule="risk.escalate")
        if request.capability_status == "approved" and request.risky_confirmed:
            return PolicyDecision(verdict="allow", risk="risky", reason="approved+confirmed", rule="risk.replay")
        return PolicyDecision(verdict="deny", risk="risky", reason="not approved/confirmed", rule="risk.replay")


class MemoryEvidence:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.snapshots: list[str] = []
        self.screenshots: list[str] = []
        self.documents: dict[str, Any] = {}

    @property
    def run_dir(self) -> str:
        return "evidence/test-run"

    def event(self, kind: str, **data: Any) -> None:
        self.events.append((kind, data))

    def screenshot(self, name: str, png: bytes) -> str:
        self.screenshots.append(name)
        return f"screenshots/{name}.png"

    def snapshot(self, name: str, observation: Observation) -> str:
        self.snapshots.append(name)
        return f"snapshots/{name}.json"

    def write_json(self, name: str, payload: BaseModel | dict[str, Any]) -> str:
        self.documents[name] = payload
        return f"{name}.json"

    def kinds(self) -> list[str]:
        return [kind for kind, _data in self.events]

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [data for event_kind, data in self.events if event_kind == kind]


HumanHook = Callable[[InterventionRequest], None]


class FakeEscalator:
    def __init__(
        self,
        outcome: Literal["resume", "abort", "step_completed_by_human"] = "resume",
        note: str = "",
        human: HumanHook | None = None,
    ) -> None:
        self.outcome = outcome
        self.note = note
        self.human = human
        self.requests: list[InterventionRequest] = []

    async def escalate(self, request: InterventionRequest) -> InterventionResolution:
        self.requests.append(request)
        if self.human is not None:
            self.human(request)
        return InterventionResolution(
            intervention_id=request.intervention_id,
            outcome=self.outcome,
            operator_id="operator-1",
            note=self.note,
            resolved_at=datetime(2026, 9, 28, tzinfo=UTC),
        )


class FakeCredentials:
    def __init__(self, values: dict[tuple[str, str], str] | None = None) -> None:
        self.values = values if values is not None else {("teller", "username"): "teller1", ("teller", "password"): "pw-123"}

    def get(self, credential_name: str, field: str) -> str | None:
        return self.values.get((credential_name, field))


class SecretLog:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str]] = []

    def __call__(self, value: str, label: str) -> bool:
        self.registered.append((value, label))
        return True
