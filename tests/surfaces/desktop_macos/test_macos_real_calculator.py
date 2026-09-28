"""Real AX backend against Calculator. Skipped unless this process has Accessibility permission."""

from pathlib import Path

import pytest

from hands.core.observation import Observation
from hands.surfaces.desktop_macos.ax import PyObjcAxBackend
from hands.surfaces.desktop_macos.observe_app import observe_app
from hands.surfaces.desktop_macos.surface import MacDesktopSurface

CALCULATOR = "com.apple.calculator"

pytestmark = [
    pytest.mark.desktop,
    pytest.mark.skipif(
        not PyObjcAxBackend().is_process_trusted(),
        reason="AXIsProcessTrusted() is false: grant Accessibility to the terminal running pytest",
    ),
]


async def test_calculator_yields_core_observation(tmp_path: Path) -> None:
    out_path = tmp_path / "calculator.json"
    outcome = await observe_app(
        CALCULATOR, str(out_path), surface=MacDesktopSurface(), quit_if_launched=True
    )
    assert outcome.status == "ok", outcome.message
    observation = Observation.model_validate_json(out_path.read_text())
    assert observation.location.value == CALCULATOR
    buttons = [node for node in observation.nodes if node.role == "button"]
    assert len(buttons) >= 10
    assert all(node.container_path[0].startswith("window:") for node in observation.nodes)
