"""GuardedSurface: the only way automation acts on a live session.

Design choice: the guard lives INSIDE `act()`, not in a separate `check()` the loop must remember to call.
`act()` returns `GuardedActResult`, a subclass of `ActResult`, so it still satisfies the `Surface`
protocol for code that only reads `ok`/`error`, while loops that care read `blocked_by`:

- `not_in_control`  the lease is not held by automation with this run id; nothing was sent to the app
- `policy_denied`   the policy gate said deny; nothing was sent
- `policy_escalate` the policy gate wants a person (risky step, unknown location); nothing was sent.
                    The loop raises an InterventionRequest and, if the operator approves ("resume"),
                    retries with `act(..., confirm_risky=True)`.

`act()` also accepts keyword-only `declared_risk` (the step's declared risk) and `confirm_risky`; both
default so the protocol signature `act(target, action)` still works.

Every attempt, every policy decision, and every result is written to evidence. Typed text is never
written: only its length. `observe()` is always allowed (read-only) and records what was seen.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from hands.core.actions import Action, ActResult, ActTarget, NodeRef, OpenAction, Point, TypeAction
from hands.core.artifact import Risk
from hands.core.log import get_logger
from hands.core.observation import Location, Node, Observation
from hands.core.ports import (
    EvidenceSink,
    LiveViewTransport,
    PolicyDecision,
    PolicyGate,
    PolicyRequest,
    Surface,
    SurfaceKind,
)
from hands.session.hittest import node_at
from hands.session.lease import LeaseManager

_logger: logging.Logger = get_logger(__name__)

GuardBlock = Literal["not_in_control", "policy_denied", "policy_escalate"]
AutomationMode = Literal["discovery", "replay"]
CapabilityStatus = Literal["draft", "approved", "deprecated"]
NOT_IN_CONTROL = "not in control"


class GuardedActResult(ActResult):
    """An ActResult that also says whether (and why) the guard stopped the action."""

    decision: PolicyDecision | None = None
    blocked_by: GuardBlock | None = None

    @property
    def needs_escalation(self) -> bool:
        return self.blocked_by == "policy_escalate"


def describe_action(action: Action) -> dict[str, Any]:
    """Evidence-safe description of an action. Typed text is reduced to its length."""
    if isinstance(action, TypeAction):
        return {"kind": "type", "text_length": len(action.text), "clear_first": action.clear_first}
    return action.model_dump(mode="json")


def describe_target(target: ActTarget, node: Node | None) -> dict[str, Any]:
    """Evidence-safe description of an act target and the node it resolved to, if any."""
    description: dict[str, Any] = {"type": "none"}
    if isinstance(target, NodeRef):
        description = {"type": "node", "ref": target.ref}
    elif isinstance(target, Point):
        description = {"type": "point", "x": target.x, "y": target.y}
    if node is not None:
        description.update(node_role=node.role, node_name=node.name)
    return description


def location_kind_for(surface_kind: SurfaceKind) -> Literal["url", "window"]:
    return "window" if surface_kind == "desktop" else "url"


class GuardedSurface:
    """Wraps a Surface; acts only while automation holds the lease and the policy gate allows."""

    def __init__(
        self,
        surface: Surface,
        lease: LeaseManager,
        policy: PolicyGate,
        evidence: EvidenceSink,
        mode: AutomationMode,
        run_id: str,
        capability_status: CapabilityStatus | None = None,
        risky_confirmed: bool = False,
    ) -> None:
        self.kind: SurfaceKind = surface.kind
        self._surface = surface
        self._lease = lease
        self._policy = policy
        self._evidence = evidence
        self._mode = mode
        self._run_id = run_id
        self._capability_status = capability_status
        self._risky_confirmed = risky_confirmed
        self._latest_observation: Observation | None = None

    @property
    def latest_observation(self) -> Observation | None:
        return self._latest_observation

    @property
    def run_id(self) -> str:
        return self._run_id

    # ------------------------------------------------------------ Surface protocol

    async def observe(self, include_screenshot: bool = True) -> Observation:
        observation = await self._surface.observe(include_screenshot=include_screenshot)
        self._latest_observation = observation
        self._evidence.event(
            "observed",
            run_id=self._run_id,
            location=observation.location.model_dump(mode="json"),
            fingerprint=observation.fingerprint,
            node_count=len(observation.nodes),
            dialog_count=len(observation.dialogs),
        )
        return observation

    async def act(
        self,
        target: ActTarget,
        action: Action,
        *,
        declared_risk: Risk | None = None,
        confirm_risky: bool = False,
    ) -> GuardedActResult:
        target_node = self._resolve_target_node(target)
        self._record_attempt(target, action, target_node)
        if not self._lease.is_held_by("automation", self._run_id):
            return self._blocked("not_in_control", NOT_IN_CONTROL, decision=None)
        request = self._policy_request(action, target_node, declared_risk, confirm_risky)
        decision = self._policy.check(request)
        self._record_decision(action, decision)
        if decision.verdict == "deny":
            return self._blocked("policy_denied", decision.reason, decision)
        if decision.verdict == "escalate":
            return self._blocked("policy_escalate", decision.reason, decision)
        return await self._perform(target, action, decision)

    async def close(self) -> None:
        await self._surface.close()

    def live_view(self) -> LiveViewTransport | None:
        return self._surface.live_view()

    # ------------------------------------------------------------ internals

    async def _perform(
        self, target: ActTarget, action: Action, decision: PolicyDecision
    ) -> GuardedActResult:
        raw_result = await self._surface.act(target, action)
        result = GuardedActResult(ok=raw_result.ok, error=raw_result.error, decision=decision)
        self._evidence.event(
            "action_result",
            run_id=self._run_id,
            action=describe_action(action),
            ok=result.ok,
            error=result.error,
        )
        return result

    def _resolve_target_node(self, target: ActTarget) -> Node | None:
        observation = self._latest_observation
        if observation is None:
            return None
        if isinstance(target, NodeRef):
            return observation.node_by_ref(target.ref)
        if isinstance(target, Point):
            return node_at(observation, target.x, target.y)
        return None

    def _current_location(self, action: Action) -> Location:
        kind = location_kind_for(self.kind)
        if isinstance(action, OpenAction):
            return Location(kind=kind, value=action.entry_point)
        if self._latest_observation is not None:
            return self._latest_observation.location
        return Location(kind=kind, value="")

    def _policy_request(
        self,
        action: Action,
        target_node: Node | None,
        declared_risk: Risk | None,
        confirm_risky: bool,
    ) -> PolicyRequest:
        return PolicyRequest(
            mode=self._mode,
            action=action,
            location=self._current_location(action),
            target_node=target_node,
            declared_risk=declared_risk,
            capability_status=self._capability_status,
            risky_confirmed=self._risky_confirmed or confirm_risky,
        )

    def _record_attempt(self, target: ActTarget, action: Action, node: Node | None) -> None:
        self._evidence.event(
            "action_attempted",
            run_id=self._run_id,
            mode=self._mode,
            action=describe_action(action),
            target=describe_target(target, node),
            holder=self._lease.current().holder,
        )

    def _record_decision(self, action: Action, decision: PolicyDecision) -> None:
        self._evidence.event(
            "policy_decision",
            run_id=self._run_id,
            action=describe_action(action),
            **decision.model_dump(mode="json"),
        )

    def _blocked(
        self, blocked_by: GuardBlock, reason: str, decision: PolicyDecision | None
    ) -> GuardedActResult:
        _logger.warning("action blocked for run %s: %s (%s)", self._run_id, blocked_by, reason)
        self._evidence.event(
            "action_blocked", run_id=self._run_id, blocked_by=blocked_by, reason=reason
        )
        return GuardedActResult(ok=False, error=reason, decision=decision, blocked_by=blocked_by)
