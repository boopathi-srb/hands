"""Deterministic replay: an agent invokes a Capability by name with typed inputs; no LLM is involved.

Public API
    ReplayEngine(surface, policy, evidence, credentials, escalator=None, secret_registrar=None, ...)
    await engine.run(capability, inputs, tenant_id=..., aliases=..., risky_confirmed=..., ...) -> RunResult

The result is one of SuccessResult / BusinessOutcomeResult / EscalatedResult / FailedResult
(hands.core.results). Recoverable interruptions never surface as a status; they are recorded on StepTraces.
"""

from hands.replay.engine import ReplayEngine, new_run_id
from hands.replay.values import Coerced, CoercionError, coerce_value

__all__ = ["Coerced", "CoercionError", "ReplayEngine", "coerce_value", "new_run_id"]
