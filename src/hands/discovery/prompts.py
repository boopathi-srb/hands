"""Planner prompts. Model-agnostic and short enough for an 8B local model.

The system prompt is a constant (so it caches on providers that support prompt caching). Everything
that changes per turn goes in the user message built by `build_user_prompt`.
"""

from __future__ import annotations

from hands.discovery.planner import HistoryEntry, PlannerContext

SYSTEM_PROMPT = """You operate a business application for a back-office user, one action per turn.
Each turn you get the GOAL, the SCREEN as a numbered list of elements, and what happened so far.
Answer with exactly one JSON object with these keys:
rationale, action, node_ref, value, key, option, output_name, expected_result.

Actions:
- click: node_ref of a button or link.
- type: node_ref of a text field, value = the text.
- select: node_ref of a dropdown, option = visible option text.
- press: key such as Enter or Tab (node_ref optional).
- scroll: node_ref optional, value "up" or "down".
- open: value = URL. Only when told to.
- extract: node_ref of the element that shows a requested value, output_name in snake_case.
- done: every requested value is extracted.
- stuck: you cannot continue; say why in rationale.

Rules:
1. Act on one element per turn, by its ref from the current SCREEN, e.g. "n12". Refs change every turn.
2. Credentials: type the placeholder exactly, e.g. {{teller.password}}. You never see real values.
3. Inputs: type the placeholder exactly, e.g. {{member_number}}.
4. Extract each requested value from the element that shows it, then say done.
5. If an error or dialog appears, handle it or say stuck. Never guess.
6. Never act outside the task. Never submit, confirm or delete anything the goal did not ask for.
7. Unused keys are null. Keep rationale to one short sentence."""


def build_user_prompt(context: PlannerContext) -> str:
    """The per-turn user message: goal, placeholders, history, feedback, then the screen."""
    sections = [
        f"GOAL: {context.goal}",
        _inputs_section(context),
        _credentials_section(context),
        _extracted_section(context),
        f"STEPS LEFT: {context.steps_remaining}",
        _history_section(context.history),
        _feedback_section(context.feedback),
        f"SCREEN:\n{context.observation_text}",
        "Answer with one JSON object.",
    ]
    return "\n\n".join(section for section in sections if section)


def _inputs_section(context: PlannerContext) -> str:
    if not context.inputs:
        return ""
    lines = [f"- {{{{{hint.name}}}}} (this run: {hint.example})" for hint in context.inputs]
    return "INPUTS (type the placeholder):\n" + "\n".join(lines)


def _credentials_section(context: PlannerContext) -> str:
    if not context.credential_placeholders:
        return ""
    return "CREDENTIALS (type the placeholder): " + ", ".join(context.credential_placeholders)


def _extracted_section(context: PlannerContext) -> str:
    if not context.extracted:
        return "EXTRACTED: nothing yet"
    pairs = [f"{name} = {value}" for name, value in context.extracted.items()]
    return "EXTRACTED: " + "; ".join(pairs)


def _history_section(history: list[HistoryEntry]) -> str:
    if not history:
        return ""
    return "HISTORY:\n" + "\n".join(format_history_entry(entry) for entry in history)


def format_history_entry(entry: HistoryEntry) -> str:
    target = f" {entry.target}" if entry.target else ""
    ref = f" [{entry.node_ref}]" if entry.node_ref else ""
    value = f" value={entry.value!r}" if entry.value is not None else ""
    return f"{entry.step}. {entry.action}{ref}{target}{value} -> {entry.result}"


def _feedback_section(feedback: str | None) -> str:
    return f"FEEDBACK ON YOUR LAST ANSWER: {feedback}" if feedback else ""
