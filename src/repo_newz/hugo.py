"""hugo publishing for repo-newz.

writes the rendered markdown into the hugo content tree, builds the site, and
merge-copies the build output into the served target directory.

the publish step is deliberately additive: files hugo generated overwrite their
prior versions, but anything already in the target that hugo did not generate
(e.g. the /stats, /prometheus, /drop-dir trees served alongside the site) is
left untouched. nothing is ever deleted from the target.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from repo_newz.errors import PublishError

log = logging.getLogger("repo_newz")


def write_post(content_dir: Path, slug: str, content: str) -> Path:
    """write the rendered markdown into the hugo content dir; return its path."""
    try:
        content_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise PublishError(f"cannot create content dir {content_dir}: {exc}") from exc

    path = content_dir / f"{slug}.md"
    try:
        path.write_text(content, encoding="utf-8")
    except PermissionError as exc:
        raise PublishError(f"cannot write {path}: {exc}") from exc
    return path


def build_and_publish(site_dir: Path, publish_dir: Path) -> None:
    """build the hugo site, then merge public/ into publish_dir (no deletes)."""
    if not site_dir.is_dir():
        raise PublishError(f"hugo site dir not found: {site_dir}")
    if not publish_dir.is_dir():
        raise PublishError(f"publish dir not found: {publish_dir}")

    try:
        subprocess.run(
            ["hugo"],
            cwd=site_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PublishError("hugo binary not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PublishError(f"hugo build failed: {detail}") from exc

    public = site_dir / "public"
    if not public.is_dir():
        raise PublishError(f"hugo produced no public dir at {public}")

    try:
        shutil.copytree(public, publish_dir, dirs_exist_ok=True)
    except OSError as exc:
        raise PublishError(f"cannot publish to {publish_dir}: {exc}") from exc


def page_url(base_url: str, section: str, slug: str) -> str:
    """build the public URL for a published post (trailing slash, hugo style)."""
    return f"{base_url.rstrip('/')}/{section.strip('/')}/{slug}/"
