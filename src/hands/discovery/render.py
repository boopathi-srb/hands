"""Observation -> compact text (and a downscaled screenshot) for the planner.

The listing is what a weak model can use: one line per useful node, numbered by ref, grouped by
container, dialogs first, capped at `max_nodes` with interactive and visible nodes kept first.

Secrets never reach the model: every registered secret value is replaced by a mask wherever it
appears (names, text, labels, values, dialogs, location), and password-like fields always show
`••••` when they hold anything.
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence

from PIL import Image, ImageDraw, UnidentifiedImageError
from pydantic import BaseModel

from hands.core.log import get_logger, log_failure
from hands.core.observation import Dialog, Node, Observation, Rect

_logger = get_logger(__name__)

SECRET_MASK = "••••"
DEFAULT_MAX_NODES = 80
MAX_NODE_TEXT_CHARS = 80
SCREENSHOT_MAX_WIDTH = 1024
PAGE_GROUP = "page"
DIALOG_GROUP = "dialog"

INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "listbox", "checkbox", "radio",
    "menuitem", "option", "tab", "spinbutton", "slider", "switch",
})
EDITABLE_ROLES = frozenset({"textbox", "searchbox", "combobox", "listbox", "spinbutton"})
CONTAINER_ROLES = frozenset({
    "table", "grid", "row", "rowgroup", "list", "document", "form", "group", "region", "main",
    "navigation", "frame", "window", "pane", "generic", "none", "presentation",
})
DIALOG_ROLES = frozenset({"dialog", "alertdialog", "alert"})
_PASSWORD_WORDS = re.compile(r"pass(word|code|phrase)?|\bpin\b|secret", re.IGNORECASE)
_MASK_CHARACTERS = frozenset("•*●")

_RANK_DIALOG = 0
_RANK_INTERACTIVE = 1
_RANK_TEXT = 2
_RANK_DISABLED = 3
_RANK_HIDDEN = 4


class RenderedObservation(BaseModel):
    text: str
    shown_refs: list[str]
    omitted_count: int = 0


# ---------------------------------------------------------------- secrets


def mask_secrets(text: str, secret_values: Sequence[str]) -> str:
    """Replace every occurrence of every secret value (longest first) with the mask."""
    if not text:
        return text
    masked_text = text
    for secret in sorted((value for value in secret_values if value), key=len, reverse=True):
        masked_text = masked_text.replace(secret, SECRET_MASK)
    return masked_text


def is_password_field(node: Node) -> bool:
    """Editable node whose label/name says password, or whose value is already masked by the surface."""
    if node.role.casefold() not in EDITABLE_ROLES:
        return False
    described_as_password = any(
        _PASSWORD_WORDS.search(text or "") for text in (node.name, node.label)
    )
    return described_as_password or _looks_masked(node.value)


def _looks_masked(value: str | None) -> bool:
    return bool(value) and all(character in _MASK_CHARACTERS for character in value or "")


def scrub_node(node: Node, secret_values: Sequence[str]) -> Node:
    """A copy of the node with secrets masked in every text field and password values masked."""
    shown_value = node.value
    if is_password_field(node) and node.value:
        shown_value = SECRET_MASK
    elif shown_value is not None:
        shown_value = mask_secrets(shown_value, secret_values)
    return node.model_copy(update={
        "name": mask_secrets(node.name, secret_values),
        "text": mask_secrets(node.text, secret_values),
        "label": None if node.label is None else mask_secrets(node.label, secret_values),
        "value": shown_value,
    })


def scrub_observation(observation: Observation, secret_values: Sequence[str]) -> Observation:
    """The observation with every secret masked (screenshot kept; it is masked by evidence redaction)."""
    dialogs = [
        Dialog(
            title=mask_secrets(dialog.title, secret_values),
            text=mask_secrets(dialog.text, secret_values),
            native=dialog.native,
        )
        for dialog in observation.dialogs
    ]
    location = observation.location.model_copy(update={
        "value": mask_secrets(observation.location.value, secret_values),
        "title": mask_secrets(observation.location.title, secret_values),
    })
    return observation.model_copy(update={
        "nodes": [scrub_node(node, secret_values) for node in observation.nodes],
        "dialogs": dialogs,
        "location": location,
    })


# ---------------------------------------------------------------- rendering


def render_observation(
    observation: Observation,
    *,
    secret_values: Sequence[str] = (),
    max_nodes: int = DEFAULT_MAX_NODES,
) -> RenderedObservation:
    """Numbered, grouped, secret-free listing of the observation for the planner."""
    scrubbed = scrub_observation(observation, secret_values)
    candidates = [node for node in scrubbed.nodes if _is_worth_showing(node)]
    selected = _select_nodes(candidates, max(0, max_nodes))
    omitted_count = len(candidates) - len(selected)
    lines = [
        *_header_lines(scrubbed),
        *_grouped_node_lines(selected),
        *_omitted_lines(omitted_count),
    ]
    return RenderedObservation(
        text="\n".join(lines),
        shown_refs=[node.ref for node in selected],
        omitted_count=omitted_count,
    )


def node_display_name(node: Node) -> str:
    """Name a person would read: accessible name, else visible text, else label."""
    for text in (node.name, node.text, node.label):
        collapsed = " ".join((text or "").split())
        if collapsed:
            return collapsed
    return ""


def render_node_line(node: Node) -> str:
    parts = [f"[{node.ref}]", node.role]
    display_name = _truncate(node_display_name(node))
    if display_name:
        parts.append(f'"{display_name}"')
    label = " ".join((node.label or "").split())
    if label and label != node_display_name(node):
        parts.append(f'label="{_truncate(label)}"')
    if node.role.casefold() in EDITABLE_ROLES:
        parts.append(f'value="{_truncate(node.value or "")}"')
    if not node.enabled:
        parts.append("(disabled)")
    if node.focused:
        parts.append("(focused)")
    return " ".join(parts)


def _truncate(text: str) -> str:
    if len(text) <= MAX_NODE_TEXT_CHARS:
        return text
    return text[: MAX_NODE_TEXT_CHARS - 1] + "…"


def _is_worth_showing(node: Node) -> bool:
    role = node.role.casefold()
    if role in INTERACTIVE_ROLES or role in DIALOG_ROLES:
        return True
    if role in CONTAINER_ROLES:
        return False
    return bool(node_display_name(node))


def _is_dialog_node(node: Node) -> bool:
    in_dialog_container = any(part.startswith("dialog") for part in node.container_path)
    return (
        node.role.casefold() in DIALOG_ROLES
        or in_dialog_container
        or node.structural_path.startswith("dialog")
    )


def _is_visible(node: Node) -> bool:
    return node.bounds is None or (node.bounds.width > 0 and node.bounds.height > 0)


def _priority(node: Node) -> int:
    if _is_dialog_node(node):
        return _RANK_DIALOG
    if not _is_visible(node):
        return _RANK_HIDDEN
    if node.role.casefold() in INTERACTIVE_ROLES:
        return _RANK_INTERACTIVE if node.enabled else _RANK_DISABLED
    return _RANK_TEXT


def _select_nodes(candidates: list[Node], max_nodes: int) -> list[Node]:
    """Keep the `max_nodes` highest-priority nodes, then restore document order."""
    ranked = sorted(enumerate(candidates), key=lambda pair: (_priority(pair[1]), pair[0]))
    kept_indexes = sorted(index for index, _node in ranked[:max_nodes])
    return [candidates[index] for index in kept_indexes]


def _group_name(node: Node) -> str:
    if _is_dialog_node(node):
        return DIALOG_GROUP
    return "/".join(node.container_path) or PAGE_GROUP


def _grouped_node_lines(nodes: list[Node]) -> list[str]:
    groups: dict[str, list[Node]] = {}
    for node in nodes:
        groups.setdefault(_group_name(node), []).append(node)
    ordered_names = sorted(groups, key=lambda name: 0 if name == DIALOG_GROUP else 1)
    lines: list[str] = []
    for group_name in ordered_names:
        lines.append(f"-- {group_name} --")
        lines.extend(render_node_line(node) for node in groups[group_name])
    return lines


def _header_lines(observation: Observation) -> list[str]:
    location = observation.location
    title = f" | title: {location.title}" if location.title else ""
    lines = [f"LOCATION: {location.value}{title}"]
    lines.extend(_dialog_line(dialog) for dialog in observation.dialogs)
    return lines


def _dialog_line(dialog: Dialog) -> str:
    kind = "native alert" if dialog.native else "dialog"
    title = f'"{_truncate(dialog.title)}"' if dialog.title else ""
    text = f": {_truncate(dialog.text)}" if dialog.text else ""
    return f"OPEN {kind.upper()} {title}{text}".rstrip()


def _omitted_lines(omitted_count: int) -> list[str]:
    return [f"({omitted_count} more elements not shown)"] if omitted_count > 0 else []


# ---------------------------------------------------------------- screenshot


def downscale_screenshot(png: bytes | None, max_width: int = SCREENSHOT_MAX_WIDTH) -> bytes | None:
    """PNG no wider than `max_width` (aspect kept). None in, or an unreadable image, gives None."""
    if not png:
        return None
    if max_width < 1:
        log_failure(_logger, "downscale_screenshot", "max_width must be >= 1", max_width=max_width)
        return None
    try:
        with Image.open(io.BytesIO(png)) as image:
            return _resized_png(image, max_width)
    except (UnidentifiedImageError, OSError, ValueError) as image_error:
        log_failure(
            _logger, "downscale_screenshot", str(image_error), png_bytes=len(png), max_width=max_width
        )
        return None


def sensitive_nodes(observation: Observation, secret_values: Sequence[str]) -> list[Node]:
    """Nodes whose pixels may show a secret: password fields with a value, or any text holding one."""
    return [node for node in observation.nodes if _node_is_sensitive(node, secret_values)]


def _node_is_sensitive(node: Node, secret_values: Sequence[str]) -> bool:
    if is_password_field(node) and node.value:
        return True
    texts = (node.name, node.text, node.label or "", node.value or "")
    non_empty_secrets = [secret for secret in secret_values if secret]
    return any(secret in text for secret in non_empty_secrets for text in texts)


def mask_screenshot(
    png: bytes | None, observation: Observation, secret_values: Sequence[str], scale: float = 1.0
) -> bytes | None:
    """Black out the bounds of every sensitive node. `scale` = image pixels per observation pixel.

    Returns None when there is no image or it cannot be read (the model then gets no screenshot,
    never an unmasked one).
    """
    if not png:
        return None
    rectangles = [node.bounds for node in sensitive_nodes(observation, secret_values) if node.bounds]
    if not rectangles:
        return png
    try:
        with Image.open(io.BytesIO(png)) as image:
            return _blacked_out_png(image, rectangles, scale)
    except (UnidentifiedImageError, OSError, ValueError) as image_error:
        log_failure(_logger, "mask_screenshot", str(image_error), png_bytes=len(png),
                    rectangles=len(rectangles))
        return None


def _blacked_out_png(image: Image.Image, rectangles: Sequence[Rect], scale: float) -> bytes:
    canvas = image.convert("RGB")
    drawing = ImageDraw.Draw(canvas)
    padding = 2
    for rect in rectangles:
        drawing.rectangle(
            (
                rect.x * scale - padding,
                rect.y * scale - padding,
                (rect.x + rect.width) * scale + padding,
                (rect.y + rect.height) * scale + padding,
            ),
            fill=(0, 0, 0),
        )
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _resized_png(image: Image.Image, max_width: int) -> bytes:
    if image.width > max_width:
        new_height = max(1, round(image.height * max_width / image.width))
        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
