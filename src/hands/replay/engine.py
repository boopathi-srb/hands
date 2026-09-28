"""ReplayEngine: invoke a Capability deterministically, without any LLM.

The engine is an orchestrator. Input validation lives in `inputs`, the wait loop in `waits`, outcome and
recovery monitors in `monitors`, per-step execution in `steps`, output reading in `extraction`, the final
checkpoint in `checkpoint`, human hand-off in `escalation`, and result building in `finish`.

It depends only on the core ports (Surface, PolicyGate, EvidenceSink, CredentialProvider, Escalator).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from hands.core.artifact import Capability
from hands.core.ports import CredentialProvider, Escalator, EvidenceSink, PolicyGate, Surface
from hands.core.results import RunResult
from hands.replay.context import (
    ReplayPorts,
    ReplayTiming,
    RunContext,
    RunInvocation,
    SecretRegistrar,
)
from hands.replay.finish import build_run_result, record_result, rejected_input_result
from hands.replay.inputs import InputRejected, prepare_params
from hands.replay.runner import bind_subflows, run_capability

DEFAULT_POLL_INTERVAL_MS = 250
DEFAULT_CHECKPOINT_TIMEOUT_MS = 10_000
DEFAULT_MAX_RESTARTS = 3


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


class ReplayEngine:
    """Runs capabilities against one live surface. One engine may run many capabilities sequentially."""

    def __init__(
        self,
        surface: Surface,
        policy: PolicyGate,
        evidence: EvidenceSink,
        credentials: CredentialProvider,
        escalator: Escalator | None = None,
        secret_registrar: SecretRegistrar | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = utc_now,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        checkpoint_timeout_ms: int = DEFAULT_CHECKPOINT_TIMEOUT_MS,
        max_restarts: int = DEFAULT_MAX_RESTARTS,
    ) -> None:
        self._ports = ReplayPorts(
            surface=surface,
            policy=policy,
            evidence=evidence,
            credentials=credentials,
            escalator=escalator,
            secret_registrar=secret_registrar,
        )
        self._timing = ReplayTiming(
            monotonic=monotonic,
            sleep=sleep,
            now=now,
            poll_interval_ms=max(1, poll_interval_ms),
            checkpoint_timeout_ms=checkpoint_timeout_ms,
        )
        self._max_restarts = max_restarts

    async def run(
        self,
        capability: Capability,
        inputs: Mapping[str, Any] | None,
        *,
        tenant_id: str | None = None,
        aliases: Mapping[str, str] | None = None,
        risky_confirmed: bool = False,
        session_id: str = "local",
        run_id: str | None = None,
        run_timeout_ms: int | None = None,
    ) -> RunResult:
        """Validate inputs, execute every step with monitors, verify the checkpoint, return a typed result."""
        started_at = self._timing.now()
        resolved_run_id = run_id or new_run_id()
        self._emit_run_started(capability, resolved_run_id, tenant_id, inputs)
        prepared = prepare_params(capability, inputs, self._ports.credentials, self._ports.secret_registrar)
        if isinstance(prepared, InputRejected):
            result: RunResult = rejected_input_result(
                prepared,
                run_id=resolved_run_id,
                capability_id=capability.id,
                capability_version=capability.version,
                tenant_id=tenant_id,
                started_at=started_at,
                finished_at=self._timing.now(),
                evidence_dir=self._ports.evidence.run_dir,
            )
        else:
            invocation = RunInvocation(
                capability=capability,
                params=prepared.params,
                aliases=dict(aliases or {}),
                tenant_id=tenant_id,
                session_id=session_id,
                run_id=resolved_run_id,
                risky_confirmed=risky_confirmed,
                started_at=started_at,
                run_deadline=self._run_deadline(run_timeout_ms),
                run_timeout_ms=run_timeout_ms,
            )
            result = await self._execute(invocation)
        record_result(self._ports.evidence, result)
        return result

    async def _execute(self, invocation: RunInvocation) -> RunResult:
        ctx = RunContext(self._ports, self._timing, invocation)
        bind_subflows(ctx)
        run_end = await run_capability(ctx, self._max_restarts)
        return build_run_result(ctx, run_end)

    def _run_deadline(self, run_timeout_ms: int | None) -> float | None:
        if run_timeout_ms is None:
            return None
        return self._timing.monotonic() + max(0, run_timeout_ms) / 1000

    def _emit_run_started(
        self, capability: Capability, run_id: str, tenant_id: str | None, inputs: Mapping[str, Any] | None
    ) -> None:
        self._ports.evidence.event(
            "run_started",
            run_id=run_id,
            mode="replay",
            capability_id=capability.id,
            capability_version=capability.version,
            capability_status=capability.status,
            tenant_id=tenant_id,
            input_names=sorted(inputs or {}),
        )
