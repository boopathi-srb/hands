"""End-to-end guarantee: a registered secret never reaches disk through any recorder write path."""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote, quote_plus

from evidence_helpers import all_bytes_under, login_observation, make_recorder, white_png
from pydantic import BaseModel

from hands.core.actions import TypeAction
from hands.core.observation import Dialog
from hands.evidence import EventKind
from hands.redact import Redactor

SECRET = "Pa$$ w0rd&<vault>"
SSN = "123-45-6789"


class ResultLike(BaseModel):
    message: str
    outputs: dict[str, str]


def _leak_forms() -> list[bytes]:
    forms = {
        SECRET,
        quote(SECRET, safe=""),
        quote_plus(SECRET),
        json.dumps(SECRET)[1:-1],
        html.escape(SECRET),
        SSN,
    }
    return [form.encode("utf-8") for form in forms]


def test_registered_secret_never_survives_any_write_path(tmp_path: Path) -> None:
    redactor = Redactor()
    redactor.register_secret(SECRET, "credential.password")
    recorder = make_recorder(tmp_path, redactor=redactor)

    observation = login_observation(SECRET, screenshot_png=white_png()).model_copy(
        update={"dialogs": [Dialog(title=f"Echo {SECRET}", text=f"SSN {SSN}")]}
    )
    recorder.event(EventKind.RUN_STARTED, goal=f"log in with {SECRET}", ssn=SSN)
    recorder.event(
        EventKind.ACTION, action=TypeAction(text=SECRET), nested={"deep": [SECRET, {"x": SECRET}]}
    )
    recorder.event(EventKind.OBSERVATION, observation=observation)
    recorder.event(
        f"kind-{SECRET}", url=f"http://127.0.0.1:8700/t/lakeside/login?pw={quote_plus(SECRET)}"
    )
    recorder.snapshot(f"after {SECRET}", observation)
    recorder.screenshot(f"shot {SECRET}", white_png())
    recorder.write_json(f"result-{SECRET}", ResultLike(message=SECRET, outputs={"ssn": SSN}))
    recorder.write_json("artifact", {"password": SECRET, "json_blob": json.dumps({"pw": SECRET})})
    recorder.summary()

    written = all_bytes_under(Path(recorder.run_dir))
    file_names = " ".join(str(path) for path in Path(recorder.run_dir).rglob("*")).encode("utf-8")
    for leak in _leak_forms():
        assert leak not in written, leak
        assert leak not in file_names, leak
    assert b"[REDACTED:credential.password]" in written


def test_secret_registered_after_the_recorder_is_created_is_still_masked(tmp_path: Path) -> None:
    redactor = Redactor()
    recorder = make_recorder(tmp_path, redactor=redactor)
    redactor.register_secret("late-secret-123", "input.answer")
    recorder.event(EventKind.HUMAN_ACTION, note="typed late-secret-123")
    assert b"late-secret-123" not in all_bytes_under(Path(recorder.run_dir))
