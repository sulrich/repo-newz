from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repo_newz.errors import VaultError
from repo_newz.obsidian import write_vault


def test_writes_file(tmp_path):
    year_dir = tmp_path / "2026"
    year_dir.mkdir()
    dest = year_dir / "test.md"
    write_vault(dest, "content")
    assert dest.read_text(encoding="utf-8") == "content"


def test_year_dir_auto_created(tmp_path):
    dest = tmp_path / "2026" / "test.md"
    # grandparent (tmp_path) exists, parent (2026) does not
    write_vault(dest, "hello")
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "hello"


def test_idempotent(tmp_path):
    year_dir = tmp_path / "2026"
    year_dir.mkdir()
    dest = year_dir / "note.md"
    write_vault(dest, "content A")
    write_vault(dest, "content B")
    assert dest.read_text(encoding="utf-8") == "content B"


def test_missing_obsidian_home_raises_vault_error():
    path = Path("/tmp/nonexistent_xyz_abc/2026/test.md")
    with pytest.raises(VaultError, match="obsidian home not found"):
        write_vault(path, "content")


def test_permission_error_on_write_raises_vault_error(tmp_path):
    year_dir = tmp_path / "2026"
    year_dir.mkdir()
    dest = year_dir / "test.md"
    with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
        with pytest.raises(VaultError):
            write_vault(dest, "content")
