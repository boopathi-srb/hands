"""Discovery: a planner accomplishes a goal on a live UI once; the recorder turns the run into a Capability.

- planner      the Planner port (PlannerContext -> PlannerResponse with a strict PlannerDecision)
- planners     ScriptedPlanner, OllamaPlanner (local dev), AnthropicPlanner (prod evidence)
- cassette     CassettePlanner: record/replay planner responses offline
- render       observation -> compact, secret-free text + downscaled screenshot
- loop         DiscoveryAgent: observe, decide, validate, enforce policy, act, detect stuck, escalate
- recorder     record_capability: trace -> validated draft Capability
"""

from hands.discovery.cassette import CassettePlanner, context_key
from hands.discovery.loop import DiscoveryAgent, DiscoveryLimits
from hands.discovery.planner import (
    Planner,
    PlannerContext,
    PlannerDecision,
    PlannerResponse,
    TokenUsage,
    decision_json_schema,
)
from hands.discovery.recorder import RecordResult, record_capability
from hands.discovery.render import render_observation
from hands.discovery.trace import DiscoveryOutcome, TraceStep

__all__ = [
    "CassettePlanner",
    "DiscoveryAgent",
    "DiscoveryLimits",
    "DiscoveryOutcome",
    "Planner",
    "PlannerContext",
    "PlannerDecision",
    "PlannerResponse",
    "RecordResult",
    "TokenUsage",
    "TraceStep",
    "context_key",
    "decision_json_schema",
    "record_capability",
    "render_observation",
]
