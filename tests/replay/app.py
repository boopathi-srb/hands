"""A small member-lookup app and capability used by the replay unit tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from hands.core.artifact import Capability
from hands.core.observation import Dialog
from hands.replay import ReplayEngine

from .fakes import (
    FakeClock,
    FakeCredentials,
    FakeEscalator,
    FakePolicy,
    MemoryEvidence,
    Route,
    Screen,
    ScriptedSurface,
    SecretLog,
    button,
    text,
    textbox,
)

LOGIN_URL = "http://app.test/login"
KNOWN_MEMBER = "10001"
MISSING_MEMBER = "99999"
RESTRICTED_MEMBER = "40300"


# ---------------------------------------------------------------- artifact building blocks


def role_name(role: str, name: str, exact: bool = True) -> dict[str, Any]:
    return {"kind": "role_name", "role": role, "name": name, "exact": exact, "confidence": 0.9, "reason": "test"}


def label(label_text: str) -> dict[str, Any]:
    return {"kind": "label", "label": label_text, "role": "textbox", "confidence": 0.85, "reason": "test"}


def target(description: str, *candidates: dict[str, Any]) -> dict[str, Any]:
    return {"description": description, "candidates": list(candidates)}


def text_visible(pattern: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "text_visible", "pattern": pattern, **extra}


def login_subflow() -> list[dict[str, Any]]:
    return [
        {"id": "login_open", "action": "open", "description": "Open sign-on", "entry_point": LOGIN_URL,
         "postcondition": {"kind": "node_present", "target": target("User ID", label("User ID"))}},
        {"id": "login_user", "action": "type", "description": "User", "value": "{{teller.username}}",
         "target": target("User ID", label("User ID"))},
        {"id": "login_password", "action": "type", "description": "Password", "value": "{{teller.password}}",
         "target": target("Password", label("Password"))},
        {"id": "login_submit", "action": "click", "description": "Sign on",
         "target": target("Sign On", role_name("button", "Sign On")),
         "postcondition": text_visible("Member Inquiry")},
    ]


def lookup_steps() -> list[dict[str, Any]]:
    return [
        {"id": "sign_in", "action": "subflow", "description": "Sign on", "subflow": "login"},
        {"id": "type_member", "action": "type", "description": "Member number", "value": "{{member_number}}",
         "target": target("Member number field", label("Member Number"))},
        {"id": "search", "action": "click", "description": "Search",
         "target": target("Search button", role_name("button", "Search"), role_name("button", "Find")),
         "postcondition": text_visible("Member Detail")},
        {"id": "read_balance", "action": "extract", "description": "Balance", "output": "balance",
         "target": target("Balance text", role_name("text", "Balance", exact=False)),
         "pattern": r"Balance:\s*(.+)"},
    ]


def lookup_outcomes() -> list[dict[str, Any]]:
    return [
        {"code": "MEMBER_NOT_FOUND", "description": "No such member",
         "when": text_visible("No member found for number {{member_number}}"),
         "message_target": target("Not found text", role_name("text", "No member found", exact=False))},
        {"code": "MEMBER_RESTRICTED", "description": "Restricted", "when": text_visible("ACCESS DENIED"),
         "message_target": target("Denied text", role_name("text", "ACCESS DENIED", exact=False))},
        {"code": "INVALID_MEMBER_NUMBER", "description": "Rejected format",
         "when": text_visible("Member number must be numeric")},
    ]


def lookup_recoveries() -> list[dict[str, Any]]:
    return [
        {"name": "session_expired", "description": "Sign on again", "when": text_visible("Your session has expired"),
         "response": {"kind": "subflow", "subflow": "login", "then": "restart"}, "max_applications": 1},
        {"name": "maintenance_notice", "description": "Acknowledge notice", "when": text_visible("System Notice"),
         "response": {"kind": "dismiss", "target": target("Acknowledge", role_name("button", "Acknowledge"))},
         "max_applications": 2},
        {"name": "native_alert", "description": "Accept alert",
         "when": {"kind": "dialog_open", "title_pattern": "^alert$"},
         "response": {"kind": "dismiss"}, "max_applications": 3},
        {"name": "transient_app_error", "description": "Retry", "when": text_visible("Internal Error. Reference ID"),
         "response": {"kind": "retry", "backoff_ms": 1500}, "max_applications": 1},
        {"name": "identity_verification", "description": "Human needed",
         "when": text_visible("Verify Member Identity"),
         "response": {"kind": "escalate", "reason": "Identity verification requires a human."},
         "max_applications": 1},
    ]


def lookup_capability_data() -> dict[str, Any]:
    return {
        "id": "test.member_lookup",
        "version": "1.0.0",
        "status": "approved",
        "title": "Member lookup",
        "description": "Find a member and read the savings balance.",
        "app": {"vendor": "Test Vendor", "product": "TestApp", "product_version": "1", "surface": "web"},
        "inputs": {"member_number": {"type": "string", "description": "Member number", "pattern": r"^\d+$"}},
        "outputs": {"balance": {"type": "decimal", "description": "Savings balance"}},
        "credentials": {"teller": {"description": "Teller sign-on"}},
        "steps": lookup_steps(),
        "checkpoint": text_visible("Member Detail"),
        "outcomes": lookup_outcomes(),
        "recoveries": lookup_recoveries(),
        "subflows": {"login": login_subflow()},
        "provenance": {"discovery_run_id": "disc-1", "recorded_at": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
                       "planner": "scripted", "goal": "look up a member"},
    }


def lookup_capability(**overrides: Any) -> Capability:
    data = lookup_capability_data()
    data.update(overrides)
    return Capability.model_validate(data)


# ---------------------------------------------------------------- the scripted app


INQUIRY_NODES = [text("Member Inquiry", 0), textbox("Member Number", 1), button("Search", 2)]
MEMBER_NODES = [text("Member Detail", 0), text("Balance: $1,250.00", 1)]


def lookup_screens() -> list[Screen]:
    return [
        Screen("blank", [], location="about:blank"),
        Screen("login", [text("Sign On", 0), textbox("User ID", 1), textbox("Password", 2), button("Sign On", 3)],
               location=LOGIN_URL),
        Screen("inquiry", list(INQUIRY_NODES)),
        Screen("member", list(MEMBER_NODES)),
        Screen("not_found", [text(f"No member found for number {MISSING_MEMBER}.", 0)]),
        Screen("restricted", [text("ACCESS DENIED: Member record is restricted (code 403-R)", 0)]),
        Screen("invalid", [*INQUIRY_NODES, text("Member number must be numeric.", 3)]),
        Screen("notice", [*INQUIRY_NODES, text("System Notice", 4), button("Acknowledge", 5)]),
        Screen("alert", [text("Printer queue offline", 0)],
               dialogs=[Dialog(title="alert", text="Printer queue offline", native=True)]),
        Screen("error", [text("Internal Error. Reference ID ERR-5521.", 0)]),
        Screen("expired", [text("Your session has expired. Please sign on again.", 0)]),
        Screen("identity", [*MEMBER_NODES, text("Verify Member Identity", 3)],
               dialogs=[Dialog(title="Verify Member Identity", text="Security question")]),
        Screen("loading", [text("Loading...", 0)]),
        Screen("find_inquiry", [text("Member Inquiry", 0), textbox("Member Number", 1), button("Find", 2)]),
        Screen("aliased_inquiry", [text("Member Inquiry", 0), textbox("Account Number", 1), button("Find", 2)]),
    ]


def route_member_search(values: Mapping[str, str]) -> str:
    member_number = values.get("Member Number", values.get("Account Number", "")).strip()
    if not member_number.isdigit():
        return "invalid"
    if member_number == KNOWN_MEMBER:
        return "member"
    if member_number == RESTRICTED_MEMBER:
        return "restricted"
    return "not_found"


def lookup_app(search_route: Route = route_member_search, after_sign_on: Route = "inquiry") -> ScriptedSurface:
    return ScriptedSurface(
        lookup_screens(),
        initial="blank",
        transitions={
            (f"open:{LOGIN_URL}", "open"): "login",
            ("Sign On", "click"): after_sign_on,
            ("Search", "click"): search_route,
            ("Find", "click"): search_route,
            ("Acknowledge", "click"): "inquiry",
            ("press:Enter", "press"): "member",
        },
    )


class Harness:
    """Engine + doubles wired together, with deterministic time."""

    def __init__(
        self,
        surface: ScriptedSurface | None = None,
        policy: FakePolicy | None = None,
        escalator: FakeEscalator | None = None,
        credentials: FakeCredentials | None = None,
    ) -> None:
        self.surface = surface or lookup_app()
        self.policy = policy or FakePolicy()
        self.evidence = MemoryEvidence()
        self.escalator = escalator
        self.credentials = credentials or FakeCredentials()
        self.secrets = SecretLog()
        self.clock = FakeClock()
        self.engine = ReplayEngine(
            self.surface,
            self.policy,
            self.evidence,
            self.credentials,
            escalator=self.escalator,
            secret_registrar=self.secrets,
            monotonic=self.clock.monotonic,
            sleep=self.clock.sleep,
            now=self.clock.now,
            poll_interval_ms=250,
            checkpoint_timeout_ms=2_000,
        )
