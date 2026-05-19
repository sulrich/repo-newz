from __future__ import annotations

from pathlib import Path

from repo_newz.errors import VaultError


def write_vault(path: Path, content: str) -> None:
    obsidian_home = path.parent.parent
    if not obsidian_home.exists():
        raise VaultError(f"obsidian home not found: {obsidian_home}")

    try:
        path.parent.mkdir(parents=False, exist_ok=True)
    except PermissionError as exc:
        raise VaultError(f"cannot create directory {path.parent}: {exc}") from exc

    try:
        path.write_text(content, encoding="utf-8")
    except PermissionError as exc:
        raise VaultError(f"cannot write {path}: {exc}") from exc
