"""AnthropicPlanner: Claude through the official `anthropic` SDK, one `act` tool call per turn.

Request shape (per the claude-api skill): adaptive thinking with `output_config.effort` (no
budget_tokens, no assistant prefill), one strict tool `act` whose input schema is the PlannerDecision
schema, `tool_choice` auto with a system instruction to always call `act`, and `cache_control` on the
stable system prompt (tools render before system, so the one breakpoint caches both).

Each turn is a single fresh user message: the compact history is text, and only the current
screenshot is attached, so older screenshots are never resent. Never raises: a missing API key,
transport errors, refusals and malformed tool input all come back as error responses.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Protocol

import anthropic

from hands.core.log import get_logger, log_failure
from hands.discovery.planner import (
    PlannerContext,
    PlannerResponse,
    TokenUsage,
    decision_json_schema,
    parse_decision_payload,
)
from hands.discovery.prompts import SYSTEM_PROMPT, build_user_prompt
from hands.discovery.render import downscale_screenshot

_logger = get_logger(__name__)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "medium"
DEFAULT_MAX_TOKENS = 16_000
API_KEY_ENV = "ANTHROPIC_API_KEY"
ACT_TOOL_NAME = "act"
TOOL_INSTRUCTION = (
    "\n\nAlways answer by calling the `act` tool exactly once with your decision. Do not reply with "
    "plain text."
)
ACT_TOOL: dict[str, Any] = {
    "name": ACT_TOOL_NAME,
    "description": (
        "Perform exactly one UI action (or report done/stuck) on the current screen. "
        "node_ref must be a ref from the current SCREEN listing."
    ),
    "strict": True,
    "input_schema": decision_json_schema(),
}


class MessagesApi(Protocol):
    async def create(self, **request: Any) -> Any: ...


class AnthropicClient(Protocol):
    @property
    def messages(self) -> MessagesApi: ...


AnyClient = AnthropicClient | anthropic.AsyncAnthropic


class AnthropicPlanner:
    """Implements the Planner port with Claude. Inject `client` in tests; never call the live API there."""

    def __init__(
        self,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        effort: str = DEFAULT_EFFORT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = 180.0,
        client: AnyClient | None = None,
    ) -> None:
        self.model = model
        self.name = "anthropic"
        self._effort = effort
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        self._client: AnyClient | None = client

    async def decide(self, context: PlannerContext) -> PlannerResponse:
        client = self._client_or_none()
        if client is None:
            return PlannerResponse(error=f"{API_KEY_ENV} is not set; the Anthropic planner cannot run")
        request = self.build_request(context)
        started = time.monotonic()
        api_result = await self._create_message(client, request)
        latency_ms = int((time.monotonic() - started) * 1000)
        if isinstance(api_result, str):
            return PlannerResponse(error=api_result, latency_ms=latency_ms)
        return parse_message(api_result, latency_ms)

    def build_request(self, context: PlannerContext) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": [{
                "type": "text",
                "text": SYSTEM_PROMPT + TOOL_INSTRUCTION,
                "cache_control": {"type": "ephemeral"},
            }],
            "tools": [ACT_TOOL],
            "tool_choice": {"type": "auto"},
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._effort},
            "messages": [{"role": "user", "content": user_content(context)}],
        }

    def _client_or_none(self) -> AnyClient | None:
        if self._client is not None:
            return self._client
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            log_failure(_logger, "AnthropicPlanner._client_or_none", "missing API key",
                        env=API_KEY_ENV, model=self.model)
            return None
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=self._timeout_s)
        return self._client

    async def _create_message(self, client: AnyClient, request: dict[str, Any]) -> Any:
        """The Message, or an error message. The only I/O boundary of this planner."""
        try:
            return await client.messages.create(**request)
        except anthropic.AuthenticationError as auth_error:
            return _api_failure("authentication failed", auth_error, self.model)
        except anthropic.RateLimitError as rate_error:
            return _api_failure("rate limited", rate_error, self.model)
        except anthropic.APIStatusError as status_error:
            return _api_failure(f"API error {status_error.status_code}", status_error, self.model)
        except anthropic.APITimeoutError as timeout_error:
            return _api_failure("request timed out", timeout_error, self.model)
        except anthropic.APIConnectionError as connection_error:
            return _api_failure("connection failed", connection_error, self.model)


def _api_failure(what_failed: str, api_error: Exception, model: str) -> str:
    log_failure(_logger, "AnthropicPlanner._create_message", f"{what_failed}: {api_error}", model=model)
    return f"anthropic {what_failed}: {api_error}"


def user_content(context: PlannerContext) -> list[dict[str, Any]]:
    """Current screenshot (if any) followed by the text prompt."""
    blocks: list[dict[str, Any]] = []
    screenshot = downscale_screenshot(context.screenshot_png)
    if screenshot is not None:
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(screenshot).decode("ascii"),
            },
        })
    blocks.append({"type": "text", "text": build_user_prompt(context)})
    return blocks


def parse_message(message: Any, latency_ms: int) -> PlannerResponse:
    """Turn an SDK Message into a PlannerResponse, checking stop_reason before reading content."""
    usage = _usage_of(message)
    stop_reason = getattr(message, "stop_reason", None)
    text = _text_of(message)
    if stop_reason == "refusal":
        return _refusal_response(message, text, usage, latency_ms)
    if stop_reason == "max_tokens":
        return PlannerResponse(error="response hit max_tokens before a complete decision",
                               raw_text=text, usage=usage, latency_ms=latency_ms)
    tool_input = _act_tool_input(message)
    if tool_input is None:
        return PlannerResponse(error=f"model did not call the {ACT_TOOL_NAME} tool",
                               raw_text=text, usage=usage, latency_ms=latency_ms)
    parsed = parse_decision_payload(tool_input)
    return PlannerResponse(decision=parsed.decision, error=parsed.error, raw_text=json.dumps(tool_input, default=str),
                           usage=usage, latency_ms=latency_ms)


def _refusal_response(message: Any, text: str, usage: TokenUsage, latency_ms: int) -> PlannerResponse:
    details = getattr(message, "stop_details", None)
    category = getattr(details, "category", None) if details is not None else None
    log_failure(_logger, "parse_message", "model refused", category=category)
    return PlannerResponse(error=f"model refused (category: {category or 'unspecified'})",
                           raw_text=text, usage=usage, latency_ms=latency_ms)


def _act_tool_input(message: Any) -> object | None:
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == ACT_TOOL_NAME:
            return getattr(block, "input", None)
    return None


def _text_of(message: Any) -> str:
    texts = [
        getattr(block, "text", "") for block in getattr(message, "content", None) or []
        if getattr(block, "type", None) == "text"
    ]
    return "\n".join(text for text in texts if text)


def _usage_of(message: Any) -> TokenUsage:
    usage = getattr(message, "usage", None)
    if usage is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )
