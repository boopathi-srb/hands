"""The API's one error shape, `{"error": code, "message": text}`, and handlers that keep FastAPI to it."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from hands.core.log import get_logger, log_failure

_logger: logging.Logger = get_logger(__name__)

HTTP_ERROR_CODES = {400: "bad_request", 401: "unauthorized", 404: "not_found", 405: "method_not_allowed",
                    409: "conflict", 422: "invalid_request"}


def error_response(status_code: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code, "message": message, **extra})


def validation_message(error: RequestValidationError) -> str:
    """'body.inputs: Input should be a valid dictionary; ...' from pydantic's error list."""
    parts = []
    for detail in error.errors():
        location = ".".join(str(segment) for segment in detail.get("loc", ()))
        parts.append(f"{location}: {detail.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid request"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        message = validation_message(error)
        log_failure(_logger, "request_validation", message, path=request.url.path)
        return error_response(422, "invalid_request", message)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = HTTP_ERROR_CODES.get(error.status_code, "http_error")
        return error_response(error.status_code, code, str(error.detail))
