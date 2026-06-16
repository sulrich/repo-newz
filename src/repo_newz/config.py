from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from repo_newz.errors import ConfigError

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_DEFAULT_CONFIG = Path.home() / ".config" / "repo-newz" / "config.yaml"

# hugo project config filenames, in priority order
_HUGO_CONFIGS = ("config.toml", "hugo.toml")


@dataclass
class Config:
    repos: list[str]
    window_hours: int
    model: str
    anthropic_api_key: str
    github_token: str
    hugo_site_dir: Path
    hugo_content_dir: Path
    hugo_publish_dir: Path
    hugo_base_url: str
    hugo_section: str


def load(config_path: Path | None = None, env_path: Path | None = None) -> Config:
    _load_env(env_path)

    anthropic_api_key = _require_env("ANTHROPIC_API_KEY")
    github_token = _require_env("GITHUB_TOKEN")
    hugo_site_dir = Path(_require_env("HUGO_SITE_DIR"))
    hugo_content_dir = Path(_require_env("HUGO_CONTENT_DIR"))
    hugo_publish_dir = Path(_require_env("HUGO_PUBLISH_DIR"))

    path = config_path or _DEFAULT_CONFIG
    raw = _load_yaml(path)

    repos = _validate_repos(raw)
    window_hours = int(raw.get("window_hours", 24))
    model = str(raw.get("model", "claude-sonnet-4-6"))

    hugo_base_url = _read_base_url(hugo_site_dir)
    hugo_section = _content_section(hugo_site_dir, hugo_content_dir)

    return Config(
        repos=repos,
        window_hours=window_hours,
        model=model,
        anthropic_api_key=anthropic_api_key,
        github_token=github_token,
        hugo_site_dir=hugo_site_dir,
        hugo_content_dir=hugo_content_dir,
        hugo_publish_dir=hugo_publish_dir,
        hugo_base_url=hugo_base_url,
        hugo_section=hugo_section,
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


def _read_base_url(site_dir: Path) -> str:
    """read baseURL from the hugo project config (config.toml / hugo.toml)."""
    for name in _HUGO_CONFIGS:
        cfg_file = site_dir / name
        if not cfg_file.exists():
            continue
        try:
            with cfg_file.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"hugo {name} parse error: {exc}") from exc
        base = str(data.get("baseURL", "")).strip()
        if not base:
            raise ConfigError(f"baseURL missing from {cfg_file}")
        return base.rstrip("/")
    raise ConfigError(
        f"no hugo config ({' or '.join(_HUGO_CONFIGS)}) found under {site_dir}"
    )


def _content_section(site_dir: Path, content_dir: Path) -> str:
    """derive the hugo url section from the content dir's path under content/."""
    content_root = (site_dir / "content").resolve()
    target = content_dir.resolve()
    try:
        rel = target.relative_to(content_root)
    except ValueError:
        raise ConfigError(
            f"HUGO_CONTENT_DIR {content_dir} is not under {content_root}"
        )
    return rel.as_posix()
