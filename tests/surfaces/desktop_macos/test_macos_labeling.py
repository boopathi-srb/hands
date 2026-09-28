from hands.core.observation import Node, Rect
from hands.surfaces.desktop_macos.labeling import (
    LabelGeometry,
    above_gap,
    assign_geometric_labels,
    left_gap,
)

WINDOW = ("window:Form",)


def text_node(
    ref: str, text: str, bounds: Rect | None, container: tuple[str, ...] = WINDOW
) -> Node:
    return Node(ref=ref, role="text", name=text, text=text, container_path=container, bounds=bounds)


def field_node(
    ref: str, bounds: Rect | None, role: str = "textbox", label: str | None = None
) -> Node:
    return Node(ref=ref, role=role, container_path=WINDOW, bounds=bounds, label=label, value="")


def test_label_from_text_on_the_left() -> None:
    nodes = [
        text_node("n1", "Member Number", Rect(x=10, y=50, width=100, height=20)),
        field_node("n2", Rect(x=120, y=48, width=150, height=24)),
    ]
    assert assign_geometric_labels(nodes)[1].label == "Member Number"


def test_label_from_text_above() -> None:
    nodes = [
        text_node("n1", "First Name", Rect(x=10, y=80, width=100, height=20)),
        field_node("n2", Rect(x=10, y=105, width=150, height=24)),
    ]
    assert assign_geometric_labels(nodes)[1].label == "First Name"


def test_left_label_preferred_over_above_and_nearest_left_wins() -> None:
    nodes = [
        text_node("n1", "Above", Rect(x=120, y=20, width=100, height=20)),
        text_node("n2", "Far Left", Rect(x=0, y=50, width=40, height=20)),
        text_node("n3", "Near Left", Rect(x=50, y=50, width=60, height=20)),
        field_node("n4", Rect(x=120, y=48, width=150, height=24)),
    ]
    assert assign_geometric_labels(nodes)[3].label == "Near Left"


def test_text_in_another_container_is_ignored() -> None:
    nodes = [
        text_node(
            "n1",
            "Sheet Text",
            Rect(x=10, y=50, width=100, height=20),
            container=(*WINDOW, "sheet:Confirm"),
        ),
        field_node("n2", Rect(x=120, y=48, width=150, height=24)),
    ]
    assert assign_geometric_labels(nodes)[1].label is None


def test_existing_label_is_kept_and_non_form_roles_untouched() -> None:
    nodes = [
        text_node("n1", "Adjacent", Rect(x=10, y=50, width=100, height=20)),
        field_node("n2", Rect(x=120, y=48, width=150, height=24), label="Programmatic"),
        field_node("n3", Rect(x=120, y=48, width=150, height=24), role="button"),
    ]
    labeled = assign_geometric_labels(nodes)
    assert labeled[1].label == "Programmatic"
    assert labeled[2].label is None


def test_missing_bounds_and_empty_input() -> None:
    assert assign_geometric_labels([]) == []
    nodes = [text_node("n1", "Label", None), field_node("n2", None)]
    assert assign_geometric_labels(nodes)[1].label is None
    nodes = [
        text_node("n1", "Label", None),
        field_node("n2", Rect(x=120, y=48, width=150, height=24)),
    ]
    assert assign_geometric_labels(nodes)[1].label is None


def test_left_gap_boundaries() -> None:
    geometry = LabelGeometry(max_left_gap=50, edge_slack=4)
    field = Rect(x=200, y=10, width=100, height=20)
    assert left_gap(Rect(x=50, y=10, width=100, height=20), field, geometry) == 50
    assert left_gap(Rect(x=49, y=10, width=100, height=20), field, geometry) is None
    assert left_gap(Rect(x=104, y=10, width=100, height=20), field, geometry) == -4
    assert left_gap(Rect(x=105, y=10, width=100, height=20), field, geometry) is None
    assert left_gap(Rect(x=90, y=200, width=100, height=20), field, geometry) is None


def test_above_gap_boundaries() -> None:
    geometry = LabelGeometry(max_above_gap=30, edge_slack=4)
    field = Rect(x=10, y=100, width=100, height=20)
    assert above_gap(Rect(x=10, y=50, width=50, height=20), field, geometry) == 30
    assert above_gap(Rect(x=10, y=49, width=50, height=20), field, geometry) is None
    assert above_gap(Rect(x=200, y=70, width=50, height=20), field, geometry) is None
