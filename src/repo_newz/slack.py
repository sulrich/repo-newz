from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("repo_newz")


def post_summary(prose: dict, date_str: str) -> None:
    """Post the daily summary to Slack via an incoming webhook.

    Reads SLACK_WEBHOOK_URL (required) and SLACK_USER_ID (optional) from env.
    Does nothing if SLACK_WEBHOOK_URL is not set. Logs a warning on failure.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    user_id = os.environ.get("SLACK_USER_ID", "").strip()
    mention = f"<@{user_id}> " if user_id else ""

    overview = prose.get("overview_prose") or "no activity in this window."
    per_repo = prose.get("per_repo_prose", {})

    lines = [f"{mention}*repo-newz {date_str}*", "", overview]
    if per_repo:
        lines.append("")
        for repo, summary in per_repo.items():
            lines.append(f"• *{repo}*: {summary}")

    try:
        resp = httpx.post(
            webhook_url,
            json={"text": "\n".join(lines)},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("posted summary to slack")
    except httpx.HTTPError as exc:
        log.warning("slack post failed: %s", exc)
