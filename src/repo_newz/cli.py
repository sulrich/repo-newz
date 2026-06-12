from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from repo_newz.config import load as load_config
from repo_newz.errors import (
    ConfigError,
    GitHubAuthError,
    GitHubRateLimitError,
    VaultError,
)

log = logging.getLogger("repo_newz")

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_GITHUB_AUTH = 3
EXIT_GITHUB_RATE = 4
EXIT_VAULT = 5
EXIT_UNEXPECTED = 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repo-newz",
        description="fetch 24h github activity and write a summary to obsidian.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be done; no API calls to anthropic, no vault writes.",
    )
    p.add_argument(
        "--since",
        type=int,
        metavar="HOURS",
        default=None,
        help="override window_hours from config.",
    )
    p.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        default=None,
        help="path to config.yaml (default: ~/.config/repo-newz/config.yaml).",
    )
    p.add_argument(
        "--env",
        type=Path,
        metavar="PATH",
        default=None,
        help="path to .env file (default: .env next to config.yaml).",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true", help="enable debug logging."
    )
    return p


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=level,
        stream=sys.stdout,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        cfg = load_config(config_path=args.config, env_path=args.env)
    except ConfigError as exc:
        log.error("configuration error: %s", exc)
        return EXIT_CONFIG

    if args.since is not None:
        cfg.window_hours = args.since

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    year_str = now.strftime("%Y")
    output_path = cfg.obsidian_home / cfg.vault_subpath.format(
        year=year_str, date=date_str
    )

    if args.dry_run:
        print("dry-run mode")
        print(f"  repos      : {cfg.repos}")
        print(f"  window     : {cfg.window_hours}h")
        print(f"  model      : {cfg.model}")
        print(f"  output     : {output_path}")
        return EXIT_OK

    try:
        return _run(cfg, output_path, now)
    except GitHubAuthError as exc:
        log.error("github auth failed: %s", exc)
        return EXIT_GITHUB_AUTH
    except GitHubRateLimitError as exc:
        log.error("github rate limit: %s", exc)
        return EXIT_GITHUB_RATE
    except VaultError as exc:
        log.error("vault error: %s", exc)
        return EXIT_VAULT
    except Exception as exc:
        log.exception("unexpected error: %s", exc)
        return EXIT_UNEXPECTED


def _run(cfg, output_path: Path, now: datetime) -> int:
    from repo_newz.github import fetch_all
    from repo_newz.summarize import fill_prose_slots
    from repo_newz.render import render
    from repo_newz.obsidian import write_vault

    log.info("fetching activity for %d repos (window: %dh)", len(cfg.repos), cfg.window_hours)
    events, warnings = fetch_all(cfg.repos, cfg.window_hours, cfg.github_token)

    prose = fill_prose_slots(events, cfg) if events else {}

    content = render(events, prose, warnings, cfg, now)
    write_vault(output_path, content)
    log.info("wrote %s", output_path)

    from repo_newz.slack import post_summary
    post_summary(prose, now.strftime("%Y-%m-%d"))

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
