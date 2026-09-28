"""Planner selection: local model for development, Claude for the production evidence run."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from hands.discovery import CassettePlanner, Planner

PlannerChoice = Literal["ollama", "anthropic", "scripted"]
CassetteChoice = Literal["off", "record", "replay"]


def build_planner(
    choice: PlannerChoice,
    model: str | None,
    tenant: str,
    cassette_path: Path | None,
    cassette_mode: CassetteChoice,
) -> Planner:
    """Build the inner planner and optionally wrap it in a record/replay cassette."""
    inner = None if cassette_mode == "replay" else _inner_planner(choice, model, tenant)
    if cassette_mode == "off" or cassette_path is None:
        return inner if inner is not None else _inner_planner(choice, model, tenant)
    return CassettePlanner(inner, cassette_path, cassette_mode)


def _inner_planner(choice: PlannerChoice, model: str | None, tenant: str) -> Planner:
    if choice == "ollama":
        from hands.discovery.planners.ollama import OllamaPlanner

        return OllamaPlanner(model=model or "qwen3-vl:8b")
    if choice == "anthropic":
        from hands.discovery.planners.anthropic import AnthropicPlanner

        return AnthropicPlanner(model=model or "claude-sonnet-5")
    from hands.discovery.planners.scripted import coreone_member_balance_script

    return coreone_member_balance_script(tenant)
