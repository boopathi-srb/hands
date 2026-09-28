"""App control, window-id matching, screencapture and the subprocess runner (all mocked except `run_command`)."""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest
from macos_ax_fakes import tiny_png

from hands.surfaces.desktop_macos import apps as apps_module
from hands.surfaces.desktop_macos.apps import (
    MacAppController,
    pick_window_id,
    window_frame_distance,
)
from hands.surfaces.desktop_macos.ax import AxPoint, AxSize
from hands.surfaces.desktop_macos.capture import ScreencaptureCli, read_png, screencapture_argv
from hands.surfaces.desktop_macos.process import CommandResult, run_command

ORIGIN, SIZE = AxPoint(100, 200), AxSize(300, 400)


def window_info(
    pid: int, number: int, x: float, y: float, w: float, h: float, layer: int = 0
) -> dict[str, Any]:
    return {
        "kCGWindowOwnerPID": pid,
        "kCGWindowNumber": number,
        "kCGWindowLayer": layer,
        "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h},
    }


# ---------------------------------------------------------------- window id matching


def test_window_frame_distance() -> None:
    assert window_frame_distance(window_info(1, 1, 100, 200, 300, 400), ORIGIN, SIZE) == 0
    assert window_frame_distance(window_info(1, 1, 101, 199, 300, 402), ORIGIN, SIZE) == 4
    assert window_frame_distance({}, AxPoint(0, 0), AxSize(0, 0)) == 0


def test_pick_window_id_best_bounds_match() -> None:
    infos = [
        window_info(9, 1, 0, 0, 10, 10),
        window_info(9, 2, 100, 200, 300, 400),
        window_info(8, 3, 100, 200, 300, 400),
    ]
    assert pick_window_id(infos, 9, ORIGIN, SIZE) == 2


def test_pick_window_id_falls_back_to_first_owned_normal_window() -> None:
    infos = [
        window_info(9, 5, 0, 0, 10, 10, layer=25),
        window_info(9, 6, 0, 0, 10, 10),
        window_info(9, 7, 1, 1, 1, 1),
    ]
    assert pick_window_id(infos, 9, ORIGIN, SIZE) == 6


def test_pick_window_id_none_when_pid_owns_nothing() -> None:
    assert pick_window_id([], 9, ORIGIN, SIZE) is None
    assert pick_window_id([window_info(8, 1, 100, 200, 300, 400)], 9, ORIGIN, SIZE) is None


# ---------------------------------------------------------------- MacAppController


class StubRunningApp:
    def __init__(self, pid: int, activates: bool = True, terminates: bool = True) -> None:
        self.pid, self.activates, self.terminates = pid, activates, terminates

    def processIdentifier(self) -> int:
        return self.pid

    def activateWithOptions_(self, options: int) -> bool:
        return self.activates

    def terminate(self) -> bool:
        return self.terminates


class StubNSRunningApplication:
    apps: ClassVar[dict[str, list[StubRunningApp]]] = {}

    @classmethod
    def runningApplicationsWithBundleIdentifier_(cls, bundle_id: str) -> list[StubRunningApp]:
        return cls.apps.get(bundle_id, [])

    @classmethod
    def runningApplicationWithProcessIdentifier_(cls, pid: int) -> StubRunningApp | None:
        return next((app for apps in cls.apps.values() for app in apps if app.pid == pid), None)


class StubAppKit:
    NSRunningApplication = StubNSRunningApplication
    NSApplicationActivateIgnoringOtherApps = 2


class StubQuartzWindows:
    kCGWindowListOptionOnScreenOnly = 1
    kCGWindowListExcludeDesktopElements = 16
    kCGNullWindowID = 0

    def __init__(self, infos: list[dict[str, Any]]) -> None:
        self.infos = infos

    def CGWindowListCopyWindowInfo(self, options: int, window_id: int) -> list[dict[str, Any]]:
        return self.infos


class RecordingRunner:
    def __init__(self, result: CommandResult, write_png: bool = False) -> None:
        self.result = result
        self.write_png = write_png
        self.argvs: list[list[str]] = []

    async def __call__(self, argv: Sequence[str], timeout_s: float) -> CommandResult:
        self.argvs.append(list(argv))
        if self.write_png:
            Path(argv[-1]).write_bytes(tiny_png())
        return self.result


def controller(
    runner: RecordingRunner | None = None, infos: list[dict[str, Any]] | None = None
) -> MacAppController:
    return MacAppController(
        appkit_module=StubAppKit,  # type: ignore[arg-type]
        quartz_module=StubQuartzWindows(infos or []),  # type: ignore[arg-type]
        command_runner=runner or RecordingRunner(CommandResult(returncode=0)),
    )


@pytest.fixture(autouse=True)
def reset_running_apps() -> None:
    StubNSRunningApplication.apps = {"com.apple.calculator": [StubRunningApp(321)]}


def test_find_pid() -> None:
    assert controller().find_pid("com.apple.calculator") == 321
    assert controller().find_pid("com.missing") is None


async def test_launch_runs_open_b() -> None:
    runner = RecordingRunner(CommandResult(returncode=0))
    assert (await controller(runner).launch("com.apple.calculator")).ok
    assert runner.argvs == [["open", "-b", "com.apple.calculator"]]


async def test_launch_failure_is_reported() -> None:
    runner = RecordingRunner(CommandResult(returncode=1, stderr="Unable to find application"))
    result = await controller(runner).launch("com.missing")
    assert not result.ok and "Unable to find application" in (result.error or "")


def test_activate() -> None:
    assert controller().activate(321).ok
    assert not controller().activate(999).ok
    StubNSRunningApplication.apps["com.apple.calculator"][0].activates = False
    assert not controller().activate(321).ok


def test_terminate() -> None:
    assert controller().terminate("com.apple.calculator").ok
    assert controller().terminate("com.not.running").ok
    StubNSRunningApplication.apps["com.apple.calculator"][0].terminates = False
    assert not controller().terminate("com.apple.calculator").ok


def test_window_id_for() -> None:
    infos = [window_info(321, 77, 100, 200, 300, 400)]
    assert controller(infos=infos).window_id_for(321, ORIGIN, SIZE) == 77
    assert controller(infos=infos).window_id_for(999, ORIGIN, SIZE) is None


def test_controller_without_pyobjc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps_module, "_import_optional", lambda name: None)
    bare = MacAppController()
    assert bare.find_pid("com.apple.calculator") is None
    assert not bare.activate(1).ok
    assert bare.terminate("com.apple.calculator").ok
    assert bare.window_id_for(1, ORIGIN, SIZE) is None


def test_import_optional_handles_import_error() -> None:
    assert apps_module._import_optional("definitely_not_a_module_xyz") is None


# ---------------------------------------------------------------- capture


def test_screencapture_argv() -> None:
    assert screencapture_argv(42, "/tmp/x.png") == [
        "screencapture",
        "-l",
        "42",
        "-x",
        "-o",
        "-t",
        "png",
        "/tmp/x.png",
    ]


def test_read_png(tmp_path: Path) -> None:
    assert read_png(tmp_path / "missing.png").error is not None
    not_png = tmp_path / "bad.png"
    not_png.write_bytes(b"GIF89a")
    assert "not a PNG" in (read_png(not_png).error or "")
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert not read_png(empty).ok
    good = tmp_path / "good.png"
    good.write_bytes(tiny_png())
    assert read_png(good).png == tiny_png()


async def test_screencapture_cli_success() -> None:
    runner = RecordingRunner(CommandResult(returncode=0), write_png=True)
    capture = await ScreencaptureCli(runner).capture_window(42)
    assert capture.ok and capture.png == tiny_png()
    assert runner.argvs[0][:3] == ["screencapture", "-l", "42"]
    assert not Path(runner.argvs[0][-1]).exists()


async def test_screencapture_cli_command_failure() -> None:
    runner = RecordingRunner(
        CommandResult(returncode=1, stderr="could not create image from window")
    )
    capture = await ScreencaptureCli(runner).capture_window(42)
    assert not capture.ok and "could not create image" in (capture.error or "")


async def test_screencapture_cli_no_file_written() -> None:
    capture = await ScreencaptureCli(RecordingRunner(CommandResult(returncode=0))).capture_window(
        42
    )
    assert not capture.ok and "no file" in (capture.error or "")


# ---------------------------------------------------------------- run_command (real, harmless processes)


async def test_run_command_success() -> None:
    result = await run_command([sys.executable, "-c", "print('hi')"], 10)
    assert result.ok and result.stdout.strip() == "hi"


async def test_run_command_nonzero_exit() -> None:
    result = await run_command([sys.executable, "-c", "import sys; sys.exit(3)"], 10)
    assert not result.ok and result.returncode == 3 and result.error is None


async def test_run_command_missing_binary() -> None:
    result = await run_command(["/nonexistent/binary-xyz"], 10)
    assert not result.ok and result.returncode is None and "could not start" in (result.error or "")


async def test_run_command_timeout() -> None:
    result = await run_command([sys.executable, "-c", "import time; time.sleep(5)"], 0.2)
    assert not result.ok and "timed out" in (result.error or "")
