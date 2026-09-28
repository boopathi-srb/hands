"""The agent-facing contract: a capability rendered as a JSON-schema tool definition.

`capability_tool_schema` returns exactly the three keys tool-use APIs accept (name, description,
input_schema). `capability_result_schema` describes what the call returns, for docs and validation.
Credentials never appear: they are resolved by the replay engine, not supplied by the caller.
"""

from __future__ import annotations

import re
from typing import Any

from hands.core.artifact import Capability, InputSpec, OutputSpec, ValueType

TOOL_NAME_MAX_LENGTH = 64
DECIMAL_STRING_PATTERN = r"^-?\d+(\.\d+)?$"
SENSITIVE_NOTE = " Sensitive: masked in all evidence and logs."
RESULT_CONTRACT_SENTENCE = (
    "Returns status 'success' (outputs), 'business_outcome' (code + message, a legitimate answer), "
    "'escalated' (a human took over), or 'failed' (step, expected, observed, evidence)."
)
_TOOL_NAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")

_INPUT_TYPE_SCHEMAS: dict[ValueType, dict[str, Any]] = {
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "decimal": {"type": "string", "pattern": DECIMAL_STRING_PATTERN},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
}
_OUTPUT_TYPE_SCHEMAS: dict[ValueType, dict[str, Any]] = {
    **_INPUT_TYPE_SCHEMAS,
    "decimal": {"type": "string", "description_suffix": " Decimal as a string, e.g. '1250.00'."},
}


def tool_name_for(capability_id: str) -> str:
    """Tool names allow [a-zA-Z0-9_-]; dots in capability ids become double underscores."""
    safe_name = _TOOL_NAME_UNSAFE.sub("_", capability_id.replace(".", "__"))
    return safe_name[:TOOL_NAME_MAX_LENGTH]


def capability_tool_schema(capability: Capability) -> dict[str, Any]:
    """A tool definition a calling agent can use to invoke this capability."""
    return {
        "name": tool_name_for(capability.id),
        "description": _tool_description(capability),
        "input_schema": capability_input_schema(capability),
    }


def capability_input_schema(capability: Capability) -> dict[str, Any]:
    properties = {name: _input_property(spec) for name, spec in capability.inputs.items()}
    required = [name for name, spec in capability.inputs.items() if spec.required]
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def capability_result_schema(capability: Capability) -> dict[str, Any]:
    """JSON schema of the `outputs` object returned with status 'success'."""
    return {
        "type": "object",
        "properties": {name: _output_property(spec) for name, spec in capability.outputs.items()},
        "required": list(capability.outputs),
    }


def _input_property(spec: InputSpec) -> dict[str, Any]:
    schema = dict(_INPUT_TYPE_SCHEMAS[spec.type])
    if spec.pattern is not None and spec.type == "string":
        schema["pattern"] = spec.pattern
    if spec.example is not None:
        schema["examples"] = [spec.example]
    schema["description"] = spec.description + (SENSITIVE_NOTE if spec.sensitive else "")
    return schema


def _output_property(spec: OutputSpec) -> dict[str, Any]:
    schema = dict(_OUTPUT_TYPE_SCHEMAS[spec.type])
    suffix = schema.pop("description_suffix", "")
    schema["description"] = spec.description + suffix + (SENSITIVE_NOTE if spec.sensitive else "")
    return schema


def _tool_description(capability: Capability) -> str:
    parts = [
        f"{capability.title}. {capability.description}",
        f"Capability '{capability.id}' version {capability.version} ({capability.status}).",
        _outputs_sentence(capability),
        _outcomes_sentence(capability),
        _risk_sentence(capability),
        RESULT_CONTRACT_SENTENCE,
    ]
    return " ".join(part for part in parts if part)


def _outputs_sentence(capability: Capability) -> str:
    if not capability.outputs:
        return "Returns no outputs."
    rendered = ", ".join(f"{name} ({spec.type})" for name, spec in capability.outputs.items())
    return f"On success returns: {rendered}."


def _outcomes_sentence(capability: Capability) -> str:
    if not capability.outcomes:
        return ""
    rendered = "; ".join(f"{detector.code}: {detector.description}" for detector in capability.outcomes)
    return f"Possible business outcomes: {rendered}"


def _risk_sentence(capability: Capability) -> str:
    risky_steps = [step.id for step in capability.steps if step.risk == "risky"]
    if not risky_steps:
        return ""
    return (
        f"Contains irreversible steps ({', '.join(risky_steps)}): runs only when the capability is approved "
        "and the caller confirms (risky_confirmed)."
    )
