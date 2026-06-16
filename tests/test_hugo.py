from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from repo_newz.errors import PublishError
from repo_newz.hugo import build_and_publish, page_url, write_post


class TestWritePost:
    def test_writes_file(self, tmp_path):
        content_dir = tmp_path / "content" / "repo-newz"
        path = write_post(content_dir, "repo-activity-20260615", "body")
        assert path == content_dir / "repo-activity-20260615.md"
        assert path.read_text(encoding="utf-8") == "body"

    def test_creates_content_dir(self, tmp_path):
        content_dir = tmp_path / "deep" / "content" / "repo-newz"
        path = write_post(content_dir, "post", "hello")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "hello"

    def test_overwrites_existing(self, tmp_path):
        content_dir = tmp_path / "content"
        write_post(content_dir, "post", "first")
        path = write_post(content_dir, "post", "second")
        assert path.read_text(encoding="utf-8") == "second"

    def test_permission_error_raises_publish_error(self, tmp_path):
        content_dir = tmp_path / "content"
        with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
            with pytest.raises(PublishError):
                write_post(content_dir, "post", "x")


class TestBuildAndPublish:
    def _site_and_target(self, tmp_path):
        site = tmp_path / "site"
        (site / "public").mkdir(parents=True)
        target = tmp_path / "www"
        target.mkdir()
        return site, target

    def test_builds_then_merges_public_into_target(self, tmp_path):
        site, target = self._site_and_target(tmp_path)

        # pre-existing non-hugo content in the target must survive
        preserved = target / "stats" / "index.html"
        preserved.parent.mkdir()
        preserved.write_text("keep me")

        def fake_run(*args, **kwargs):
            # simulate hugo emitting build output into public/
            (site / "public" / "index.html").write_text("generated")
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch("repo_newz.hugo.subprocess.run", side_effect=fake_run):
            build_and_publish(site, target)

        assert (target / "index.html").read_text() == "generated"
        # untouched: the copy never deletes from the target
        assert preserved.read_text() == "keep me"

    def test_hugo_build_failure_raises_publish_error(self, tmp_path):
        site, target = self._site_and_target(tmp_path)
        err = subprocess.CalledProcessError(1, ["hugo"], output="", stderr="boom")
        with patch("repo_newz.hugo.subprocess.run", side_effect=err):
            with pytest.raises(PublishError, match="hugo build failed"):
                build_and_publish(site, target)

    def test_missing_hugo_binary_raises_publish_error(self, tmp_path):
        site, target = self._site_and_target(tmp_path)
        with patch("repo_newz.hugo.subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(PublishError, match="hugo binary not found"):
                build_and_publish(site, target)

    def test_missing_publish_dir_raises_publish_error(self, tmp_path):
        site = tmp_path / "site"
        (site / "public").mkdir(parents=True)
        with pytest.raises(PublishError, match="publish dir not found"):
            build_and_publish(site, tmp_path / "nope")


class TestPageUrl:
    def test_builds_trailing_slash_url(self):
        url = page_url("https://dyn.botwerks.net", "repo-newz", "repo-activity-20260615")
        assert url == "https://dyn.botwerks.net/repo-newz/repo-activity-20260615/"

    def test_normalizes_extra_slashes(self):
        url = page_url("https://dyn.botwerks.net/", "/repo-newz/", "post")
        assert url == "https://dyn.botwerks.net/repo-newz/post/"
