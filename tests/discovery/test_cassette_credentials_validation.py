from __future__ import annotations

from pathlib import Path

from hands.core.actions import OpenAction, PressAction, ScrollAction, SelectAction, TypeAction
from hands.discovery.cassette import CassettePlanner, context_key, load_cassette
from hands.discovery.credentials import SecretBook, expand_credential_names
from hands.discovery.planner import PlannerDecision
from hands.discovery.validation import (
    DecisionRejection,
    ValidatedDecision,
    ValidationInputs,
    normalize_ref,
    validate_decision,
)

from .helpers import (
    DictCredentials,
    SequencePlanner,
    make_node,
    make_observation,
    planner_context,
    respond,
)

# ---------------------------------------------------------------- cassette


async def test_cassette_record_then_replay_offline(tmp_path: Path) -> None:
    path = tmp_path / "cassettes" / "run.jsonl"
    inner = SequencePlanner([respond("click", node_ref="n1"), respond("done")])
    recorder = CassettePlanner(inner, path, "record")
    first_context, second_context = planner_context("screen A"), planner_context("screen B")
    recorded = [await recorder.decide(first_context), await recorder.decide(second_context)]
    replayer = CassettePlanner(None, path, "replay")
    replayed = [await replayer.decide(first_context), await replayer.decide(second_context)]
    assert replayed == recorded
    assert replayer.hits == 2 and replayer.misses == 0
    assert len(path.read_text().splitlines()) == 2


async def test_cassette_replay_miss_is_an_error_response(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    await CassettePlanner(SequencePlanner([respond("done")]), path, "record").decide(planner_context("A"))
    replayer = CassettePlanner(None, path, "replay")
    response = await replayer.decide(planner_context("never seen"))
    assert response.decision is None and response.error is not None and "cassette miss" in response.error
    assert replayer.misses == 1


async def test_cassette_serves_repeated_contexts_in_order(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    recorder = CassettePlanner(SequencePlanner([respond("press", key="Tab"), respond("done")]), path, "record")
    context = planner_context("same screen")
    await recorder.decide(context)
    await recorder.decide(context)
    replayer = CassettePlanner(None, path, "replay")
    actions = [(await replayer.decide(context)).decision for _ in range(3)]
    assert [decision.action for decision in actions if decision] == ["press", "done", "done"]


async def test_cassette_record_starts_fresh_file(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text("old line\n")
    await CassettePlanner(SequencePlanner([respond("done")]), path, "record").decide(planner_context("A"))
    assert "old line" not in path.read_text()


async def test_cassette_passthrough_and_missing_inner(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    passthrough = CassettePlanner(SequencePlanner([respond("done")]), path, "passthrough")
    assert (await passthrough.decide(planner_context("A"))).decision is not None
    assert not path.exists()
    no_inner = await CassettePlanner(None, path, "record").decide(planner_context("A"))
    assert no_inner.error is not None and "inner planner" in no_inner.error


def test_context_key_ignores_screenshot_and_clock_text() -> None:
    base = planner_context("Signed on 09:41 on 2026-09-28")
    same = planner_context("Signed on 10:05 on 2026-10-01", screenshot_png=None)
    assert context_key(base) == context_key(same)
    assert context_key(base) != context_key(planner_context("Other screen"))
    first_image = planner_context("screen", screenshot_png=b"image one")
    second_image = planner_context("screen", screenshot_png=b"image two")
    assert context_key(first_image) == context_key(second_image)


def test_load_cassette_skips_bad_lines_and_missing_file(tmp_path: Path) -> None:
    assert load_cassette(tmp_path / "missing.jsonl") == {}
    path = tmp_path / "bad.jsonl"
    path.write_text("\nnot json\n{\"key\": \"k\", \"response\": {}}\n")
    assert list(load_cassette(path)) == ["k"]


# ---------------------------------------------------------------- credentials


def test_expand_credential_names() -> None:
    assert expand_credential_names(["teller", "teller.pin", " ", "teller"]) == [
        "teller.username", "teller.password", "teller.pin",
    ]
    assert expand_credential_names([]) == []


def test_secret_book_resolves_registers_and_masks() -> None:
    registered: list[tuple[str, str]] = []
    book = SecretBook.resolve(DictCredentials(), ["teller", "vault.token"],
                              lambda value, label: registered.append((value, label)))
    assert book.names == ["teller.username", "teller.password"]
    assert book.placeholders == ["{{teller.username}}", "{{teller.password}}"]
    assert [label for _value, label in registered] == ["teller.username", "teller.password"]
    assert book.contains_secret("my teller1 login") and not book.contains_secret(None)
    assert "teller1" not in book.mask("user teller1")
    assert book.mask_optional(None) is None


# ---------------------------------------------------------------- validation


def _inputs(**overrides: object) -> ValidationInputs:
    observation = make_observation([
        make_node("n1", "textbox", label="Member Number", text=""),
        make_node("n2", "button", "Search"),
        make_node("n3", "button", "Locked", enabled=False),
        make_node("n4", "cell", "1,250.00"),
        make_node("n5", "cell", ""),
        make_node("n6", "combobox", label="Share Type", text=""),
    ])
    secrets = SecretBook({"teller.username": "teller1", "teller.password": "pw-123456"})
    fields: dict[str, object] = {"observation": observation, "input_values": {"member_number": "10001"},
                                 "secrets": secrets}
    fields.update(overrides)
    return ValidationInputs(**fields)  # type: ignore[arg-type]


def _check(**decision_fields: object) -> ValidatedDecision | DecisionRejection:
    rationale = str(decision_fields.pop("rationale", "r"))
    return validate_decision(PlannerDecision(rationale=rationale, **decision_fields), _inputs())  # type: ignore[arg-type]


def _feedback(**decision_fields: object) -> str:
    outcome = _check(**decision_fields)
    assert isinstance(outcome, DecisionRejection), outcome
    return outcome.feedback


def test_type_resolves_placeholders_but_keeps_template() -> None:
    outcome = _check(action="type", node_ref="n1", value="{{member_number}}")
    assert isinstance(outcome, ValidatedDecision)
    assert outcome.value_template == "{{member_number}}"
    assert outcome.surface_action == TypeAction(text="10001")
    credential = _check(action="type", node_ref="n1", value="{{teller.password}}")
    assert isinstance(credential, ValidatedDecision) and credential.surface_action == TypeAction(text="pw-123456")
    assert credential.value_template == "{{teller.password}}"


def test_literal_credential_value_is_rejected() -> None:
    assert "never type credential values" in _feedback(action="type", node_ref="n1", value="pw-123456")


def test_unknown_placeholder_and_missing_fields() -> None:
    assert "unknown placeholder {{teller.pin}}" in _feedback(action="type", node_ref="n1", value="{{teller.pin}}")
    assert "needs a value" in _feedback(action="type", node_ref="n1")
    assert "needs node_ref" in _feedback(action="click")
    assert "needs option" in _feedback(action="select", node_ref="n6")
    assert "needs key" in _feedback(action="press")
    assert "needs a value" in _feedback(action="open")


def test_unknown_ref_disabled_node_and_wrong_role() -> None:
    assert "not on the current SCREEN" in _feedback(action="click", node_ref="n99")
    assert "disabled" in _feedback(action="click", node_ref="n3")
    assert "not a text field" in _feedback(action="type", node_ref="n2", value="x")


def test_extract_rules() -> None:
    assert "snake_case" in _feedback(action="extract", node_ref="n4", output_name="Balance")
    assert "snake_case" in _feedback(action="extract", node_ref="n4")
    assert "no text" in _feedback(action="extract", node_ref="n5", output_name="empty")
    outcome = _check(action="extract", node_ref="n4", output_name="savings_balance")
    assert isinstance(outcome, ValidatedDecision) and outcome.surface_action is None


def test_plain_surface_actions() -> None:
    select = _check(action="select", node_ref="n6", option="Money Market")
    assert isinstance(select, ValidatedDecision) and select.surface_action == SelectAction(option="Money Market")
    press = _check(action="press", key="Enter")
    assert isinstance(press, ValidatedDecision) and press.surface_action == PressAction(key="Enter")
    scroll_up = _check(action="scroll", value="UP")
    assert isinstance(scroll_up, ValidatedDecision) and scroll_up.surface_action == ScrollAction(direction="up")
    scroll_default = _check(action="scroll")
    assert isinstance(scroll_default, ValidatedDecision)
    assert scroll_default.surface_action == ScrollAction(direction="down")
    opened = _check(action="open", value="http://x/member/{{member_number}}")
    assert isinstance(opened, ValidatedDecision)
    assert opened.surface_action == OpenAction(entry_point="http://x/member/10001")


def test_disallowed_action() -> None:
    outcome = validate_decision(PlannerDecision(rationale="r", action="open", value="http://x"),
                                _inputs(allowed_actions=frozenset({"click"})))
    assert isinstance(outcome, DecisionRejection) and "not allowed" in outcome.feedback


def test_normalize_ref_variants() -> None:
    observation = _inputs().observation
    for raw_ref in ("n2", "[n2]", " n2 ", "2"):
        node = normalize_ref(raw_ref, observation)
        assert node is not None and node.ref == "n2"
    assert normalize_ref("", observation) is None
