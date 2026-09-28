"""Unit tests for the composition root: credentials, run ids, planner selection, CLI parsing, commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from hands.cli import _choice, _parse_pairs, app
from hands.runtime.assembly import SessionOptions, build_session
from hands.runtime.commands import (
    RESULT_EXIT_CODES,
    DiscoverRequest,
    _infer_input_spec,
    catalog_list,
    catalog_set_status,
    catalog_tools,
    run_discover,
    run_replay,
    ReplayRequest,
)
from hands.runtime.credentials import EnvCredentialProvider, credential_env_name
from hands.runtime.planners import build_planner
from hands.runtime.run_ids import new_run_id

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = REPO_ROOT / "policies" / "coreone.yaml"
PROFILE = REPO_ROOT / "profiles" / "coreone.yaml"
GOAL = "Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance."


# ---------------------------------------------------------------- credentials


def test_credential_env_name_is_upper_snake() -> None:
    assert credential_env_name("teller", "password") == "HANDS_CRED_TELLER_PASSWORD"


def test_env_credential_prefers_configured_value() -> None:
    provider = EnvCredentialProvider({"HANDS_CRED_TELLER_USERNAME": "teller9"})
    assert provider.get("teller", "username") == "teller9"


def test_env_credential_demo_password_from_env_then_default() -> None:
    assert EnvCredentialProvider({"HANDS_DEMO_PASSWORD": "p1"}).get("teller", "password") == "p1"
    assert EnvCredentialProvider({}).get("teller", "password") == "demo-only-password"


def test_env_credential_unknown_returns_none() -> None:
    assert EnvCredentialProvider({}).get("vault", "token") is None


def test_env_credential_empty_value_falls_back() -> None:
    assert EnvCredentialProvider({"HANDS_CRED_TELLER_USERNAME": ""}).get("teller", "username") == "teller1"


# ---------------------------------------------------------------- run ids


def test_run_ids_are_unique_prefixed_and_have_no_long_digit_runs() -> None:
    run_ids = [new_run_id("replay") for _ in range(200)]
    assert len(set(run_ids)) == 200
    for run_id in run_ids:
        assert run_id.startswith("replay-")
        assert not any(run_id[i : i + 5].isdigit() for i in range(len(run_id) - 4))


# ---------------------------------------------------------------- planners


def test_build_planner_scripted_without_cassette() -> None:
    planner = build_planner("scripted", None, "lakeside", None, "off")
    assert planner is not None


def test_build_planner_replay_cassette_needs_no_inner(tmp_path: Path) -> None:
    planner = build_planner("anthropic", None, "lakeside", tmp_path / "c.jsonl", "replay")
    assert type(planner).__name__ == "CassettePlanner"


def test_build_planner_off_mode_ignores_cassette_path(tmp_path: Path) -> None:
    planner = build_planner("ollama", "qwen3-vl:8b", "lakeside", tmp_path / "c.jsonl", "off")
    assert type(planner).__name__ == "OllamaPlanner"


# ---------------------------------------------------------------- cli parsing


def test_parse_pairs_accepts_equals_in_value() -> None:
    assert _parse_pairs(["a=1", "b=x=y", "c="]) == {"a": "1", "b": "x=y", "c": ""}


def test_parse_pairs_empty_list() -> None:
    assert _parse_pairs([]) == {}


@pytest.mark.parametrize("bad", ["novalue", "=1"])
def test_parse_pairs_rejects_malformed(bad: str) -> None:
    with pytest.raises(typer.BadParameter):
        _parse_pairs([bad])


def test_choice_rejects_unknown_value() -> None:
    from hands.runtime.planners import PlannerChoice

    assert _choice("ollama", PlannerChoice) == "ollama"
    with pytest.raises(typer.BadParameter):
        _choice("gpt", PlannerChoice)


def test_cli_help_lists_verbs() -> None:
    output = CliRunner().invoke(app, ["--help"]).output
    for verb in ("discover", "replay", "catalog", "observe-desktop"):
        assert verb in output


# ---------------------------------------------------------------- commands


def test_infer_input_spec_digits_become_patterned_strings() -> None:
    spec = _infer_input_spec("member_number", "10001", sensitive=False)
    assert spec.type == "string" and spec.pattern == r"^\d+$" and spec.example == "10001"


def test_infer_input_spec_sensitive_hides_example() -> None:
    spec = _infer_input_spec("ssn", "123-45-6789", sensitive=True)
    assert spec.sensitive and spec.example is None and spec.pattern is None


def test_result_exit_codes_cover_every_status() -> None:
    assert set(RESULT_EXIT_CODES) == {"success", "business_outcome", "escalated", "failed"}


def test_catalog_on_empty_dir(tmp_path: Path) -> None:
    assert catalog_list(tmp_path) == []
    assert catalog_tools(tmp_path) == []
    assert catalog_set_status(tmp_path, "missing", None, "approved").exit_code == 2


async def test_build_session_reports_bad_policy(tmp_path: Path) -> None:
    options = SessionOptions(mode="replay", run_id="replay-abc", evidence_root=tmp_path,
                             policy_path=tmp_path / "missing.yaml", surface="fake", escalation="none")
    built = await build_session(options)
    assert built.session is None and "policy" in (built.error or "")


def _options(tmp_path: Path, mode: str, run_id: str) -> SessionOptions:
    return SessionOptions(mode=mode, run_id=run_id, evidence_root=tmp_path / "runs",  # type: ignore[arg-type]
                          policy_path=POLICY, surface="fake", escalation="none")


async def test_discover_then_replay_on_fake_surface(tmp_path: Path) -> None:
    """Integration happy path plus failure paths through the command layer (fake surface, scripted planner)."""
    discover = DiscoverRequest(
        goal=GOAL, entry_point="http://127.0.0.1:8700/t/lakeside/login", inputs={"member_number": "10001"},
        sensitive_inputs=[], capability_id="coreone.member_balance", title="Member savings balance",
        description="Balance lookup.", tenant="lakeside", planner="scripted", model=None, cassette_path=None,
        cassette_mode="off", max_steps=25, session=_options(tmp_path, "discovery", "disc-abc"),
        profile_path=PROFILE, artifacts_dir=tmp_path / "artifacts",
    )
    discovered = await run_discover(discover)
    assert discovered.exit_code == 0, discovered.summary
    assert catalog_tools(tmp_path / "artifacts")[0]["name"]

    async def replay(member_number: str, run_id: str) -> dict[str, object]:
        request = ReplayRequest(
            capability_id="coreone.member_balance", version=None, inputs={"member_number": member_number},
            tenant=None, risky_confirmed=False, faults=[], target_url="http://127.0.0.1:1",
            session=_options(tmp_path, "replay", run_id), artifacts_dir=tmp_path / "artifacts",
        )
        return (await run_replay(request)).summary

    assert (await replay("10002", "replay-aa"))["outputs"] == {"savings_balance": "9870.12"}
    assert (await replay("99999", "replay-bb"))["code"] == "MEMBER_NOT_FOUND"
    failed = await replay("abc", "replay-cc")
    assert failed["status"] == "failed" and failed["failure"]["code"] == "invalid_input"  # type: ignore[index]
    stats = json.loads((tmp_path / "artifacts" / "coreone.member_balance" / "1.0.0.json").read_text())["stats"]
    assert stats["runs"] == 3


async def test_replay_unknown_capability_is_an_error(tmp_path: Path) -> None:
    request = ReplayRequest(capability_id="nope", version=None, inputs={}, tenant=None, risky_confirmed=False,
                            faults=[], target_url="http://127.0.0.1:1",
                            session=_options(tmp_path, "replay", "replay-dd"), artifacts_dir=tmp_path)
    outcome = await run_replay(request)
    assert outcome.exit_code == 2 and outcome.summary["status"] == "error"
