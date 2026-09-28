"""The Planner port: what the discovery loop asks a model, and the strict shape of what it may answer.

Every planner (scripted, Ollama, Anthropic, cassette) takes a `PlannerContext` and returns a
`PlannerResponse`. A planner never raises for model or transport problems: it returns a response with
`decision=None` and an `error`, and the loop decides what to do (re-prompt, give up, escalate).

The model's answer is untrusted. `PlannerDecision` is validated strictly (unknown keys rejected, action
limited to a closed set) and the loop validates it again against the live observation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PlannerAction = Literal[
    "open", "click", "type", "press", "select", "scroll", "extract", "done", "stuck"
]
PLANNER_ACTIONS: tuple[str, ...] = (
    "open", "click", "type", "press", "select", "scroll", "extract", "done", "stuck"
)
MAX_RATIONALE_CHARS = 300
MAX_EXPECTED_RESULT_CHARS = 200
_OPTIONAL_TEXT_FIELDS = ("node_ref", "value", "key", "option", "output_name", "expected_result")
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class PlannerDecision(BaseModel):
    """One action the model proposes. Field order matters: rationale first helps small models reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rationale: str = Field(description="Why this action, in one short sentence.")
    action: PlannerAction
    node_ref: str | None = Field(default=None, description="Ref from the screen listing, e.g. 'n12'.")
    value: str | None = Field(default=None, description="Text to type, or URL for open.")
    key: str | None = Field(default=None, description="Key for press, e.g. 'Enter'.")
    option: str | None = Field(default=None, description="Visible option text for select.")
    output_name: str | None = Field(default=None, description="snake_case name for extract.")
    expected_result: str | None = Field(default=None, description="What should happen next.")

    @field_validator("rationale")
    @classmethod
    def _short_rationale(cls, rationale: str) -> str:
        return " ".join(rationale.split())[:MAX_RATIONALE_CHARS]

    @field_validator("expected_result")
    @classmethod
    def _short_expected_result(cls, expected_result: str | None) -> str | None:
        if expected_result is None:
            return None
        return " ".join(expected_result.split())[:MAX_EXPECTED_RESULT_CHARS] or None

    @field_validator("node_ref", "value", "key", "option", "output_name")
    @classmethod
    def _empty_as_none(cls, text: str | None) -> str | None:
        return text if text not in (None, "") else None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0


class PlannerResponse(BaseModel):
    """What a planner returns. Exactly one of `decision` / `error` is normally set."""

    decision: PlannerDecision | None = None
    raw_text: str = ""
    error: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: int = 0


class HistoryEntry(BaseModel):
    """A compact record of one earlier turn, shown back to the model. Values are placeholders only."""

    step: int
    action: str
    node_ref: str | None = None
    target: str = ""
    value: str | None = None
    result: str


class InputHint(BaseModel):
    name: str
    example: str


class PlannerContext(BaseModel):
    """Everything a planner may see for one turn. Never contains a credential value."""

    goal: str
    inputs: list[InputHint] = Field(default_factory=list)
    credential_placeholders: list[str] = Field(default_factory=list)
    observation_text: str
    screenshot_png: bytes | None = Field(default=None, exclude=True)
    history: list[HistoryEntry] = Field(default_factory=list)
    extracted: dict[str, str] = Field(default_factory=dict)
    steps_remaining: int
    feedback: str | None = None


@runtime_checkable
class Planner(Protocol):
    """Decide the next action. Must not raise for model or transport failures."""

    async def decide(self, context: PlannerContext) -> PlannerResponse: ...


# ---------------------------------------------------------------- schema and parsing


def _nullable_string() -> dict[str, Any]:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def decision_json_schema() -> dict[str, Any]:
    """Strict JSON schema for PlannerDecision: every key required, nullable optionals, no extras.

    Written by hand (not `model_json_schema()`) so it has no $defs, no titles and no length limits,
    which keeps it acceptable to both Ollama's grammar sampler and Anthropic strict tool use.
    """
    properties: dict[str, Any] = {
        "rationale": {"type": "string", "description": "Why this action, one short sentence."},
        "action": {"type": "string", "enum": list(PLANNER_ACTIONS)},
        "node_ref": _nullable_string(),
        "value": _nullable_string(),
        "key": _nullable_string(),
        "option": _nullable_string(),
        "output_name": _nullable_string(),
        "expected_result": _nullable_string(),
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class DecisionParse(BaseModel):
    decision: PlannerDecision | None = None
    error: str | None = None


def parse_decision_payload(payload: object) -> DecisionParse:
    """Validate an already-decoded JSON object as a PlannerDecision."""
    if not isinstance(payload, dict):
        return DecisionParse(error=f"expected a JSON object, got {type(payload).__name__}")
    normalized = {key: value for key, value in payload.items()}
    for field_name in _OPTIONAL_TEXT_FIELDS:
        normalized.setdefault(field_name, None)
    try:
        return DecisionParse(decision=PlannerDecision.model_validate(normalized))
    except ValidationError as validation_error:
        return DecisionParse(error=_summarize_validation_error(validation_error))


def parse_decision_text(raw_text: str) -> DecisionParse:
    """Parse model text that should be one JSON object (tolerates code fences and surrounding prose)."""
    candidate = _json_candidate(raw_text)
    if candidate is None:
        return DecisionParse(error="no JSON object found in the model output")
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as decode_error:
        return DecisionParse(error=f"invalid JSON: {decode_error.msg} at char {decode_error.pos}")
    return parse_decision_payload(payload)


def _json_candidate(raw_text: str) -> str | None:
    stripped = raw_text.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        return stripped
    match = _JSON_OBJECT.search(stripped)
    return match.group(0) if match else None


def _summarize_validation_error(validation_error: ValidationError) -> str:
    problems = [
        f"{'.'.join(str(part) for part in issue['loc']) or 'decision'}: {issue['msg']}"
        for issue in validation_error.errors()
    ]
    return "decision failed validation: " + "; ".join(problems)
