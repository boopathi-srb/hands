"""`hands` CLI: discover a flow with a model, replay it without one, and browse the catalog."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from hands.runtime.assembly import EscalationMode, SessionOptions, SurfaceChoice
from hands.runtime.commands import (
    CommandOutcome,
    DiscoverRequest,
    ReplayRequest,
    catalog_list,
    catalog_merge_profile,
    catalog_set_status,
    catalog_tools,
    run_discover,
    run_replay,
)
from hands.runtime.planners import CassetteChoice, PlannerChoice
from hands.runtime.run_ids import new_run_id

app = typer.Typer(add_completion=False, help=__doc__, no_args_is_help=True)
catalog_app = typer.Typer(help="Browse and manage saved capabilities.", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")

DEFAULT_TARGET = "http://127.0.0.1:8700"
DEFAULT_EVIDENCE = Path("runs")
DEFAULT_ARTIFACTS = Path("artifacts")
DEFAULT_POLICY = Path("policies/coreone.yaml")
DEFAULT_PROFILE = Path("profiles/coreone.yaml")


def _parse_pairs(pairs: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for pair in pairs:
        name, separator, value = pair.partition("=")
        if not separator or not name:
            raise typer.BadParameter(f"expected name=value, got '{pair}'")
        parsed[name.strip()] = value
    return parsed


def _emit(outcome: CommandOutcome) -> None:
    typer.echo(json.dumps(outcome.summary, indent=2, default=str))
    raise typer.Exit(outcome.exit_code)


def _session_options(
    mode: str, evidence_root: Path, policy: Path, surface: SurfaceChoice, headed: bool,
    escalation: EscalationMode, console_port: int, tenant: str, risky_confirmed: bool = False,
) -> SessionOptions:
    prefix = "disc" if mode == "discovery" else "replay"
    return SessionOptions(
        mode="discovery" if mode == "discovery" else "replay", run_id=new_run_id(prefix),
        evidence_root=evidence_root, policy_path=policy, surface=surface, headless=not headed,
        escalation=escalation, console_port=console_port, fake_tenant=tenant, risky_confirmed=risky_confirmed,
    )


@app.command()
def discover(
    goal: str = typer.Argument(..., help="Natural-language goal. Use {{name}} to reference --input values."),
    entry: str = typer.Option(f"{DEFAULT_TARGET}/t/lakeside/login", help="Entry URL (web) or bundle id."),
    input_pairs: list[str] = typer.Option([], "--input", "-i", help="name=value for this run; becomes a typed input."),
    sensitive: list[str] = typer.Option([], help="Input names to treat as sensitive."),
    capability_id: str = typer.Option("coreone.member_balance", help="Id of the capability to record."),
    title: str = typer.Option("Member savings balance", help="Human title of the capability."),
    description: str = typer.Option(
        "Look up a member by member number and return the balance of their savings share.",
        help="What the capability does, for reviewers and calling agents."),
    tenant: str = typer.Option("lakeside", help="Tenant the discovery run is recorded on."),
    planner: str = typer.Option("ollama", help="ollama (dev), anthropic (prod), or scripted (offline)."),
    model: str | None = typer.Option(None, help="Override the planner model."),
    cassette: Path | None = typer.Option(None, help="JSONL cassette of planner responses."),
    cassette_mode: str = typer.Option("off", help="off, record, or replay (offline, no model calls)."),
    max_steps: int = typer.Option(25, help="Hard cap on model decisions."),
    surface: str = typer.Option("web", help="web (Playwright) or fake (in-memory CoreOne)."),
    headed: bool = typer.Option(False, help="Show the browser window."),
    escalation: str = typer.Option("console", help="console, scripted-resume, scripted-abort, or none."),
    console_port: int = typer.Option(8765, help="Operator console port."),
    evidence_root: Path = typer.Option(DEFAULT_EVIDENCE),
    artifacts_dir: Path = typer.Option(DEFAULT_ARTIFACTS),
    policy: Path = typer.Option(DEFAULT_POLICY),
    profile: Path = typer.Option(DEFAULT_PROFILE),
) -> None:
    """Run the model-driven discovery loop once and record the result as a capability artifact."""
    request = DiscoverRequest(
        goal=goal, entry_point=entry, inputs=_parse_pairs(input_pairs), sensitive_inputs=sensitive,
        capability_id=capability_id, title=title, description=description, tenant=tenant,
        planner=_choice(planner, PlannerChoice), model=model, cassette_path=cassette,
        cassette_mode=_choice(cassette_mode, CassetteChoice), max_steps=max_steps,
        session=_session_options("discovery", evidence_root, policy, _choice(surface, SurfaceChoice), headed,
                                 _choice(escalation, EscalationMode), console_port, tenant),
        profile_path=profile, artifacts_dir=artifacts_dir,
    )
    _emit(asyncio.run(run_discover(request)))


@app.command()
def replay(
    capability_id: str = typer.Argument(..., help="Capability id from the catalog."),
    input_pairs: list[str] = typer.Option([], "--input", "-i", help="name=value inputs."),
    version: str | None = typer.Option(None, help="Capability version; latest by default."),
    tenant: str | None = typer.Option(None, help="Tenant id; applies its overlay if one exists."),
    risky_confirmed: bool = typer.Option(False, help="Caller confirms risky steps (approved capabilities only)."),
    fault: list[str] = typer.Option([], help="Test harness: arm a mock-app fault first, e.g. session_expired:1."),
    target_url: str = typer.Option(DEFAULT_TARGET, help="Mock app base URL, used only to arm faults."),
    surface: str = typer.Option("web", help="web (Playwright) or fake (in-memory CoreOne)."),
    headed: bool = typer.Option(False, help="Show the browser window."),
    escalation: str = typer.Option("console", help="console, scripted-resume, scripted-abort, or none."),
    console_port: int = typer.Option(8765, help="Operator console port."),
    evidence_root: Path = typer.Option(DEFAULT_EVIDENCE),
    artifacts_dir: Path = typer.Option(DEFAULT_ARTIFACTS),
    policy: Path = typer.Option(DEFAULT_POLICY),
) -> None:
    """Replay a saved capability deterministically, with no model, and print the typed result."""
    request = ReplayRequest(
        capability_id=capability_id, version=version, inputs=_parse_pairs(input_pairs), tenant=tenant,
        risky_confirmed=risky_confirmed, faults=fault, target_url=target_url,
        session=_session_options("replay", evidence_root, policy, _choice(surface, SurfaceChoice), headed,
                                 _choice(escalation, EscalationMode), console_port, tenant or "lakeside",
                                 risky_confirmed),
        artifacts_dir=artifacts_dir,
    )
    _emit(asyncio.run(run_replay(request)))


@catalog_app.command("list")
def catalog_list_command(artifacts_dir: Path = typer.Option(DEFAULT_ARTIFACTS)) -> None:
    """List capabilities with their contracts and replay stats."""
    typer.echo(json.dumps(catalog_list(artifacts_dir), indent=2, default=str))


@catalog_app.command("tools")
def catalog_tools_command(artifacts_dir: Path = typer.Option(DEFAULT_ARTIFACTS)) -> None:
    """Print tool definitions a calling agent can use to invoke each capability."""
    typer.echo(json.dumps(catalog_tools(artifacts_dir), indent=2, default=str))


@catalog_app.command("approve")
def catalog_approve_command(
    capability_id: str, version: str | None = typer.Option(None),
    artifacts_dir: Path = typer.Option(DEFAULT_ARTIFACTS),
) -> None:
    """Mark a reviewed capability approved; only approved capabilities may run risky steps."""
    _emit(catalog_set_status(artifacts_dir, capability_id, version, "approved"))


@catalog_app.command("merge-profile")
def catalog_merge_profile_command(
    capability_id: str, profile: Path = typer.Option(DEFAULT_PROFILE),
    artifacts_dir: Path = typer.Option(DEFAULT_ARTIFACTS),
) -> None:
    """Re-apply the vendor app profile to a saved capability."""
    _emit(catalog_merge_profile(artifacts_dir, capability_id, profile))


@app.command("observe-desktop")
def observe_desktop(
    bundle_id: str = typer.Argument("com.apple.calculator"),
    out: Path = typer.Option(Path("evidence/desktop/calculator_observation.json")),
) -> None:
    """Observe a native macOS app through the Accessibility API into the same Observation model."""
    from hands.surfaces.desktop_macos.observe_app import observe_app_to_json

    outcome = observe_app_to_json(bundle_id, str(out))
    typer.echo(json.dumps(_as_jsonable(outcome), indent=2, default=str))
    raise typer.Exit(0 if getattr(outcome, "status", "") == "ok" else 1)


def _as_jsonable(value: Any) -> Any:
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else value


def _choice(value: str, literal_type: Any) -> Any:
    allowed = getattr(literal_type, "__args__", ())
    if value not in allowed:
        raise typer.BadParameter(f"'{value}' is not one of {list(allowed)}")
    return value


if __name__ == "__main__":
    app()
