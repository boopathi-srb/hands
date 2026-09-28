"""ScriptedPlanner: deterministic rules instead of a model, for tests and offline demos.

A rule is a predicate over the PlannerContext (usually over the rendered screen text) plus a factory
that builds the decision, typically by finding a ref in the rendered listing by role and name. Rules
are tried in order; by default each fires once, so a script reads like the flow it drives.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from hands.core.log import get_logger, log_failure
from hands.discovery.planner import PlannerContext, PlannerDecision, PlannerResponse

_logger = get_logger(__name__)

Predicate = Callable[[PlannerContext], bool]
DecisionFactory = Callable[[PlannerContext], PlannerDecision | None]

_NODE_LINE = re.compile(r'^\[(?P<ref>[^\]]+)\] (?P<role>\S+)(?: "(?P<name>[^"]*)")?')


@dataclass
class ScriptRule:
    name: str
    when: Predicate
    decide: DecisionFactory
    once: bool = True


class ScriptedPlanner:
    """Implements the Planner port from an ordered list of rules."""

    def __init__(self, rules: Sequence[ScriptRule], *, name: str = "scripted") -> None:
        self._rules = list(rules)
        self._consumed: list[str] = []
        self.name = name
        self.fired: list[str] = []
        self.contexts: list[PlannerContext] = []

    async def decide(self, context: PlannerContext) -> PlannerResponse:
        self.contexts.append(context)
        for rule in self._rules:
            if rule.name in self._consumed or not rule.when(context):
                continue
            decision = rule.decide(context)
            if decision is None:
                log_failure(_logger, "ScriptedPlanner.decide", "rule matched but built no decision",
                            rule=rule.name)
                continue
            self._mark_fired(rule)
            return PlannerResponse(decision=decision, raw_text=decision.model_dump_json())
        stuck = PlannerDecision(rationale="No scripted rule matches this screen.", action="stuck")
        return PlannerResponse(decision=stuck, raw_text=stuck.model_dump_json())

    def _mark_fired(self, rule: ScriptRule) -> None:
        self.fired.append(rule.name)
        if rule.once:
            self._consumed.append(rule.name)


# ---------------------------------------------------------------- listing helpers


@dataclass(frozen=True)
class ListedNode:
    ref: str
    role: str
    name: str


def listed_nodes(observation_text: str) -> list[ListedNode]:
    """The node lines of a rendered observation, in listing order."""
    nodes: list[ListedNode] = []
    for line in observation_text.splitlines():
        match = _NODE_LINE.match(line)
        if match:
            nodes.append(ListedNode(match["ref"], match["role"], match["name"] or ""))
    return nodes


def find_ref(observation_text: str, role: str, name: str) -> str | None:
    """Ref of the first listed node with this role and name (case-insensitive)."""
    for node in listed_nodes(observation_text):
        if node.role.casefold() == role.casefold() and node.name.casefold() == name.casefold():
            return node.ref
    return None


def find_ref_near(observation_text: str, anchor_name: str, offset: int) -> str | None:
    """Ref of the node `offset` places after (negative: before) the first node named `anchor_name`."""
    nodes = listed_nodes(observation_text)
    anchor_index = next(
        (index for index, node in enumerate(nodes) if node.name.casefold() == anchor_name.casefold()),
        None,
    )
    if anchor_index is None or not 0 <= anchor_index + offset < len(nodes):
        return None
    return nodes[anchor_index + offset].ref


# ---------------------------------------------------------------- predicates


def screen_has(*fragments: str) -> Predicate:
    return lambda context: all(fragment in context.observation_text for fragment in fragments)


def screen_lacks(fragment: str) -> Predicate:
    return lambda context: fragment not in context.observation_text


def all_of(*predicates: Predicate) -> Predicate:
    return lambda context: all(predicate(context) for predicate in predicates)


def extracted(output_name: str) -> Predicate:
    return lambda context: output_name in context.extracted


def always() -> Predicate:
    return lambda _context: True


# ---------------------------------------------------------------- decision factories


def click(role: str, name: str, rationale: str | None = None) -> DecisionFactory:
    def build(context: PlannerContext) -> PlannerDecision | None:
        ref = find_ref(context.observation_text, role, name)
        if ref is None:
            return None
        return PlannerDecision(
            rationale=rationale or f"Click the {name} {role}.", action="click", node_ref=ref
        )

    return build


def type_into(role: str, name: str, value: str, rationale: str | None = None) -> DecisionFactory:
    def build(context: PlannerContext) -> PlannerDecision | None:
        ref = find_ref(context.observation_text, role, name)
        if ref is None:
            return None
        return PlannerDecision(
            rationale=rationale or f"Enter {value} into {name}.", action="type", node_ref=ref,
            value=value,
        )

    return build


def press(key: str, rationale: str | None = None) -> DecisionFactory:
    return lambda _context: PlannerDecision(
        rationale=rationale or f"Press {key}.", action="press", key=key
    )


def extract_near(anchor_name: str, offset: int, output_name: str) -> DecisionFactory:
    def build(context: PlannerContext) -> PlannerDecision | None:
        ref = find_ref_near(context.observation_text, anchor_name, offset)
        if ref is None:
            return None
        return PlannerDecision(
            rationale=f"Read {output_name} from the row of {anchor_name}.",
            action="extract", node_ref=ref, output_name=output_name,
        )

    return build


def decision(built: PlannerDecision) -> DecisionFactory:
    return lambda _context: built


def done(rationale: str = "Every requested value is extracted.") -> DecisionFactory:
    return decision(PlannerDecision(rationale=rationale, action="done"))


# ---------------------------------------------------------------- CoreOne demo script

COREONE_BALANCE_GOAL = (
    "Look up member {{member_number}} in CoreOne and return the balance of their savings share "
    "as savings_balance."
)


@dataclass(frozen=True)
class CoreOneScreenText:
    """Tenant wording the script needs (PLAN.md tenant table)."""

    member_label: str = "Member Number"
    search_button: str = "Search"
    savings_name: str = "Regular Savings"
    balance_offset: int = 1


COREONE_SCREEN_TEXT: dict[str, CoreOneScreenText] = {
    "lakeside": CoreOneScreenText(),
    "prairie": CoreOneScreenText("Account Number", "Find", "Share Savings", -1),
}


def coreone_member_balance_script(
    tenant: str = "lakeside", output_name: str = "savings_balance"
) -> ScriptedPlanner:
    """Sign on, open Member Inquiry, search {{member_number}}, extract the savings balance, done."""
    wording = COREONE_SCREEN_TEXT.get(tenant, CoreOneScreenText())
    member_field = f'textbox "{wording.member_label}"'
    rules = [
        ScriptRule("enter_user_id", screen_has('textbox "User ID"'),
                   type_into("textbox", "User ID", "{{teller.username}}")),
        ScriptRule("enter_password", screen_has('textbox "Password"'),
                   type_into("textbox", "Password", "{{teller.password}}")),
        ScriptRule("sign_on", screen_has('button "Sign On"'), click("button", "Sign On")),
        ScriptRule("open_member_inquiry",
                   all_of(screen_has('link "Member Inquiry"'), screen_lacks(member_field)),
                   click("link", "Member Inquiry")),
        ScriptRule("enter_member_number", screen_has(member_field),
                   type_into("textbox", wording.member_label, "{{member_number}}")),
        ScriptRule("search", screen_has(f'button "{wording.search_button}"'),
                   click("button", wording.search_button)),
        ScriptRule("extract_balance", screen_has('"Member Detail"'),
                   extract_near(wording.savings_name, wording.balance_offset, output_name)),
        ScriptRule("done", extracted(output_name), done()),
    ]
    return ScriptedPlanner(rules, name="scripted")
