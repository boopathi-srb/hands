"""In-memory stand-ins for the session package's ports, for tests and headless demos.

These deliberately do not import other adapters (FakeSurface, policy, evidence recorder), so the
session and console packages can be exercised in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from hands.core.actions import Action, ActResult, ActTarget
from hands.core.artifact import Risk
from hands.core.control import InterventionRequest
from hands.core.observation import Location, Node, Observation
from hands.core.ports import (
    FrameHandler,
    KeyEvent,
    LiveViewTransport,
    PointerEvent,
    PolicyDecision,
    PolicyRequest,
    SurfaceKind,
)

InterventionKind = Literal["stuck", "unrecoverable", "risky_action", "policy_block"]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TINY_PNG_FRAME = PNG_SIGNATURE + b"stub-frame"


class InMemoryEvidence:
    """EvidenceSink that keeps events, screenshots, and snapshots in lists."""

    def __init__(self, run_dir: str = "memory") -> None:
        self._run_dir = run_dir
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.screenshots: dict[str, bytes] = {}
        self.snapshots: dict[str, Observation] = {}
        self.json_documents: dict[str, dict[str, Any]] = {}

    @property
    def run_dir(self) -> str:
        return self._run_dir

    def event(self, kind: str, **data: Any) -> None:
        self.events.append((kind, data))

    def screenshot(self, name: str, png: bytes) -> str:
        self.screenshots[name] = png
        return f"{name}.png"

    def snapshot(self, name: str, observation: Observation) -> str:
        self.snapshots[name] = observation
        return f"{name}.json"

    def write_json(self, name: str, payload: BaseModel | dict[str, Any]) -> str:
        document = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        self.json_documents[name] = document
        return f"{name}.json"

    def kinds(self) -> list[str]:
        return [kind for kind, _data in self.events]

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [data for event_kind, data in self.events if event_kind == kind]


class FixedPolicyGate:
    """PolicyGate that always returns the same verdict and remembers every request."""

    def __init__(
        self,
        verdict: Literal["allow", "deny", "escalate"] = "allow",
        reason: str = "fixed verdict",
        risk: Risk = "safe",
    ) -> None:
        self._decision = PolicyDecision(verdict=verdict, risk=risk, reason=reason, rule="fixed")
        self.requests: list[PolicyRequest] = []

    def check(self, request: PolicyRequest) -> PolicyDecision:
        self.requests.append(request)
        return self._decision


class StubLiveView:
    """LiveViewTransport that emits pre-set frames on start and records injected input."""

    def __init__(self, frames: list[bytes] | None = None, fail_injection: bool = False) -> None:
        self._frames = [TINY_PNG_FRAME] if frames is None else frames
        self._fail_injection = fail_injection
        self.pointer_events: list[PointerEvent] = []
        self.key_events: list[KeyEvent] = []
        self.started = False
        self.stopped = False

    async def start(self, on_frame: FrameHandler) -> None:
        self.started = True
        for frame in self._frames:
            await on_frame(frame)

    async def stop(self) -> None:
        self.stopped = True

    async def inject_pointer(self, event: PointerEvent) -> None:
        if self._fail_injection:
            raise ConnectionError("stub transport configured to fail")
        self.pointer_events.append(event)

    async def inject_key(self, event: KeyEvent) -> None:
        if self._fail_injection:
            raise ConnectionError("stub transport configured to fail")
        self.key_events.append(event)


class StubSurface:
    """Surface returning a fixed observation; records acts; exposes an optional live view."""

    def __init__(
        self,
        observation: Observation,
        live_view: LiveViewTransport | None = None,
        act_result: ActResult | None = None,
        kind: SurfaceKind = "fake",
    ) -> None:
        self.kind: SurfaceKind = kind
        self.observation = observation
        self._live_view = live_view
        self._act_result = act_result or ActResult(ok=True)
        self.acts: list[tuple[ActTarget, Action]] = []
        self.observe_calls = 0
        self.closed = False

    async def observe(self, include_screenshot: bool = True) -> Observation:
        self.observe_calls += 1
        return self.observation

    async def act(self, target: ActTarget, action: Action) -> ActResult:
        self.acts.append((target, action))
        return self._act_result

    async def close(self) -> None:
        self.closed = True

    def live_view(self) -> LiveViewTransport | None:
        return self._live_view


def make_observation(
    nodes: list[Node] | None = None, url: str = "http://app.test/page"
) -> Observation:
    """A minimal observation at `url` with the given nodes."""
    return Observation(
        observed_at=datetime.now(UTC),
        location=Location(kind="url", value=url, title="Stub"),
        nodes=nodes or [],
        fingerprint="stub-fingerprint",
    )


def make_intervention_request(
    session_id: str = "session-1",
    run_id: str = "run-1",
    intervention_id: str = "iv-1",
    kind: InterventionKind = "stuck",
    screenshot_path: str | None = None,
) -> InterventionRequest:
    """A synthetic intervention request with no real data."""
    return InterventionRequest(
        intervention_id=intervention_id,
        session_id=session_id,
        run_id=run_id,
        mode="replay",
        kind=kind,
        reason="unknown modal 'Verify Member Identity'",
        capability_id="member.lookup",
        goal="look up member balances",
        step_id="search",
        step_description="Click Search",
        location="http://app.test/page",
        screenshot_path=screenshot_path,
        created_at=datetime.now(UTC),
    )
