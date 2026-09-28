"""Registers the `desktop` marker: tests that drive a real macOS app through the AX API."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "desktop: uses the real macOS Accessibility API; skipped when AXIsProcessTrusted() is false",
    )
