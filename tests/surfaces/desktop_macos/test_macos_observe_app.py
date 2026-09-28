"""observe_app / CLI: the evidence path proving a native app yields the core Observation model."""

import json
from pathlib import Path

import pytest
from macos_ax_fakes import BUNDLE_ID, calculator_app, form_scenario, make_surface, tiny_png

from hands.core.observation import Observation
from hands.surfaces.desktop_macos import __main__ as cli
from hands.surfaces.desktop_macos import observe_app as observe_app_module
from hands.surfaces.desktop_macos.observe_app import (
    ObserveOutcome,
    observe_app,
    observe_app_to_json,
    screenshot_path_for,
    write_observation,
)


async def test_permission_missing_is_a_typed_outcome(tmp_path: Path) -> None:
    kit = make_surface(calculator_app(), trusted=False)
    outcome = await observe_app(BUNDLE_ID, str(tmp_path / "obs.json"), surface=kit.surface)
    assert outcome.status == "permission_missing"
    assert "Privacy & Security > Accessibility" in outcome.message
    assert not (tmp_path / "obs.json").exists()
    assert kit.apps.launched == []


async def test_ok_writes_observation_json_and_screenshot(tmp_path: Path) -> None:
    kit = make_surface(form_scenario().app)
    out_path = tmp_path / "nested" / "obs.json"
    outcome = await observe_app(BUNDLE_ID, str(out_path), surface=kit.surface)
    assert outcome.status == "ok"
    assert outcome.window_title == "New Member"
    assert outcome.dialog_count == 2
    assert outcome.screenshot_path == str(tmp_path / "nested" / "obs.png")
    assert Path(outcome.screenshot_path).read_bytes() == tiny_png()
    reloaded = Observation.model_validate_json(out_path.read_text())
    assert len(reloaded.nodes) == outcome.node_count > 0
    assert reloaded.location.kind == "window"
    assert "screenshot_png" not in json.loads(out_path.read_text())


async def test_ok_without_screenshot_mentions_screen_recording(tmp_path: Path) -> None:
    kit = make_surface(calculator_app())
    kit.capturer.error = "denied"
    outcome = await observe_app(BUNDLE_ID, str(tmp_path / "obs.json"), surface=kit.surface)
    assert outcome.status == "ok" and outcome.screenshot_path is None
    assert "Screen Recording" in outcome.message


async def test_quit_if_launched_only_quits_apps_we_started(tmp_path: Path) -> None:
    started = make_surface(calculator_app(), running=False)
    outcome = await observe_app(
        BUNDLE_ID, str(tmp_path / "a.json"), surface=started.surface, quit_if_launched=True
    )
    assert outcome.launched_by_us is True
    assert started.apps.terminated == [BUNDLE_ID]
    attached = make_surface(calculator_app())
    outcome = await observe_app(
        BUNDLE_ID, str(tmp_path / "b.json"), surface=attached.surface, quit_if_launched=True
    )
    assert outcome.launched_by_us is False
    assert attached.apps.terminated == []


async def test_launch_failure_outcome(tmp_path: Path) -> None:
    kit = make_surface(calculator_app(), running=False)
    kit.apps.launch_ok = False
    outcome = await observe_app(BUNDLE_ID, str(tmp_path / "obs.json"), surface=kit.surface)
    assert outcome.status == "launch_failed"


async def test_write_failure_outcome(tmp_path: Path) -> None:
    kit = make_surface(calculator_app())
    blocker = tmp_path / "is_a_file"
    blocker.write_text("x")
    outcome = await observe_app(BUNDLE_ID, str(blocker / "obs.json"), surface=kit.surface)
    assert outcome.status == "write_failed"


def test_write_observation_without_screenshot(tmp_path: Path) -> None:
    observation = Observation.model_validate(
        {
            "observed_at": "2026-01-01T00:00:00Z",
            "location": {"kind": "window", "value": "x"},
            "nodes": [],
            "fingerprint": "f",
        }
    )
    assert write_observation(observation, tmp_path / "o.json") is None
    assert screenshot_path_for(tmp_path / "o.json") == tmp_path / "o.png"


def test_observe_app_to_json_uses_real_surface_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    kit = make_surface(calculator_app(), trusted=False)
    monkeypatch.setattr(observe_app_module, "MacDesktopSurface", lambda: kit.surface)
    outcome = observe_app_to_json(BUNDLE_ID, str(tmp_path / "obs.json"))
    assert outcome.status == "permission_missing"


def test_cli_parse_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = cli.parse_arguments(["com.apple.calculator", "/tmp/o.json", "--quit-if-launched"])
    assert (arguments.bundle_id, arguments.out_path, arguments.quit_if_launched) == (
        "com.apple.calculator",
        "/tmp/o.json",
        True,
    )
    assert cli.exit_code_for(ObserveOutcome(status="ok", bundle_id="x", message="")) == 0
    assert (
        cli.exit_code_for(ObserveOutcome(status="permission_missing", bundle_id="x", message=""))
        == 2
    )
    assert cli.exit_code_for(ObserveOutcome(status="launch_failed", bundle_id="x", message="")) == 1
    monkeypatch.setattr(
        cli,
        "observe_app_to_json",
        lambda bundle_id, out_path, quit_if_launched: ObserveOutcome(
            status="permission_missing", bundle_id=bundle_id, message="grant it"
        ),
    )
    assert cli.main(["com.apple.calculator", "/tmp/o.json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "permission_missing"
