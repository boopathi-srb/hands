"""Ports: the interfaces that separate the core from its adapters.

Replay and discovery depend only on these protocols. Adapters (browser, desktop, fake, console,
evidence, policy) implement them. This is the seam the brief asks about.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from hands.core.actions import Action, ActResult, ActTarget
from hands.core.artifact import Risk
from hands.core.control import InterventionRequest, InterventionResolution
from hands.core.observation import Location, Node, Observation

SurfaceKind = Literal["web", "desktop", "fake"]


# ---------------------------------------------------------------- surface


class PointerEvent(BaseModel):
    type: Literal["down", "up", "move", "click", "wheel"]
    x: float
    y: float
    button: Literal["left", "right", "none"] = "left"
    delta_y: float = 0.0


class KeyEvent(BaseModel):
    type: Literal["down", "up", "char"]
    key: str
    text: str | None = None


FrameHandler = Callable[[bytes], Awaitable[None]]


@runtime_checkable
class LiveViewTransport(Protocol):
    """Streams the live surface to an operator and injects their input into the SAME session."""

    async def start(self, on_frame: FrameHandler) -> None: ...
    async def stop(self) -> None: ...
    async def inject_pointer(self, event: PointerEvent) -> None: ...
    async def inject_key(self, event: KeyEvent) -> None: ...


@runtime_checkable
class Surface(Protocol):
    """Perceive and act on one live application session. The only place technology leaks is the adapter."""

    kind: SurfaceKind

    async def observe(self, include_screenshot: bool = True) -> Observation:
        """Wait for the surface to settle, then snapshot a11y nodes, dialogs, location, screenshot."""
        ...

    async def act(self, target: ActTarget, action: Action) -> ActResult:
        """Perform one action. NodeRef refers to the latest observation. Must not raise for UI errors."""
        ...

    async def close(self) -> None: ...

    def live_view(self) -> LiveViewTransport | None: ...


# ---------------------------------------------------------------- policy


class PolicyRequest(BaseModel):
    mode: Literal["discovery", "replay", "human"]
    action: Action
    location: Location
    target_node: Node | None = None
    declared_risk: Risk | None = None
    capability_status: Literal["draft", "approved", "deprecated"] | None = None
    risky_confirmed: bool = False


class PolicyDecision(BaseModel):
    verdict: Literal["allow", "deny", "escalate"]
    risk: Risk
    reason: str
    rule: str | None = None


class PolicyGate(Protocol):
    def check(self, request: PolicyRequest) -> PolicyDecision: ...


# ---------------------------------------------------------------- evidence


class EvidenceSink(Protocol):
    """Append-only run evidence. Implementations redact before anything touches disk."""

    @property
    def run_dir(self) -> str: ...

    def event(self, kind: str, **data: Any) -> None: ...
    def screenshot(self, name: str, png: bytes) -> str: ...
    def snapshot(self, name: str, observation: Observation) -> str: ...
    def write_json(self, name: str, payload: BaseModel | dict[str, Any]) -> str: ...


# ---------------------------------------------------------------- escalation


class Escalator(Protocol):
    """Raises an intervention, cedes the live session to a human, and blocks until they hand back."""

    async def escalate(self, request: InterventionRequest) -> InterventionResolution: ...


# ---------------------------------------------------------------- secrets


class CredentialProvider(Protocol):
    def get(self, credential_name: str, field: str) -> str | None: ...
