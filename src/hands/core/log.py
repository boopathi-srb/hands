"""Structured logging helper shared by every package."""

from __future__ import annotations

import logging
from typing import Any

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, configuring the root handler once."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO, format=_FORMAT)
    return logging.getLogger(name)


def log_failure(logger: logging.Logger, function_name: str, what_failed: str, **inputs: Any) -> None:
    """Log a failure with the function name, its (already redacted) inputs, and what failed."""
    rendered_inputs = ", ".join(f"{key}={value!r}" for key, value in inputs.items())
    logger.error("%s failed: %s | inputs: %s", function_name, what_failed, rendered_inputs)
