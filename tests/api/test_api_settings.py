"""Unit tests: settings from env and seeding an empty data dir."""

from __future__ import annotations

from pathlib import Path

import pytest

from hands.api.settings import (
    REPO_ROOT,
    ApiSettings,
    default_evidence_root,
    parse_flag,
    parse_origins,
    parse_surface,
    seed_artifacts,
)


def test_from_env_defaults_use_the_repo_locally() -> None:
    settings = ApiSettings.from_env({})

    assert settings.data_dir == REPO_ROOT
    assert settings.artifacts_dir == REPO_ROOT / "artifacts"
    assert settings.evidence_root == REPO_ROOT / "evidence" / "runs"
    assert settings.surface == "web" and settings.headless is True
    assert settings.target_url == "http://127.0.0.1:8700"
    assert settings.api_token is None and settings.auth_required is False
    assert settings.cors_origins == () and settings.anthropic_key_present is False
    assert settings.policy_path.is_file() and settings.profile_path.is_file()


def test_from_env_reads_every_variable(tmp_path: Path) -> None:
    settings = ApiSettings.from_env({
        "HANDS_API_TOKEN": "t", "HANDS_CORS_ORIGINS": "https://a.app/, https://b.app", "HANDS_DATA_DIR": str(tmp_path),
        "HANDS_SURFACE": "fake", "HANDS_TARGET_URL": "http://core:9000/", "HANDS_HEADLESS": "0",
        "HANDS_OLLAMA_URL": "http://ollama:1/", "HANDS_WEB_DIST": str(tmp_path / "ui"), "ANTHROPIC_API_KEY": "k",
    })

    assert settings.auth_required and settings.api_token == "t"
    assert settings.cors_origins == ("https://a.app", "https://b.app")
    assert settings.artifacts_dir == tmp_path / "artifacts" and settings.evidence_root == tmp_path / "runs"
    assert settings.surface == "fake" and settings.headless is False
    assert settings.target_url == "http://core:9000" and settings.ollama_url == "http://ollama:1"
    assert settings.web_dist_dir == tmp_path / "ui" and settings.anthropic_key_present


def test_empty_token_means_no_auth() -> None:
    assert ApiSettings.from_env({"HANDS_API_TOKEN": ""}).auth_required is False


def test_default_evidence_root_precedence(tmp_path: Path) -> None:
    assert default_evidence_root({"HANDS_EVIDENCE_ROOT": "/x", "HANDS_DATA_DIR": "/d"}, tmp_path) == Path("/x")
    assert default_evidence_root({"HANDS_DATA_DIR": str(tmp_path)}, tmp_path) == tmp_path / "runs"
    assert default_evidence_root({}, tmp_path) == REPO_ROOT / "evidence" / "runs"


@pytest.mark.parametrize(("raw", "expected"), [
    (None, ()), ("", ()), (" , ", ()), ("https://a.app", ("https://a.app",)),
    ("https://a.app/,https://b.app,", ("https://a.app", "https://b.app")),
])
def test_parse_origins(raw: str | None, expected: tuple[str, ...]) -> None:
    assert parse_origins(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [(None, "web"), ("", "web"), ("FAKE", "fake"), ("web", "web"),
                                               ("desktop", "web")])
def test_parse_surface(raw: str | None, expected: str) -> None:
    assert parse_surface(raw) == expected


@pytest.mark.parametrize(("raw", "default", "expected"), [
    (None, True, True), ("", False, False), ("1", False, True), ("0", True, False), ("false", True, False),
    ("yes", False, True), (" OFF ", True, False),
])
def test_parse_flag(raw: str | None, default: bool, expected: bool) -> None:
    assert parse_flag(raw, default) is expected


def _seed_tree(root: Path) -> Path:
    (root / "cap.one").mkdir(parents=True)
    (root / "cap.one" / "1.0.0.json").write_text("{}")
    return root


def test_seed_copies_into_an_empty_data_dir(tmp_path: Path) -> None:
    seed = _seed_tree(tmp_path / "seed")
    result = seed_artifacts(seed, tmp_path / "data" / "artifacts")

    assert result.status == "seeded"
    assert (tmp_path / "data" / "artifacts" / "cap.one" / "1.0.0.json").is_file()


def test_seed_never_overwrites_existing_artifacts(tmp_path: Path) -> None:
    seed = _seed_tree(tmp_path / "seed")
    existing = tmp_path / "artifacts"
    (existing / "mine").mkdir(parents=True)

    assert seed_artifacts(seed, existing).status == "already_present"
    assert not (existing / "cap.one").exists()


def test_seed_skips_same_directory_and_missing_seed(tmp_path: Path) -> None:
    seed = _seed_tree(tmp_path / "seed")
    assert seed_artifacts(seed, seed).status == "same_directory"
    assert seed_artifacts(tmp_path / "none", tmp_path / "artifacts").status == "no_seed"
    (tmp_path / "empty").mkdir()
    assert seed_artifacts(tmp_path / "empty", tmp_path / "artifacts").status == "no_seed"


def test_seed_reports_copy_failure(tmp_path: Path) -> None:
    seed = _seed_tree(tmp_path / "seed")
    blocker = tmp_path / "artifacts"
    blocker.write_text("a file where the directory should go")
    result = seed_artifacts(seed, blocker)
    assert result.status == "failed" and result.message
