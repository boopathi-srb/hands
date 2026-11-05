"""API settings from the environment, and seeding an empty data directory with the repo's artifacts.

| Env                  | Meaning                                                    | Default                      |
|----------------------|------------------------------------------------------------|------------------------------|
| HANDS_API_TOKEN      | bearer token for /api and /console (health stays public)   | unset: no auth               |
| HANDS_CORS_ORIGINS   | comma-separated allowed origins                            | none                         |
| HANDS_DATA_DIR       | holds `artifacts/` and `runs/` (a Railway volume)          | repo root                    |
| HANDS_EVIDENCE_ROOT  | where run evidence directories go                          | `<data>/runs`, or            |
|                      |                                                            | `<repo>/evidence/runs` local |
| HANDS_SURFACE        | `web` (Playwright) or `fake` (in-memory CoreOne, tests)    | web                          |
| HANDS_TARGET_URL     | CoreOne mock base URL                                      | http://127.0.0.1:8700        |
| HANDS_HEADLESS       | `0` shows the browser window                               | 1                            |
| HANDS_OLLAMA_URL     | Ollama base URL probed by /api/health                      | http://localhost:11434       |
| HANDS_WEB_DIST       | built UI directory served at `/`                           | `<repo>/web/dist`            |
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hands.core.log import get_logger, log_failure
from hands.runtime.assembly import SurfaceChoice

_logger: logging.Logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TARGET_URL = "http://127.0.0.1:8700"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
SURFACE_CHOICES: tuple[SurfaceChoice, ...] = ("web", "fake")
FALSE_FLAGS = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class ApiSettings:
    data_dir: Path
    evidence_root: Path
    repo_root: Path = REPO_ROOT
    api_token: str | None = None
    cors_origins: tuple[str, ...] = ()
    surface: SurfaceChoice = "web"
    target_url: str = DEFAULT_TARGET_URL
    headless: bool = True
    ollama_url: str = DEFAULT_OLLAMA_URL
    web_dist_dir: Path = field(default_factory=lambda: REPO_ROOT / "web" / "dist")
    anthropic_key_present: bool = False
    escalation_timeout_s: float | None = 900.0

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def seed_artifacts_dir(self) -> Path:
        return self.repo_root / "artifacts"

    @property
    def policy_path(self) -> Path:
        return self.repo_root / "policies" / "coreone.yaml"

    @property
    def profile_path(self) -> Path:
        return self.repo_root / "profiles" / "coreone.yaml"

    @property
    def auth_required(self) -> bool:
        return bool(self.api_token)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ApiSettings:
        source = os.environ if environ is None else environ
        data_dir = _path_or(source.get("HANDS_DATA_DIR"), REPO_ROOT)
        return cls(
            data_dir=data_dir,
            evidence_root=default_evidence_root(source, data_dir),
            api_token=source.get("HANDS_API_TOKEN") or None,
            cors_origins=parse_origins(source.get("HANDS_CORS_ORIGINS")),
            surface=parse_surface(source.get("HANDS_SURFACE")),
            target_url=(source.get("HANDS_TARGET_URL") or DEFAULT_TARGET_URL).rstrip("/"),
            headless=parse_flag(source.get("HANDS_HEADLESS"), default=True),
            ollama_url=(source.get("HANDS_OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/"),
            web_dist_dir=_path_or(source.get("HANDS_WEB_DIST"), REPO_ROOT / "web" / "dist"),
            anthropic_key_present=bool(source.get("ANTHROPIC_API_KEY")),
        )


def default_evidence_root(source: Mapping[str, str], data_dir: Path) -> Path:
    """HANDS_EVIDENCE_ROOT wins; a configured data dir uses `<data>/runs`; locally the repo's evidence/runs."""
    explicit_root = source.get("HANDS_EVIDENCE_ROOT")
    if explicit_root:
        return Path(explicit_root)
    if source.get("HANDS_DATA_DIR"):
        return data_dir / "runs"
    return REPO_ROOT / "evidence" / "runs"


def parse_origins(raw_origins: str | None) -> tuple[str, ...]:
    """'https://a.app, https://b.app,' -> ('https://a.app', 'https://b.app'); empty/None -> ()."""
    if not raw_origins:
        return ()
    return tuple(origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip())


def parse_surface(raw_surface: str | None) -> SurfaceChoice:
    """`web` or `fake`; anything else (logged) falls back to `web`."""
    if not raw_surface:
        return "web"
    cleaned = raw_surface.strip().lower()
    if cleaned == "fake":
        return "fake"
    if cleaned != "web":
        log_failure(_logger, "parse_surface", "unknown surface, using web", surface=raw_surface)
    return "web"


def parse_flag(raw_flag: str | None, default: bool) -> bool:
    if raw_flag is None or not raw_flag.strip():
        return default
    return raw_flag.strip().lower() not in FALSE_FLAGS


def _path_or(raw_path: str | None, fallback: Path) -> Path:
    return Path(raw_path) if raw_path else fallback


SeedStatus = Literal["seeded", "already_present", "same_directory", "no_seed", "failed"]


@dataclass(frozen=True)
class SeedResult:
    status: SeedStatus
    message: str = ""


def seed_artifacts(seed_dir: Path, artifacts_dir: Path) -> SeedResult:
    """Copy the repo's artifacts into an empty data dir (a fresh Railway volume). Never overwrites."""
    if _same_directory(seed_dir, artifacts_dir):
        return SeedResult("same_directory")
    if _has_capabilities(artifacts_dir):
        return SeedResult("already_present")
    if not _has_capabilities(seed_dir):
        log_failure(_logger, "seed_artifacts", "no seed artifacts to copy", seed_dir=str(seed_dir))
        return SeedResult("no_seed", f"no artifacts under {seed_dir}")
    return _copy_tree(seed_dir, artifacts_dir)


def _same_directory(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve()


def _has_capabilities(artifacts_dir: Path) -> bool:
    return artifacts_dir.is_dir() and any(path.is_dir() for path in artifacts_dir.iterdir())


def _copy_tree(seed_dir: Path, artifacts_dir: Path) -> SeedResult:
    try:  # file-system I/O boundary
        shutil.copytree(seed_dir, artifacts_dir, dirs_exist_ok=True)
    except OSError as copy_error:
        log_failure(_logger, "seed_artifacts", repr(copy_error), seed_dir=str(seed_dir),
                    artifacts_dir=str(artifacts_dir))
        return SeedResult("failed", str(copy_error))
    _logger.info("seeded artifacts from %s into %s", seed_dir, artifacts_dir)
    return SeedResult("seeded")
