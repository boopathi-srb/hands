"""Realistic Observations of the CoreOne legacy frameset app, for hands.locate tests.

Coordinates are viewport pixels. Frames share the viewport coordinate space, as a browser surface
reports them. All data is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hands.core.observation import Dialog, Location, Node, Observation, Rect

TOP_FRAME = ("frame:top",)
NAV_FRAME = ("frame:nav",)
CONTENT_FRAME = ("frame:content",)
NO_CONTAINER: tuple[str, ...] = ()

BASE_URL = "http://127.0.0.1:8000"
OBSERVED_AT = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def make_node(
    ref: str,
    role: str,
    *,
    name: str = "",
    text: str = "",
    value: str | None = None,
    label: str | None = None,
    container: tuple[str, ...] = CONTENT_FRAME,
    path: str = "",
    box: tuple[float, float, float, float] | None = None,
    enabled: bool = True,
) -> Node:
    bounds = Rect(x=box[0], y=box[1], width=box[2], height=box[3]) if box is not None else None
    return Node(
        ref=ref,
        role=role,
        name=name,
        text=text,
        value=value,
        label=label,
        container_path=container,
        structural_path=path,
        bounds=bounds,
        enabled=enabled,
    )


def make_observation(
    nodes: list[Node],
    *,
    url: str = f"{BASE_URL}/t/lakeside/main",
    title: str = "CoreOne",
    dialogs: list[Dialog] | None = None,
    location: Location | None = None,
) -> Observation:
    return Observation(
        observed_at=OBSERVED_AT,
        location=location or Location(kind="url", value=url, title=title),
        nodes=nodes,
        dialogs=dialogs or [],
        fingerprint="fixture",
    )


def empty_observation() -> Observation:
    return make_observation([], url=f"{BASE_URL}/blank", title="")


# ---------------------------------------------------------------- login page (no frames)


def login_observation() -> Observation:
    """Table layout; labels are adjacent <td> cells, inputs have no accessible name."""
    nodes = [
        make_node(
            "n1",
            "heading",
            name="CoreOne Member Services",
            container=NO_CONTAINER,
            path="heading[1]",
            box=(20, 10, 400, 30),
        ),
        make_node(
            "n2",
            "table",
            text="User ID Password Sign On",
            container=NO_CONTAINER,
            path="table[1]",
            box=(20, 60, 420, 110),
        ),
        make_node(
            "n3",
            "row",
            text="User ID",
            container=NO_CONTAINER,
            path="table[1]/row[1]",
            box=(20, 60, 420, 30),
        ),
        make_node(
            "n4",
            "cell",
            text="User ID",
            container=NO_CONTAINER,
            path="table[1]/row[1]/cell[1]",
            box=(20, 60, 120, 30),
        ),
        make_node(
            "n5",
            "cell",
            container=NO_CONTAINER,
            path="table[1]/row[1]/cell[2]",
            box=(140, 60, 300, 30),
        ),
        make_node(
            "n6",
            "textbox",
            value="",
            container=NO_CONTAINER,
            path="table[1]/row[1]/cell[2]/textbox[1]",
            box=(145, 63, 200, 24),
        ),
        make_node(
            "n7",
            "row",
            text="Password",
            container=NO_CONTAINER,
            path="table[1]/row[2]",
            box=(20, 95, 420, 30),
        ),
        make_node(
            "n8",
            "cell",
            text="Password:",
            container=NO_CONTAINER,
            path="table[1]/row[2]/cell[1]",
            box=(20, 95, 120, 30),
        ),
        make_node(
            "n9",
            "cell",
            container=NO_CONTAINER,
            path="table[1]/row[2]/cell[2]",
            box=(140, 95, 300, 30),
        ),
        make_node(
            "n10",
            "textbox",
            value="",
            container=NO_CONTAINER,
            path="table[1]/row[2]/cell[2]/textbox[1]",
            box=(145, 98, 200, 24),
        ),
        make_node(
            "n11",
            "row",
            text="Sign On",
            container=NO_CONTAINER,
            path="table[1]/row[3]",
            box=(20, 130, 420, 40),
        ),
        make_node(
            "n12",
            "button",
            name="Sign On",
            container=NO_CONTAINER,
            path="table[1]/row[3]/cell[2]/button[1]",
            box=(145, 135, 90, 28),
        ),
        make_node(
            "n13",
            "text",
            text="CoreOne 7.4 - Northwind Core Systems",
            container=NO_CONTAINER,
            path="text[1]",
            box=(20, 200, 300, 20),
        ),
    ]
    return make_observation(nodes, url=f"{BASE_URL}/t/lakeside/login", title="CoreOne Sign On")


# ---------------------------------------------------------------- frameset chrome


def _top_and_nav_frames(brand: str) -> list[Node]:
    return [
        make_node(
            "t1", "text", text=brand, container=TOP_FRAME, path="text[1]", box=(10, 5, 300, 20)
        ),
        make_node(
            "t2",
            "text",
            text="Signed on as teller1",
            container=TOP_FRAME,
            path="text[2]",
            box=(500, 5, 200, 20),
        ),
        make_node(
            "t3", "link", name="Sign Off", container=TOP_FRAME, path="link[1]", box=(720, 5, 60, 20)
        ),
        make_node(
            "v1",
            "link",
            name="Member Inquiry",
            container=NAV_FRAME,
            path="link[1]",
            box=(10, 50, 150, 20),
        ),
        make_node(
            "v2",
            "link",
            name="Open Share Account",
            container=NAV_FRAME,
            path="link[2]",
            box=(10, 75, 150, 20),
        ),
        make_node(
            "v3",
            "link",
            name="Reports",
            container=NAV_FRAME,
            path="link[3]",
            box=(10, 100, 150, 20),
        ),
    ]


# ---------------------------------------------------------------- member inquiry


def inquiry_observation(
    member_label: str = "Member Number", search_label: str = "Search"
) -> Observation:
    content = [
        make_node(
            "c1", "heading", name="Member Inquiry", path="heading[1]", box=(200, 50, 300, 30)
        ),
        make_node(
            "c2", "cell", text=member_label, path="table[1]/row[1]/cell[1]", box=(200, 90, 140, 24)
        ),
        make_node("c3", "cell", path="table[1]/row[1]/cell[2]", box=(340, 90, 170, 24)),
        make_node(
            "c4",
            "textbox",
            value="",
            path="table[1]/row[1]/cell[2]/textbox[1]",
            box=(350, 92, 150, 20),
        ),
        make_node(
            "c5",
            "button",
            name=search_label,
            path="table[1]/row[1]/cell[3]/button[1]",
            box=(515, 90, 70, 24),
        ),
    ]
    return make_observation(
        _top_and_nav_frames("Lakeside Community CU") + content,
        url=f"{BASE_URL}/t/lakeside/main?content=/t/lakeside/inquiry",
        title="CoreOne - Member Inquiry",
    )


def prairie_inquiry_observation() -> Observation:
    return inquiry_observation(member_label="Account Number", search_label="Find")


# ---------------------------------------------------------------- member detail with shares table

SHARE_COLUMNS_LAKESIDE = ("Share ID", "Description", "Balance", "Available")
SHARE_COLUMNS_PRAIRIE = ("Share ID", "Balance", "Description", "Available")
COLUMN_LEFT_EDGES = (200.0, 280.0, 440.0, 540.0)
COLUMN_WIDTHS = (80.0, 160.0, 100.0, 100.0)
ACTION_COLUMN = (640.0, 120.0)
ROW_HEIGHT = 25.0
HEADER_TOP = 170.0


def _share_rows(savings_name: str) -> list[dict[str, str]]:
    return [
        {
            "Share ID": "0001",
            "Description": savings_name,
            "Balance": "1,250.00",
            "Available": "1,250.00",
        },
        {"Share ID": "0014", "Description": "Checking", "Balance": "310.45", "Available": "310.45"},
        {
            "Share ID": "0021",
            "Description": "Holiday Club",
            "Balance": "85.00",
            "Available": "85.00",
        },
    ]


def _cell(ref: str, text: str, row_index: int, column_index: int, top: float) -> Node:
    return make_node(
        ref,
        "cell",
        text=text,
        path=f"table[2]/row[{row_index}]/cell[{column_index + 1}]",
        box=(COLUMN_LEFT_EDGES[column_index], top, COLUMN_WIDTHS[column_index], ROW_HEIGHT),
    )


def _shares_table(columns: tuple[str, ...], savings_name: str) -> list[Node]:
    rows = _share_rows(savings_name)
    table_text = " ".join(
        [*columns, *(" ".join(row[column] for column in columns) + " View" for row in rows)]
    )
    table_height = ROW_HEIGHT * (len(rows) + 1)
    nodes = [
        make_node(
            "s0",
            "table",
            text=table_text,
            path="table[2]",
            box=(200, HEADER_TOP, 560, table_height),
        ),
        make_node(
            "h0",
            "row",
            text=" ".join(columns),
            path="table[2]/row[1]",
            box=(200, HEADER_TOP, 560, ROW_HEIGHT),
        ),
    ]
    nodes += [
        _cell(f"h{index + 1}", column, 1, index, HEADER_TOP) for index, column in enumerate(columns)
    ]
    for row_number, row in enumerate(rows, start=1):
        nodes += _share_row_nodes(row_number, row, columns)
    return nodes


def _share_row_nodes(row_number: int, row: dict[str, str], columns: tuple[str, ...]) -> list[Node]:
    top = HEADER_TOP + ROW_HEIGHT * row_number
    row_index = row_number + 1
    row_text = " ".join(row[column] for column in columns) + " View"
    action_left, action_width = ACTION_COLUMN
    nodes = [
        make_node(
            f"r{row_number}",
            "row",
            text=row_text,
            path=f"table[2]/row[{row_index}]",
            box=(200, top, 560, ROW_HEIGHT),
        )
    ]
    nodes += [
        _cell(f"r{row_number}c{index + 1}", row[column], row_index, index, top)
        for index, column in enumerate(columns)
    ]
    nodes += [
        make_node(
            f"r{row_number}c5",
            "cell",
            text="View",
            path=f"table[2]/row[{row_index}]/cell[5]",
            box=(action_left, top, action_width, ROW_HEIGHT),
        ),
        make_node(
            f"r{row_number}view",
            "link",
            name="View",
            path=f"table[2]/row[{row_index}]/cell[5]/link[1]",
            box=(action_left + 10, top + 3, 40, 19),
        ),
    ]
    return nodes


def _member_summary() -> list[Node]:
    return [
        make_node("m1", "heading", name="Member Detail", path="heading[1]", box=(200, 50, 300, 30)),
        make_node(
            "m2", "cell", text="Name", path="table[1]/row[1]/cell[1]", box=(200, 90, 100, 20)
        ),
        make_node(
            "m3", "cell", text="Avery Quinn", path="table[1]/row[1]/cell[2]", box=(300, 90, 200, 20)
        ),
        make_node(
            "m4", "cell", text="Status", path="table[1]/row[2]/cell[1]", box=(200, 110, 100, 20)
        ),
        make_node(
            "m5", "cell", text="Active", path="table[1]/row[2]/cell[2]", box=(300, 110, 200, 20)
        ),
        make_node("m6", "heading", name="Shares", path="heading[2]", box=(200, 140, 200, 24)),
        make_node("m7", "button", name="Print", path="button[1]", box=(200, 290, 70, 24)),
        make_node(
            "m8",
            "button",
            name="Close Member",
            path="button[2]",
            box=(280, 290, 110, 24),
            enabled=False,
        ),
    ]


def member_detail_observation() -> Observation:
    """Lakeside tenant: member 10001 with Regular Savings, Checking, Holiday Club."""
    nodes = _top_and_nav_frames("Lakeside Community CU") + _member_summary()
    nodes += _shares_table(SHARE_COLUMNS_LAKESIDE, "Regular Savings")
    return make_observation(
        nodes,
        url=f"{BASE_URL}/t/lakeside/member/10001",
        title="CoreOne - Member Detail",
    )


def prairie_member_detail_observation() -> Observation:
    """Prairie tenant: 'Share Savings' and a different column order."""
    nodes = _top_and_nav_frames("Prairie Federal CU") + _member_summary()
    nodes += _shares_table(SHARE_COLUMNS_PRAIRIE, "Share Savings")
    return make_observation(
        nodes,
        url=f"{BASE_URL}/t/prairie/member/10001",
        title="CoreOne - Member Detail",
    )


# ---------------------------------------------------------------- modal dialogs


def maintenance_modal_observation() -> Observation:
    """In-page 'System Notice' modal table over the member detail content."""
    base = member_detail_observation()
    modal_nodes = [
        make_node(
            "d1",
            "dialog",
            name="System Notice",
            text="System Notice Scheduled maintenance tonight.",
            path="dialog[1]",
            box=(300, 150, 300, 150),
        ),
        make_node(
            "d2",
            "text",
            text="Scheduled maintenance tonight.",
            path="dialog[1]/text[1]",
            box=(320, 190, 260, 40),
        ),
        make_node(
            "d3", "button", name="Acknowledge", path="dialog[1]/button[1]", box=(400, 260, 100, 28)
        ),
    ]
    return make_observation(
        base.nodes + modal_nodes,
        url=base.location.value,
        title=base.location.title,
        dialogs=[
            Dialog(title="System Notice", text="Scheduled maintenance tonight.", native=False)
        ],
    )


def native_alert_observation() -> Observation:
    base = member_detail_observation()
    return make_observation(
        base.nodes,
        url=base.location.value,
        title=base.location.title,
        dialogs=[Dialog(title="", text="Printer queue offline", native=True)],
    )


def desktop_window_observation() -> Observation:
    nodes = [
        make_node(
            "w1",
            "button",
            name="Search",
            container=("window:Member Inquiry",),
            path="button[1]",
            box=(300, 100, 80, 24),
        ),
    ]
    return make_observation(
        nodes,
        location=Location(
            kind="window", value="com.northwind.coreone", title="Member Inquiry - CoreOne"
        ),
    )


def all_fixture_observations() -> dict[str, Observation]:
    return {
        "login": login_observation(),
        "inquiry": inquiry_observation(),
        "prairie_inquiry": prairie_inquiry_observation(),
        "member_detail": member_detail_observation(),
        "prairie_member_detail": prairie_member_detail_observation(),
        "maintenance_modal": maintenance_modal_observation(),
        "native_alert": native_alert_observation(),
        "desktop_window": desktop_window_observation(),
    }
