from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from repo_newz.errors import ConfigError

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config.yaml"


@dataclass
class Config:
    repos: list[str]
    window_hours: int
    model: str
    vault_subpath: str
    anthropic_api_key: str
    github_token: str
    obsidian_home: Path


def load(config_path: Path | None = None, env_path: Path | None = None) -> Config:
    _load_env(env_path)

    anthropic_api_key = _require_env("ANTHROPIC_API_KEY")
    github_token = _require_env("GITHUB_TOKEN")
    obsidian_home = Path(_require_env("OBSIDIAN_HOME"))

    path = config_path or _DEFAULT_CONFIG
    raw = _load_yaml(path)

    repos = _validate_repos(raw)
    window_hours = int(raw.get("window_hours", 24))
    model = str(raw.get("model", "claude-sonnet-4-6"))
    vault_subpath = str(raw.get("vault_subpath", "{year}/repo-activity-{date}.md"))

    return Config(
        repos=repos,
        window_hours=window_hours,
        model=model,
        vault_subpath=vault_subpath,
        anthropic_api_key=anthropic_api_key,
        github_token=github_token,
        obsidian_home=obsidian_home,
    )


def _load_env(env_path: Path | None) -> None:
    if env_path:
        load_dotenv(env_path, override=True)
    else:
        candidate = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(candidate, override=False)


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise ConfigError(f"required env var {name!r} is not set")
    return val


def _load_yaml(path: Path) -> dict:
    try:
        with path.open() as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}")
    except yaml.YAMLError as exc:
        raise ConfigError(f"config.yaml parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("config.yaml must be a YAML mapping")
    return data


def _validate_repos(raw: dict) -> list[str]:
    repos = raw.get("repos")
    if not repos:
        raise ConfigError("config.yaml: 'repos' list is missing or empty")
    if not isinstance(repos, list):
        raise ConfigError("config.yaml: 'repos' must be a list")
    validated = []
    for entry in repos:
        if not isinstance(entry, str) or not _REPO_PATTERN.match(entry):
            raise ConfigError(
                f"config.yaml: invalid repo entry {entry!r} - expected 'owner/repo'"
            )
        validated.append(entry)
    return validated
