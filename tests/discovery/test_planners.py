from __future__ import annotations

import base64
import json
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
from anthropic.types import Message

from hands.discovery.planner import PlannerContext, PlannerDecision
from hands.discovery.planners.anthropic import ACT_TOOL_NAME, AnthropicPlanner, parse_message
from hands.discovery.planners.ollama import OllamaPlanner, answer_text, parse_chat_response
from hands.discovery.planners.scripted import (
    ScriptedPlanner,
    ScriptRule,
    always,
    click,
    coreone_member_balance_script,
    decision,
    done,
    extract_near,
    find_ref,
    find_ref_near,
    listed_nodes,
    press,
    screen_has,
    type_into,
)

from .helpers import planner_context, png_bytes

SCREEN_LINES = (
    "LOCATION: http://x/t/lakeside/main",
    "-- frame:content --",
    '[n1] cell "Regular Savings"',
    '[n2] cell "1,250.00"',
    '[n3] textbox "Member Number" value=""',
    '[n4] button "Search"',
)
SCREEN = "\n".join(SCREEN_LINES)
VALID_DECISION = {"rationale": "search", "action": "click", "node_ref": "n4", "value": None, "key": None,
                  "option": None, "output_name": None, "expected_result": None}


# ---------------------------------------------------------------- scripted


def test_listing_helpers() -> None:
    assert [node.ref for node in listed_nodes(SCREEN)] == ["n1", "n2", "n3", "n4"]
    assert find_ref(SCREEN, "BUTTON", "search") == "n4"
    assert find_ref(SCREEN, "button", "Missing") is None
    assert find_ref_near(SCREEN, "Regular Savings", 1) == "n2"
    assert find_ref_near(SCREEN, "Regular Savings", -1) is None
    assert find_ref_near(SCREEN, "Nope", 1) is None
    assert listed_nodes("") == []


async def test_scripted_rules_fire_in_order_once() -> None:
    planner = ScriptedPlanner([
        ScriptRule("type", screen_has('textbox "Member Number"'),
                   type_into("textbox", "Member Number", "{{member_number}}")),
        ScriptRule("search", screen_has('button "Search"'), click("button", "Search")),
    ])
    first = await planner.decide(planner_context(SCREEN))
    second = await planner.decide(planner_context(SCREEN))
    third = await planner.decide(planner_context(SCREEN))
    assert first.decision is not None and first.decision.value == "{{member_number}}"
    assert second.decision is not None and second.decision.node_ref == "n4"
    assert third.decision is not None and third.decision.action == "stuck"
    assert planner.fired == ["type", "search"]


async def test_scripted_rule_without_target_falls_through() -> None:
    planner = ScriptedPlanner([
        ScriptRule("missing", always(), click("button", "Nope")),
        ScriptRule("repeat", always(), press("Enter"), once=False),
    ])
    for _ in range(2):
        response = await planner.decide(planner_context(SCREEN))
        assert response.decision is not None and response.decision.key == "Enter"
    assert planner.fired == ["repeat", "repeat"]


async def test_scripted_factories() -> None:
    context = planner_context(SCREEN)
    extracted = extract_near("Regular Savings", 1, "savings_balance")(context)
    assert extracted is not None and extracted.node_ref == "n2" and extracted.action == "extract"
    assert extract_near("Unknown", 1, "x")(context) is None
    assert type_into("textbox", "Nope", "x")(context) is None
    assert done()(context).action == "done"  # type: ignore[union-attr]
    fixed = PlannerDecision(rationale="r", action="scroll")
    assert decision(fixed)(context) is fixed


def test_coreone_script_supports_both_tenants() -> None:
    assert coreone_member_balance_script("prairie").name == "scripted"
    assert coreone_member_balance_script("unknown-tenant").name == "scripted"


# ---------------------------------------------------------------- ollama


def _ollama_planner(handler: Any) -> OllamaPlanner:
    return OllamaPlanner(transport=httpx.MockTransport(handler), timeout_s=5)


def _context_with_screenshot() -> PlannerContext:
    return planner_context(SCREEN, screenshot_png=png_bytes(2000, 1000))


async def test_ollama_parses_content_and_sends_schema_and_image() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(VALID_DECISION)},
                                         "prompt_eval_count": 120, "eval_count": 30})

    response = await _ollama_planner(handler).decide(_context_with_screenshot())
    assert response.error is None and response.decision is not None
    assert response.decision.node_ref == "n4"
    assert response.usage.input_tokens == 120 and response.usage.output_tokens == 30
    assert captured["think"] is False and captured["stream"] is False
    assert captured["format"]["additionalProperties"] is False
    assert captured["options"] == {"temperature": 0.0, "num_ctx": 12_288}
    images = captured["messages"][1]["images"]
    assert len(images) == 1 and base64.b64decode(images[0]).startswith(b"\x89PNG")
    assert captured["messages"][0]["role"] == "system"


async def test_ollama_falls_back_to_thinking_when_content_is_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "", "thinking": json.dumps(VALID_DECISION)}})

    response = await _ollama_planner(handler).decide(planner_context(SCREEN))
    assert response.decision is not None and response.decision.action == "click"


async def test_ollama_without_screenshot_sends_no_images() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(VALID_DECISION)}})

    await _ollama_planner(handler).decide(planner_context(SCREEN))
    assert "images" not in captured["messages"][1]


async def test_ollama_invalid_json_is_an_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "{not json"}})

    response = await _ollama_planner(handler).decide(planner_context(SCREEN))
    assert response.decision is None and response.error is not None
    assert response.raw_text == "{not json"


async def test_ollama_timeout_is_an_error_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    response = await _ollama_planner(handler).decide(planner_context(SCREEN))
    assert response.decision is None and response.error is not None and "timed out" in response.error


async def test_ollama_connection_and_http_errors() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model not found")

    def not_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    assert "request failed" in ((await _ollama_planner(refused).decide(planner_context(SCREEN))).error or "")
    assert "HTTP 500" in ((await _ollama_planner(server_error).decide(planner_context(SCREEN))).error or "")
    assert "not JSON" in ((await _ollama_planner(not_json).decide(planner_context(SCREEN))).error or "")


def test_answer_text_edge_cases() -> None:
    assert answer_text({}) == ""
    assert answer_text({"message": "text"}) == ""
    assert answer_text({"message": {"content": "  ", "thinking": None}}) == ""
    assert parse_chat_response({"message": {"content": "x"}, "eval_count": "n/a"}, 5).usage.output_tokens == 0


# ---------------------------------------------------------------- anthropic


def _message(content: list[dict[str, Any]], stop_reason: str = "tool_use", **extra: Any) -> Message:
    return Message.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 60, "cache_read_input_tokens": 800}, **extra,
    })


def _tool_use(tool_input: dict[str, Any], name: str = ACT_TOOL_NAME) -> dict[str, Any]:
    return {"type": "tool_use", "id": "toolu_1", "name": name, "input": tool_input}


class FakeMessages:
    def __init__(self, result: Message | Exception) -> None:
        self._result = result
        self.requests: list[dict[str, Any]] = []

    async def create(self, **request: Any) -> Message:
        self.requests.append(request)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeClient:
    def __init__(self, result: Message | Exception) -> None:
        self.messages = FakeMessages(result)


async def test_anthropic_parses_act_tool_use_and_builds_request() -> None:
    client = FakeClient(_message([{"type": "text", "text": "Clicking."}, _tool_use(VALID_DECISION)]))
    planner = AnthropicPlanner(client=client)
    response = await planner.decide(_context_with_screenshot())
    assert response.error is None and response.decision is not None
    assert response.decision.node_ref == "n4"
    assert response.usage.cache_read_input_tokens == 800
    request = client.messages.requests[0]
    assert request["model"] == "claude-sonnet-5"
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "medium"}
    assert request["tool_choice"] == {"type": "auto"}
    assert request["tools"][0]["strict"] is True and request["tools"][0]["name"] == ACT_TOOL_NAME
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "budget_tokens" not in json.dumps(request["thinking"])
    assert [message["role"] for message in request["messages"]] == ["user"]
    blocks = request["messages"][0]["content"]
    assert [block["type"] for block in blocks] == ["image", "text"]


async def test_anthropic_without_screenshot_sends_text_only() -> None:
    client = FakeClient(_message([_tool_use(VALID_DECISION)]))
    await AnthropicPlanner(client=client).decide(planner_context(SCREEN))
    assert [block["type"] for block in client.messages.requests[0]["messages"][0]["content"]] == ["text"]


async def test_anthropic_refusal_is_an_error_response() -> None:
    refusal = _message([], stop_reason="refusal",
                       stop_details={"type": "refusal", "category": "cyber", "explanation": "no"})
    response = await AnthropicPlanner(client=FakeClient(refusal)).decide(planner_context(SCREEN))
    assert response.decision is None and response.error is not None and "refused" in response.error


def test_anthropic_other_stop_reasons_and_bad_tool_input() -> None:
    assert "max_tokens" in (parse_message(_message([], stop_reason="max_tokens"), 1).error or "")
    no_tool = parse_message(_message([{"type": "text", "text": "hi"}], stop_reason="end_turn"), 1)
    assert no_tool.error == f"model did not call the {ACT_TOOL_NAME} tool" and no_tool.raw_text == "hi"
    other_tool = parse_message(_message([_tool_use(VALID_DECISION, name="other")]), 1)
    assert other_tool.decision is None
    bad_input = parse_message(_message([_tool_use({"action": "fly", "rationale": "r"})]), 1)
    assert bad_input.decision is None and bad_input.error is not None


async def test_anthropic_missing_key_is_an_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = await AnthropicPlanner().decide(planner_context(SCREEN))
    assert response.decision is None and response.error is not None and "ANTHROPIC_API_KEY" in response.error


async def test_anthropic_api_errors_are_error_responses() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    for api_error in (anthropic.APIConnectionError(request=request), anthropic.APITimeoutError(request=request)):
        response = await AnthropicPlanner(client=FakeClient(api_error)).decide(planner_context(SCREEN))
        assert response.decision is None and response.error is not None and response.error.startswith("anthropic")
    status_error = anthropic.InternalServerError(
        "boom", response=httpx2.Response(500, request=request), body=None
    )
    response = await AnthropicPlanner(client=FakeClient(status_error)).decide(planner_context(SCREEN))
    assert response.error is not None and "API error 500" in response.error


def test_ollama_request_sets_context_window_and_keep_alive() -> None:
    from hands.discovery.planners.ollama import DEFAULT_CONTEXT_TOKENS, OllamaPlanner

    default_body = OllamaPlanner().build_request(_context_with_screenshot())
    custom_body = OllamaPlanner(context_tokens=8192).build_request(_context_with_screenshot())
    assert default_body["options"]["num_ctx"] == DEFAULT_CONTEXT_TOKENS
    assert custom_body["options"]["num_ctx"] == 8192
    assert default_body["keep_alive"] == "30m"
