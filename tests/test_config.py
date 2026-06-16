from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repo_newz.config import load
from repo_newz.errors import ConfigError

_HUGO_VARS = ("HUGO_SITE_DIR", "HUGO_CONTENT_DIR", "HUGO_PUBLISH_DIR")
_ALL_VARS = ("ANTHROPIC_API_KEY", "GITHUB_TOKEN", *_HUGO_VARS)

_VALID_CONFIG = {
    "window_hours": 24,
    "model": "claude-sonnet-4-6",
    "repos": ["owner/repo", "another/thing"],
}


def _make_hugo_site(tmp_path: Path, base_url: str = "https://dyn.botwerks.net/") -> Path:
    """create a minimal hugo site (config.toml + content/repo-newz) under tmp_path."""
    site = tmp_path / "site"
    (site / "content" / "repo-newz").mkdir(parents=True)
    (site / "config.toml").write_text(f'baseURL = "{base_url}"\n')
    (tmp_path / "www").mkdir(exist_ok=True)
    return site


def _valid_env(tmp_path: Path) -> dict:
    site = _make_hugo_site(tmp_path)
    return {
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "GITHUB_TOKEN": "ghp_test",
        "HUGO_SITE_DIR": str(site),
        "HUGO_CONTENT_DIR": str(site / "content" / "repo-newz"),
        "HUGO_PUBLISH_DIR": str(tmp_path / "www"),
    }


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.yaml"
    with p.open("w") as f:
        yaml.dump(data, f)
    return p


def _write_env(tmp_path: Path, env: dict) -> Path:
    p = tmp_path / ".env"
    lines = "\n".join(f"{k}={v}" for k, v in env.items())
    p.write_text(lines + "\n")
    return p


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in _ALL_VARS:
        monkeypatch.delenv(k, raising=False)


def test_default_config_path():
    from repo_newz.config import _DEFAULT_CONFIG

    assert _DEFAULT_CONFIG == Path.home() / ".config" / "repo-newz" / "config.yaml"


class TestLoadHappyPath:
    def test_returns_config_with_correct_repos(self, tmp_path):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert cfg.repos == ["owner/repo", "another/thing"]

    def test_returns_config_with_correct_model(self, tmp_path):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert cfg.model == "claude-sonnet-4-6"

    def test_hugo_paths_are_paths(self, tmp_path):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert isinstance(cfg.hugo_site_dir, Path)
        assert isinstance(cfg.hugo_content_dir, Path)
        assert isinstance(cfg.hugo_publish_dir, Path)

    def test_base_url_read_from_config_toml(self, tmp_path):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        cfg = load(config_path=cfg_path, env_path=env_path)
        # trailing slash from the toml is stripped
        assert cfg.hugo_base_url == "https://dyn.botwerks.net"

    def test_section_derived_from_content_dir(self, tmp_path):
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        cfg = load(config_path=cfg_path, env_path=env_path)
        assert cfg.hugo_section == "repo-newz"


class TestMissingEnvVars:
    @pytest.mark.parametrize("missing", _ALL_VARS)
    def test_missing_var_raises_config_error(self, tmp_path, missing):
        env = {k: v for k, v in _valid_env(tmp_path).items() if k != missing}
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, env)
        with pytest.raises(ConfigError) as exc_info:
            load(config_path=cfg_path, env_path=env_path)
        assert missing in str(exc_info.value)


class TestHugoConfigErrors:
    def test_missing_hugo_config_raises(self, tmp_path):
        env = _valid_env(tmp_path)
        # remove the config.toml the helper created
        (Path(env["HUGO_SITE_DIR"]) / "config.toml").unlink()
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, env)
        with pytest.raises(ConfigError, match="no hugo config"):
            load(config_path=cfg_path, env_path=env_path)

    def test_content_dir_outside_content_root_raises(self, tmp_path):
        env = _valid_env(tmp_path)
        env["HUGO_CONTENT_DIR"] = str(tmp_path / "elsewhere")
        cfg_path = _write_config(tmp_path, _VALID_CONFIG)
        env_path = _write_env(tmp_path, env)
        with pytest.raises(ConfigError, match="not under"):
            load(config_path=cfg_path, env_path=env_path)


class TestConfigYamlErrors:
    def test_missing_file_raises_config_error(self, tmp_path):
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        with pytest.raises(ConfigError, match="not found"):
            load(config_path=tmp_path / "nonexistent.yaml", env_path=env_path)

    def test_malformed_yaml_raises_config_error(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(": bad: yaml: [\n")
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        with pytest.raises(ConfigError, match="parse error"):
            load(config_path=cfg_path, env_path=env_path)

    def test_missing_repos_key_raises_config_error(self, tmp_path):
        data = {**_VALID_CONFIG}
        del data["repos"]
        cfg_path = _write_config(tmp_path, data)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        with pytest.raises(ConfigError, match="repos"):
            load(config_path=cfg_path, env_path=env_path)

    def test_empty_repos_list_raises_config_error(self, tmp_path):
        data = {**_VALID_CONFIG, "repos": []}
        cfg_path = _write_config(tmp_path, data)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        with pytest.raises(ConfigError, match="repos"):
            load(config_path=cfg_path, env_path=env_path)

    def test_bad_repo_entry_raises_config_error_naming_entry(self, tmp_path):
        data = {**_VALID_CONFIG, "repos": ["owner/repo", "notvalid"]}
        cfg_path = _write_config(tmp_path, data)
        env_path = _write_env(tmp_path, _valid_env(tmp_path))
        with pytest.raises(ConfigError, match="notvalid"):
            load(config_path=cfg_path, env_path=env_path)
