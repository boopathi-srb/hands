"""Run the mock target: `uv run python -m target_app --port 8700`."""

from __future__ import annotations

import argparse

import uvicorn

from target_app.app import create_app
from target_app.config import AppConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="target_app", description="CoreOne Member Services mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8700)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    arguments = parse_args(argv)
    app = create_app(AppConfig.from_env())
    uvicorn.run(app, host=arguments.host, port=arguments.port, log_level="info")


if __name__ == "__main__":
    main()
