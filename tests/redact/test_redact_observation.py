from __future__ import annotations

import pytest
from redact_helpers import node, observation_with, white_png

from hands.core.observation import Dialog, Location, Rect
from hands.redact import Redactor

SECRET = "demo-only-password"


@pytest.fixture
def redactor() -> Redactor:
    redactor = Redactor()
    redactor.register_secret(SECRET, "credential.password")
    return redactor


# ---------------------------------------------------------------- password fields


@pytest.mark.parametrize(
    "password_node",
    [
        node("n1", role="textbox", label="Password", value="anything at all"),
        node("n2", role="textbox", name="PIN", value="1234"),
        node("n3", role="AXSecureTextField", name="", value="hunter2"),
        node("n4", role="password", value="x"),
        node("n5", role="textbox", name="Passcode", value="x", text="x"),
    ],
)
def test_password_field_values_are_always_masked(redactor: Redactor, password_node) -> None:  # type: ignore[no-untyped-def]
    redacted = redactor.redact_node(password_node)
    assert redacted.value == "[REDACTED:password]"
    assert redacted.name == password_node.name
    assert redactor.node_needs_mask(password_node)


def test_password_field_text_is_masked_too(redactor: Redactor) -> None:
    redacted = redactor.redact_node(
        node("n1", role="textbox", name="Password", text="••••", value="abc")
    )
    assert redacted.text == "[REDACTED:password]"


def test_empty_password_value_stays_empty_but_is_still_masked_on_screen(redactor: Redactor) -> None:
    empty_field = node("n1", role="textbox", name="Password", value="")
    assert redactor.redact_node(empty_field).value == ""
    assert redactor.node_needs_mask(empty_field)


def test_password_buttons_are_not_password_fields(redactor: Redactor) -> None:
    change_button = node("n1", role="button", name="Change Password")
    assert redactor.redact_node(change_button) == change_button
    assert not redactor.node_needs_mask(change_button)


# ---------------------------------------------------------------- sensitive labelled fields


def test_sensitive_labelled_values_are_masked_whatever_their_format(redactor: Redactor) -> None:
    ssn_cell = node("n1", role="cell", label="SSN", text="xxx-xx-1234")
    dob_box = node("n2", role="textbox", name="Date of Birth", value="Jan the 2nd")
    assert redactor.redact_node(ssn_cell).text == "[REDACTED:sensitive_field]"
    assert redactor.redact_node(dob_box).value == "[REDACTED:sensitive_field]"


def test_label_cells_themselves_are_not_masked(redactor: Redactor) -> None:
    label_cell = node("n1", role="cell", name="SSN", text="SSN")
    assert redactor.redact_node(label_cell) == label_cell
    assert not redactor.node_needs_mask(label_cell)


# ---------------------------------------------------------------- free text


def test_registered_secret_is_masked_in_every_node_field(redactor: Redactor) -> None:
    leaky = node(
        "n1",
        role="cell",
        name=f"name {SECRET}",
        text=f"text {SECRET}",
        value=f"value {SECRET}",
        label=f"label {SECRET}",
    ).model_copy(update={"container_path": (f"frame:{SECRET}",)})
    redacted = redactor.redact_node(leaky)
    assert SECRET not in redacted.model_dump_json()
    assert redacted.ref == "n1" and redacted.role == "cell"


def test_ordinary_nodes_are_unchanged(redactor: Redactor) -> None:
    ordinary = node("n1", role="cell", text="Regular Savings", label="Description")
    assert redactor.redact_node(ordinary) == ordinary
    assert not redactor.node_needs_mask(ordinary)


def test_already_redacted_node_needs_mask(redactor: Redactor) -> None:
    assert redactor.node_needs_mask(node("n1", text="[REDACTED:ssn]"))


def test_redact_dialog_and_location(redactor: Redactor) -> None:
    dialog = Dialog(title=f"Hi {SECRET}", text="SSN 123-45-6789", native=True)
    redacted_dialog = redactor.redact_dialog(dialog)
    assert redacted_dialog.title == "Hi [REDACTED:credential.password]"
    assert redacted_dialog.text == "SSN [REDACTED:ssn]"
    assert redacted_dialog.native is True
    location = Location(
        kind="url", value=f"http://127.0.0.1:8700/t/lakeside/login?pw={SECRET}", title=SECRET
    )
    redacted_location = redactor.redact_location(location)
    assert SECRET not in redacted_location.value + redacted_location.title


def test_redact_observation_covers_nodes_dialogs_location_and_screenshot(
    redactor: Redactor,
) -> None:
    password_field = node(
        "n1",
        role="textbox",
        name="Password",
        value=SECRET,
        bounds=Rect(x=10, y=10, width=20, height=10),
    )
    observation = observation_with(
        [password_field, node("n2", text="Member 10001")],
        dialogs=[Dialog(title="Notice", text=f"typed {SECRET}")],
        location=Location(kind="url", value=f"http://127.0.0.1:8700/t/lakeside/x?q={SECRET}"),
        screenshot_png=white_png(),
    )
    redacted = redactor.redact_observation(observation)
    assert SECRET not in redacted.model_dump_json()
    assert redacted.nodes[1].text == "Member 10001"
    assert redacted.fingerprint == observation.fingerprint
    assert (
        redacted.screenshot_png is not None
        and redacted.screenshot_png != observation.screenshot_png
    )
    assert observation.nodes[0].value == SECRET  # the original is not mutated


def test_redact_observation_without_screenshot(redactor: Redactor) -> None:
    redacted = redactor.redact_observation(observation_with([]))
    assert redacted.screenshot_png is None
    assert redacted.nodes == []


def test_sensitive_rects_only_include_bounded_sensitive_nodes(redactor: Redactor) -> None:
    sensitive_bounds = Rect(x=1, y=2, width=3, height=4)
    observation = observation_with(
        [
            node("n1", role="textbox", name="Password", bounds=sensitive_bounds),
            node("n2", role="textbox", name="Password", bounds=None),
            node("n3", text="Regular Savings", bounds=Rect(x=5, y=5, width=5, height=5)),
        ]
    )
    assert redactor.sensitive_rects(observation) == [sensitive_bounds]
