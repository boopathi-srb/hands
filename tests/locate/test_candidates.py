from __future__ import annotations

import logging

import pytest

from hands.core.observation import Node, Observation
from hands.core.targets import (
    LabelCandidate,
    RoleNameCandidate,
    StructuralCandidate,
    TextAnchorCandidate,
    VisualAnchorCandidate,
)
from hands.locate import build_target_spec, generate_candidates, is_volatile_text, resolve_target
from hands.locate._nodes import is_interactive
from hands.locate.candidates import resolves_uniquely_to

from .fixtures import (
    all_fixture_observations,
    empty_observation,
    login_observation,
    make_node,
    make_observation,
    member_detail_observation,
)


def node_in(observation: Observation, ref: str) -> Node:
    node = observation.node_by_ref(ref)
    assert node is not None, ref
    return node


# ---------------------------------------------------------------- is_volatile_text


@pytest.mark.parametrize(
    "text",
    [
        "10001",
        "Member 10001",
        "ERR-5521",
        "1,250.00",
        "0.00",
        "$85",
        "2026-09-28",
        "09/28/2026",
        "Sep 28",
        "10:30",
    ],
)
def test_volatile_text(text: str) -> None:
    assert is_volatile_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        None,
        "Regular Savings",
        "Search",
        "teller1",
        "code 403-R",
        "CoreOne 7.4",
        "S1",
        "Share ID",
        "September",
    ],
)
def test_stable_text(text: str | None) -> None:
    assert not is_volatile_text(text)


# ---------------------------------------------------------------- each candidate kind


def test_role_name_candidate_first_for_named_button() -> None:
    observation = login_observation()
    candidates = generate_candidates(node_in(observation, "n12"), observation)
    first = candidates[0]
    assert isinstance(first, RoleNameCandidate)
    assert (first.role, first.name, first.exact, first.confidence) == (
        "button",
        "Sign On",
        True,
        0.9,
    )
    assert first.reason


def test_label_candidate_for_unnamed_legacy_input() -> None:
    observation = login_observation()
    candidates = generate_candidates(node_in(observation, "n6"), observation)
    first = candidates[0]
    assert isinstance(first, LabelCandidate)
    assert first.label == "User ID" and first.role == "textbox"
    assert first.confidence == pytest.approx(0.8)  # adjacency penalty
    assert "adjacent label cell" in first.reason


def test_explicit_label_has_no_penalty() -> None:
    field = make_node(
        "f", "combobox", label="Share Type", box=(100, 100, 120, 20), path="select[1]"
    )
    observation = make_observation([field])
    first = generate_candidates(field, observation)[0]
    assert isinstance(first, LabelCandidate) and first.confidence == pytest.approx(0.85)


def test_text_anchor_for_balance_cell_in_regular_savings_row() -> None:
    observation = member_detail_observation()
    balance_cell = node_in(observation, "r1c3")
    candidates = generate_candidates(balance_cell, observation)
    first = candidates[0]
    assert isinstance(first, TextAnchorCandidate)
    assert (first.anchor_text, first.relation, first.role, first.ordinal) == (
        "Regular Savings",
        "right_of",
        "cell",
        0,
    )
    assert first.confidence == pytest.approx(0.7)


def test_text_anchor_for_repeated_view_links() -> None:
    observation = member_detail_observation()
    checking_view = node_in(observation, "r2view")
    candidates = generate_candidates(checking_view, observation)
    assert not any(
        isinstance(candidate, RoleNameCandidate) for candidate in candidates
    )  # 'View' is not unique
    first = candidates[0]
    assert isinstance(first, TextAnchorCandidate) and first.anchor_text == "Checking"


def test_text_anchor_below_header_uses_ordinal_with_penalty() -> None:
    share_id_cell = make_node("id2", "cell", text="0014", box=(0, 40, 80, 20))
    observation = make_observation(
        [
            make_node("hdr", "cell", text="Share ID", box=(0, 0, 80, 20)),
            make_node("id1", "cell", text="0001", box=(0, 20, 80, 20)),
            share_id_cell,
        ]
    )
    candidates = generate_candidates(share_id_cell, observation)
    anchored = next(
        candidate for candidate in candidates if isinstance(candidate, TextAnchorCandidate)
    )
    assert (anchored.relation, anchored.ordinal) == ("below", 1)
    assert anchored.confidence == pytest.approx(0.65)


def test_structural_candidate_present_and_verified() -> None:
    observation = member_detail_observation()
    candidates = generate_candidates(node_in(observation, "v3"), observation)
    structural = next(
        candidate for candidate in candidates if isinstance(candidate, StructuralCandidate)
    )
    assert structural.container_path == ("frame:nav",)
    assert structural.structural_path == "link[3]"
    assert structural.confidence == pytest.approx(0.5)


def test_visual_anchor_is_last_and_offsets_from_unique_anchor() -> None:
    observation = member_detail_observation()
    candidates = generate_candidates(node_in(observation, "r1c3"), observation)
    last = candidates[-1]
    assert isinstance(last, VisualAnchorCandidate)
    assert last.confidence == pytest.approx(0.3)
    resolution = resolve_target(
        build_target_spec(node_in(observation, "r1c3"), observation, "balance").model_copy(
            update={"candidates": [last]}
        ),
        observation,
    )
    assert resolution is not None and resolution.node is not None and resolution.node.ref == "r1c3"


def test_no_visual_anchor_without_stable_text_in_container() -> None:
    observation = member_detail_observation()
    candidates = generate_candidates(
        node_in(observation, "v1"), observation
    )  # nav frame has only links
    assert not any(isinstance(candidate, VisualAnchorCandidate) for candidate in candidates)


def test_volatile_name_skips_role_name() -> None:
    member_link = make_node("m", "link", name="Member 10001", path="link[1]", box=(0, 0, 100, 20))
    candidates = generate_candidates(member_link, make_observation([member_link]))
    assert not any(isinstance(candidate, RoleNameCandidate) for candidate in candidates)
    assert isinstance(candidates[0], StructuralCandidate)


def test_name_from_text_and_long_name_penalties() -> None:
    long_text = "Please acknowledge the scheduled maintenance notice"
    cell = make_node("c", "cell", text=long_text, box=(0, 0, 400, 20))
    first = generate_candidates(cell, make_observation([cell]))[0]
    assert isinstance(first, RoleNameCandidate)
    assert first.confidence == pytest.approx(0.75)


def test_every_candidate_resolves_uniquely_back() -> None:
    observation = member_detail_observation()
    for ref in ("r1c3", "r2view", "m7", "t3"):
        node = node_in(observation, ref)
        for candidate in generate_candidates(node, observation):
            if isinstance(candidate, VisualAnchorCandidate):
                continue
            assert resolves_uniquely_to(candidate, node, observation), (ref, candidate)


# ---------------------------------------------------------------- budget and edge cases


def test_max_candidates_budget_keeps_visual_last() -> None:
    observation = login_observation()
    field = node_in(observation, "n6")
    two = generate_candidates(field, observation, max_candidates=2)
    assert [candidate.kind for candidate in two] == ["label", "visual_anchor"]
    one = generate_candidates(field, observation, max_candidates=1)
    assert [candidate.kind for candidate in one] == ["label"]
    four = generate_candidates(field, observation)
    assert len(four) == 4 and four[-1].kind == "visual_anchor"


def test_max_candidates_zero_or_negative_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    observation = login_observation()
    with caplog.at_level(logging.ERROR):
        assert generate_candidates(node_in(observation, "n6"), observation, max_candidates=0) == []
    assert "max_candidates must be >= 1" in caplog.text


def test_node_not_in_observation_logs_and_returns_empty(caplog: pytest.LogCaptureFixture) -> None:
    stranger = make_node("zz", "button", name="Ghost")
    with caplog.at_level(logging.ERROR):
        assert generate_candidates(stranger, empty_observation()) == []
    assert "not part of the observation" in caplog.text


def test_only_visual_when_nothing_robust() -> None:
    caption = make_node(
        "a", "text", text="Chart", box=(300, 0, 50, 20)
    )  # neither left of nor above
    canvas_region = make_node("b", "image", box=(0, 30, 200, 100))
    candidates = generate_candidates(canvas_region, make_observation([caption, canvas_region]))
    assert [candidate.kind for candidate in candidates] == ["visual_anchor"]


# ---------------------------------------------------------------- build_target_spec


def test_build_target_spec_uses_description_or_default() -> None:
    observation = login_observation()
    named = build_target_spec(node_in(observation, "n12"), observation, "  Sign On button ")
    assert named.description == "Sign On button"
    defaulted = build_target_spec(node_in(observation, "n12"), observation, "")
    assert defaulted.description == "button 'Sign On'"


def test_build_target_spec_fallback_is_structural_when_possible(
    caplog: pytest.LogCaptureFixture,
) -> None:
    twin_a = make_node("a", "button", path="button[1]")
    twin_b = make_node("b", "button", path="button[1]")
    observation = make_observation([twin_a, twin_b])
    with caplog.at_level(logging.ERROR):
        spec = build_target_spec(twin_a, observation, "")
    assert "no verified candidate" in caplog.text
    only = spec.candidates[0]
    assert isinstance(only, StructuralCandidate) and only.confidence == pytest.approx(0.05)
    assert spec.description == "button"


def test_build_target_spec_fallback_role_name_without_structure() -> None:
    bare = make_node("a", "button")
    spec = build_target_spec(bare, make_observation([bare]), "mystery")
    only = spec.candidates[0]
    assert isinstance(only, RoleNameCandidate) and only.name == "button"
    assert "human review" in only.reason


# ---------------------------------------------------------------- round-trip property


def _interactive_cases() -> list[tuple[str, str]]:
    return [
        (fixture_name, node.ref)
        for fixture_name, observation in all_fixture_observations().items()
        for node in observation.nodes
        if is_interactive(node)
    ]


@pytest.mark.parametrize(("fixture_name", "ref"), _interactive_cases())
def test_round_trip_every_interactive_node_resolves_at_rank_zero(
    fixture_name: str, ref: str
) -> None:
    observation = all_fixture_observations()[fixture_name]
    node = node_in(observation, ref)
    spec = build_target_spec(node, observation, f"{fixture_name} {ref}")
    resolution = resolve_target(spec, observation)
    assert resolution is not None
    assert resolution.node is not None and resolution.node.ref == ref
    assert resolution.rank == 0
    assert not resolution.ambiguous
    assert all(candidate.reason for candidate in spec.candidates)


def test_round_trip_covers_a_meaningful_number_of_nodes() -> None:
    assert len(_interactive_cases()) >= 40
