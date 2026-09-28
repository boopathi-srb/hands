"""OllamaPlanner: a local vision model (default qwen3-vl:8b) through Ollama's /api/chat.

The request constrains output with `format` = the PlannerDecision JSON schema and attaches only the
current screenshot. Measured quirk of qwen3-vl on Ollama 0.32: with `think: false` the JSON answer
arrives in `message.thinking` while `message.content` is empty; with thinking on it arrives in
`content`. We parse `content` and fall back to `thinking`. Output is validated; anything invalid is
returned as an error response so the loop can re-prompt.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from hands.core.log import get_logger, log_failure
from hands.discovery.planner import (
    PlannerContext,
    PlannerResponse,
    TokenUsage,
    decision_json_schema,
    parse_decision_text,
)
from hands.discovery.prompts import SYSTEM_PROMPT, build_user_prompt
from hands.discovery.render import downscale_screenshot

_logger = get_logger(__name__)

DEFAULT_OLLAMA_MODEL = "qwen3-vl:8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
# Ollama defaults to a 4k context on small GPUs; screen text + screenshot overflow it silently.
DEFAULT_CONTEXT_TOKENS = 12_288
CHAT_PATH = "/api/chat"


class OllamaPlanner:
    """Implements the Planner port against a local Ollama server."""

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        think: bool = False,
        temperature: float = 0.0,
        timeout_s: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
        context_tokens: int = DEFAULT_CONTEXT_TOKENS,
    ) -> None:
        self.model = model
        self.name = "ollama"
        self._base_url = base_url.rstrip("/")
        self._think = think
        self._temperature = temperature
        self._timeout_s = timeout_s
        self._transport = transport
        self._context_tokens = context_tokens

    async def decide(self, context: PlannerContext) -> PlannerResponse:
        request_body = self.build_request(context)
        started = time.monotonic()
        http_result = await self._post_chat(request_body)
        latency_ms = int((time.monotonic() - started) * 1000)
        if isinstance(http_result, str):
            return PlannerResponse(error=http_result, latency_ms=latency_ms)
        return parse_chat_response(http_result, latency_ms)

    def build_request(self, context: PlannerContext) -> dict[str, Any]:
        user_message: dict[str, Any] = {"role": "user", "content": build_user_prompt(context)}
        screenshot = downscale_screenshot(context.screenshot_png)
        if screenshot is not None:
            user_message["images"] = [base64.b64encode(screenshot).decode("ascii")]
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, user_message],
            "stream": False,
            "think": self._think,
            "format": decision_json_schema(),
            "options": {"temperature": self._temperature, "num_ctx": self._context_tokens},
            "keep_alive": "30m",
        }

    async def _post_chat(self, request_body: dict[str, Any]) -> dict[str, Any] | str:
        """The decoded JSON body, or an error message. The only I/O boundary of this planner."""
        url = f"{self._base_url}{CHAT_PATH}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
                response = await client.post(url, json=request_body)
        except httpx.TimeoutException:
            log_failure(_logger, "OllamaPlanner._post_chat", "request timed out", url=url,
                        model=self.model, timeout_s=self._timeout_s)
            return f"ollama request timed out after {self._timeout_s}s"
        except httpx.HTTPError as http_error:
            log_failure(_logger, "OllamaPlanner._post_chat", str(http_error), url=url, model=self.model)
            return f"ollama request failed: {http_error}"
        return _decode_body(response, url, self.model)


def _decode_body(response: httpx.Response, url: str, model: str) -> dict[str, Any] | str:
    if response.status_code >= 400:
        log_failure(_logger, "OllamaPlanner._decode_body", "HTTP error status", url=url, model=model,
                    status=response.status_code, body=response.text[:200])
        return f"ollama returned HTTP {response.status_code}: {response.text[:200]}"
    try:
        payload = response.json()
    except ValueError as decode_error:
        log_failure(_logger, "OllamaPlanner._decode_body", str(decode_error), url=url, model=model)
        return "ollama returned a body that is not JSON"
    return payload if isinstance(payload, dict) else "ollama returned a JSON body that is not an object"


def answer_text(payload: dict[str, Any]) -> str:
    """The model's answer: message.content, else message.thinking (qwen3-vl with think=false)."""
    message = payload.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    thinking = message.get("thinking")
    return thinking if isinstance(thinking, str) else ""


def parse_chat_response(payload: dict[str, Any], latency_ms: int) -> PlannerResponse:
    raw_text = answer_text(payload)
    usage = TokenUsage(
        input_tokens=_int_field(payload, "prompt_eval_count"),
        output_tokens=_int_field(payload, "eval_count"),
    )
    parsed = parse_decision_text(raw_text)
    if parsed.decision is None:
        log_failure(_logger, "parse_chat_response", parsed.error or "no decision",
                    raw_text=raw_text[:300])
    return PlannerResponse(
        decision=parsed.decision, raw_text=raw_text, error=parsed.error, usage=usage,
        latency_ms=latency_ms,
    )


def _int_field(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) else 0
