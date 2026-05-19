from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repo_newz.config import load
from repo_newz.errors import ConfigError


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.yaml"
    with p.open("w") as f:
        yaml.dump(data, f)
    return p


def _write_env(tmp_path: Path, **kwargs) -> Path:
    p = tmp_path / ".env"
    lines = "\n".join(f"{k}={v}" for k, v in kwargs.items())
    p.write_text(lines + "\n")
    return p


_VALID_ENV = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "GITHUB_TOKEN": "ghp_test",
    "OBSIDIAN_HOME": "/tmp/vault",
}

_VALID_CONFIG = {
    "window_hours": 24,
    "model": "claude-sonnet-4-6",
    "vault_subpath": "{year}/repo-activity-{date}.md",
    "repos": ["owner/repo", "another/thing"],
}


class TestLoadHappyPath:
    def test_returns_config_with_correct_repos(self, tmp_path, monkeypatch):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert cfg.repos == ["owner/repo", "another/thing"]

    def test_returns_config_with_correct_model(self, tmp_path, monkeypatch):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert cfg.model == "claude-sonnet-4-6"

    def test_obsidian_home_is_path(self, tmp_path, monkeypatch):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert isinstance(cfg.obsidian_home, Path)


class TestMissingEnvVars:
    @pytest.mark.parametrize("missing", ["ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OBSIDIAN_HOME"])
    def test_missing_var_raises_config_error(self, tmp_path, monkeypatch, missing):
        env = {k: v for k, v in _VALID_ENV.items() if k != missing}
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, **env)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ConfigError) as exc_info:
            load(config_path=cfg_path, env_path=env_path)
        assert missing in str(exc_info.value)


class TestConfigYamlErrors:
    def test_missing_file_raises_config_error(self, tmp_path, monkeypatch):
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ConfigError, match="not found"):
            load(config_path=tmp_path / "nonexistent.yaml", env_path=env_path)

    def test_malformed_yaml_raises_config_error(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(": bad: yaml: [\n")
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ConfigError, match="parse error"):
            load(config_path=cfg_path, env_path=env_path)

    def test_missing_repos_key_raises_config_error(self, tmp_path, monkeypatch):
        data = {**_VALID_CONFIG}
        del data["repos"]
        cfg_path = _write_config(tmp_path, data)
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ConfigError, match="repos"):
            load(config_path=cfg_path, env_path=env_path)

    def test_empty_repos_list_raises_config_error(self, tmp_path, monkeypatch):
        data = {**_VALID_CONFIG, "repos": []}
        cfg_path = _write_config(tmp_path, data)
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ConfigError, match="repos"):
            load(config_path=cfg_path, env_path=env_path)

    def test_bad_repo_entry_raises_config_error_naming_entry(self, tmp_path, monkeypatch):
        data = {**_VALID_CONFIG, "repos": ["owner/repo", "notvalid"]}
        cfg_path = _write_config(tmp_path, data)
        env_path = _write_env(tmp_path, **_VALID_ENV)
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ConfigError, match="notvalid"):
            load(config_path=cfg_path, env_path=env_path)


class TestPathResolution:
    def test_vault_path_resolves_correctly(self, tmp_path, monkeypatch):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, ANTHROPIC_API_KEY="k", GITHUB_TOKEN="t",
                              OBSIDIAN_HOME="/my/vault")
        for k in _VALID_ENV:
            monkeypatch.delenv(k, raising=False)
        cfg = load(config_path=cfg_path, env_path=env_path)
        path = cfg.obsidian_home / cfg.vault_subpath.format(year="2026", date="20260519")
        assert str(path) == "/my/vault/2026/repo-activity-20260519.md"
