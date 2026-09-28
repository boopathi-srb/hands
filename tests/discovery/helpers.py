"""Tiny fakes for discovery tests: evidence, policy, credentials, escalator, planner, observations."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from hands.core.control import HumanAction, InterventionRequest, InterventionResolution
from hands.core.observation import Dialog, Location, Node, Observation, Rect
from hands.core.ports import PolicyDecision, PolicyRequest
from hands.discovery.planner import PlannerContext, PlannerDecision, PlannerResponse
from hands.policy import YamlPolicyGate, load_policy
from hands.surfaces.fake import FakeSurface, coreone_fake

REPO_ROOT = Path(__file__).resolve().parents[2]
COREONE_POLICY_PATH = REPO_ROOT / "policies" / "coreone.yaml"
COREONE_PROFILE_PATH = REPO_ROOT / "profiles" / "coreone.yaml"
BASE_URL = "http://127.0.0.1:8700"
LOGIN_URL = f"{BASE_URL}/t/lakeside/login"
TEST_USERNAME = "teller1"
TEST_PASSWORD = "unit-test-pass-7781"
FIXED_TIME = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------- evidence


class RecordingEvidence:
    """EvidenceSink that keeps everything in memory (and does NOT redact, to prove the loop doesn't leak)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.snapshots: dict[str, Observation] = {}
        self.screenshots: dict[str, bytes] = {}
        self.json_documents: dict[str, Any] = {}

    @property
    def run_dir(self) -> str:
        return "memory"

    def event(self, kind: str, /, **data: Any) -> None:
        self.events.append((kind, data))

    def screenshot(self, name: str, png: bytes) -> str:
        self.screenshots[name] = png
        return f"screenshots/{name}.png"

    def snapshot(self, name: str, observation: Observation) -> str:
        self.snapshots[name] = observation
        return f"snapshots/{name}.json"

    def write_json(self, name: str, payload: BaseModel | dict[str, Any]) -> str:
        self.json_documents[name] = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        return f"{name}.json"

    def kinds(self) -> list[str]:
        return [kind for kind, _data in self.events]

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [data for event_kind, data in self.events if event_kind == kind]

    def all_text(self) -> str:
        parts = [json.dumps(self.events, default=str), json.dumps(self.json_documents, default=str)]
        parts += [observation.model_dump_json() for observation in self.snapshots.values()]
        return "\n".join(parts)


# ---------------------------------------------------------------- policy


class FixedPolicy:
    """Allow everything except requests matched by `deny_when` / `escalate_when`."""

    def __init__(
        self,
        deny_when: Callable[[PolicyRequest], bool] | None = None,
        escalate_when: Callable[[PolicyRequest], bool] | None = None,
    ) -> None:
        self._deny_when = deny_when
        self._escalate_when = escalate_when
        self.requests: list[PolicyRequest] = []

    def check(self, request: PolicyRequest) -> PolicyDecision:
        self.requests.append(request)
        if self._deny_when and self._deny_when(request):
            return PolicyDecision(verdict="deny", risk="safe", reason="blocked by test rule", rule="test.deny")
        if self._escalate_when and self._escalate_when(request):
            return PolicyDecision(verdict="escalate", risk="risky", reason="risky in test", rule="test.risky")
        return PolicyDecision(verdict="allow", risk="safe", reason="allowed", rule="test.allow")


def coreone_policy() -> YamlPolicyGate:
    loaded = load_policy(COREONE_POLICY_PATH)
    assert loaded.ok, getattr(loaded, "message", "")
    return YamlPolicyGate(loaded.config)


def node_named(name: str) -> Callable[[PolicyRequest], bool]:
    return lambda request: request.target_node is not None and request.target_node.name == name


# ---------------------------------------------------------------- credentials and escalation


class DictCredentials:
    def __init__(self, values: dict[tuple[str, str], str] | None = None) -> None:
        self._values = values if values is not None else {
            ("teller", "username"): TEST_USERNAME, ("teller", "password"): TEST_PASSWORD,
        }
        self.requests: list[tuple[str, str]] = []

    def get(self, credential_name: str, field: str) -> str | None:
        self.requests.append((credential_name, field))
        return self._values.get((credential_name, field))


Outcome = Literal["resume", "abort", "step_completed_by_human"]


class StubEscalator:
    """Resolves each intervention with the next scripted outcome; optionally acts on the surface first."""

    def __init__(
        self,
        outcomes: Sequence[Outcome] = ("resume",),
        on_escalate: Callable[[InterventionRequest], Any] | None = None,
        human_actions: Sequence[HumanAction] = (),
        note: str = "",
    ) -> None:
        self._outcomes = list(outcomes)
        self._on_escalate = on_escalate
        self._human_actions = list(human_actions)
        self._note = note
        self.requests: list[InterventionRequest] = []

    async def escalate(self, request: InterventionRequest) -> InterventionResolution:
        self.requests.append(request)
        if self._on_escalate is not None:
            await self._on_escalate(request)
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        return InterventionResolution(
            intervention_id=request.intervention_id, outcome=outcome, operator_id="op-1",
            note=self._note, human_actions=self._human_actions, resolved_at=FIXED_TIME,
        )


# ---------------------------------------------------------------- planners


class SequencePlanner:
    """Returns pre-built responses (or builds them from the context) in order; the last one repeats."""

    def __init__(self, responses: Sequence[PlannerResponse | Callable[[PlannerContext], PlannerResponse]]) -> None:
        self._responses = list(responses)
        self.contexts: list[PlannerContext] = []
        self.name = "sequence"
        self.model = "none"

    async def decide(self, context: PlannerContext) -> PlannerResponse:
        self.contexts.append(context)
        index = min(len(self.contexts) - 1, len(self._responses) - 1)
        response = self._responses[index]
        return response(context) if callable(response) else response


def respond(action: str, **fields: Any) -> PlannerResponse:
    decision = PlannerDecision(rationale=fields.pop("rationale", f"test {action}"), action=action, **fields)
    return PlannerResponse(decision=decision, raw_text=decision.model_dump_json())


def failed_response(error: str) -> PlannerResponse:
    return PlannerResponse(error=error, raw_text="garbage")


# ---------------------------------------------------------------- surfaces and observations


def lakeside_fake() -> FakeSurface:
    return coreone_fake("lakeside", base_url=BASE_URL, password=TEST_PASSWORD)


def make_node(
    ref: str,
    role: str,
    name: str = "",
    *,
    text: str | None = None,
    value: str | None = None,
    label: str | None = None,
    container: tuple[str, ...] = ("frame:content",),
    path: str = "",
    box: tuple[float, float, float, float] | None = (0, 0, 100, 20),
    enabled: bool = True,
) -> Node:
    return Node(
        ref=ref, role=role, name=name, text=name if text is None else text, value=value, label=label,
        container_path=container, structural_path=path,
        bounds=Rect(x=box[0], y=box[1], width=box[2], height=box[3]) if box else None, enabled=enabled,
    )


def make_observation(
    nodes: Sequence[Node],
    url: str = f"{BASE_URL}/t/lakeside/main",
    *,
    title: str = "",
    dialogs: Sequence[Dialog] = (),
    fingerprint: str = "fp",
    screenshot: bytes | None = None,
) -> Observation:
    return Observation(
        observed_at=FIXED_TIME, location=Location(kind="url", value=url, title=title), nodes=list(nodes),
        dialogs=list(dialogs), fingerprint=fingerprint, screenshot_png=screenshot,
    )


def png_bytes(width: int, height: int, color: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    import io

    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return output.getvalue()


def planner_context(observation_text: str = "LOCATION: x", **fields: Any) -> PlannerContext:
    return PlannerContext(goal=fields.pop("goal", "test goal"), observation_text=observation_text,
                          steps_remaining=fields.pop("steps_remaining", 10), **fields)
