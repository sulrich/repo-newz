"""github REST API client for repo-newz.

fetches commits, PRs, issues, and releases for a list of repos within a time
window. auth errors and rate-limit errors propagate to the caller; per-repo
errors are collected as warnings and execution continues.

NOTE: pagination is capped at one page (per_page=100). for repos with very high
activity a future pass could follow Link rel="next" headers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from repo_newz.errors import (
    GitHubAuthError,
    GitHubRateLimitError,
    GitHubRepoError,
)

_BASE_URL = "https://api.github.com"
_TIMEOUT = 10  # seconds
_MAX_RETRIES = 2  # retry 5xx up to this many extra times (3 total attempts overall)


def _make_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _check_response(response: httpx.Response, repo: str) -> None:
    """raise the appropriate error for non-2xx responses."""
    status = response.status_code
    if status == 401:
        raise GitHubAuthError("github returned 401 - check GITHUB_TOKEN")
    if status == 403:
        remaining = response.headers.get("X-RateLimit-Remaining", "1")
        if remaining == "0":
            reset_at = int(response.headers.get("X-RateLimit-Reset", 0))
            raise GitHubRateLimitError(reset_at=reset_at)
        raise GitHubRepoError(repo, "403 forbidden (SSO or permission)")
    if status == 404:
        raise GitHubRepoError(repo, "not found (404)")


def _get(
    client: httpx.Client,
    url: str,
    repo: str,
    params: Optional[dict] = None,
) -> httpx.Response:
    """GET with retry on 5xx. 401/403/404 raise immediately, no retry."""
    attempts = 0
    last_exc: Optional[Exception] = None

    while attempts <= _MAX_RETRIES:
        try:
            response = client.get(url, params=params)
        except httpx.TimeoutException:
            raise GitHubRepoError(repo, "request timed out")
        except httpx.ConnectError:
            raise GitHubRepoError(repo, "connection failed")

        if response.status_code in (401, 403, 404):
            _check_response(response, repo)

        if response.status_code >= 500:
            attempts += 1
            last_exc = GitHubRepoError(repo, f"server error {response.status_code}")
            continue

        # Success path
        response.raise_for_status()
        return response

    # exhausted retries on 5xx
    assert last_exc is not None
    raise last_exc


def _fetch_repo_info(client: httpx.Client, owner: str, repo_name: str) -> dict:
    """return the /repos/{o}/{r} JSON payload."""
    url = f"{_BASE_URL}/repos/{owner}/{repo_name}"
    repo = f"{owner}/{repo_name}"
    response = _get(client, url, repo)
    return response.json()


def _fetch_commits(
    client: httpx.Client,
    owner: str,
    repo_name: str,
    default_branch: str,
    since: datetime,
) -> list[dict]:
    url = f"{_BASE_URL}/repos/{owner}/{repo_name}/commits"
    repo = f"{owner}/{repo_name}"
    params = {
        "since": since.isoformat(),
        "sha": default_branch,
        "per_page": 100,
    }
    response = _get(client, url, repo, params=params)
    return response.json()


def _fetch_prs(
    client: httpx.Client,
    owner: str,
    repo_name: str,
) -> list[dict]:
    url = f"{_BASE_URL}/repos/{owner}/{repo_name}/pulls"
    repo = f"{owner}/{repo_name}"
    params = {
        "state": "all",
        "sort": "updated",
        "direction": "desc",
        "per_page": 100,
    }
    response = _get(client, url, repo, params=params)
    return response.json()


def _fetch_issues(
    client: httpx.Client,
    owner: str,
    repo_name: str,
    since: datetime,
) -> list[dict]:
    url = f"{_BASE_URL}/repos/{owner}/{repo_name}/issues"
    repo = f"{owner}/{repo_name}"
    params = {
        "state": "all",
        "since": since.isoformat(),
        "per_page": 100,
    }
    response = _get(client, url, repo, params=params)
    return response.json()


def _fetch_releases(
    client: httpx.Client,
    owner: str,
    repo_name: str,
) -> list[dict]:
    url = f"{_BASE_URL}/repos/{owner}/{repo_name}/releases"
    repo = f"{owner}/{repo_name}"
    params = {"per_page": 100}
    response = _get(client, url, repo, params=params)
    return response.json()


def _parse_dt(dt_str: str) -> datetime:
    """parse an ISO8601 datetime string from the github API."""
    # github returns strings like "2026-05-18T12:00:00Z"
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def _events_for_repo(
    client: httpx.Client,
    repo: str,
    since: datetime,
) -> list[dict]:
    """fetch and normalize all events for a single repo."""
    owner, repo_name = repo.split("/", 1)
    events: list[dict] = []

    # repo info to resolve default_branch
    info = _fetch_repo_info(client, owner, repo_name)
    default_branch = info.get("default_branch", "main")
    full_name = info.get("full_name", repo)

    # --- commits ---
    commits = _fetch_commits(client, owner, repo_name, default_branch, since)
    for commit in commits:
        date_str = commit["commit"]["author"]["date"]
        at = _parse_dt(date_str)
        if at < since:
            continue
        author_obj = commit.get("author")
        if author_obj and author_obj.get("login"):
            actor = author_obj["login"]
        else:
            actor = commit["commit"]["author"]["name"]
        title = commit["commit"]["message"].splitlines()[0]
        events.append(
            {
                "repo": full_name,
                "kind": "commit",
                "actor": actor,
                "title": title,
                "url": commit["html_url"],
                "at": date_str,
                "number": None,
                "sha": commit["sha"][:7],
            }
        )

    # --- PRs ---
    prs = _fetch_prs(client, owner, repo_name)
    for pr in prs:
        created_at = _parse_dt(pr["created_at"])
        merged_at_str = pr.get("merged_at")
        merged_at = _parse_dt(merged_at_str) if merged_at_str else None
        closed_at_str = pr.get("closed_at")
        closed_at = _parse_dt(closed_at_str) if closed_at_str else None
        labels = [lbl["name"] for lbl in pr.get("labels", [])]

        actor = pr["user"]["login"]
        base_event = {
            "repo": full_name,
            "actor": actor,
            "title": pr["title"],
            "url": pr["html_url"],
            "number": pr["number"],
            "sha": None,
            "labels": labels,
        }

        if created_at >= since:
            events.append({**base_event, "kind": "pr_opened", "at": pr["created_at"]})
        if merged_at is not None and merged_at >= since:
            events.append({**base_event, "kind": "pr_merged", "at": merged_at_str})
        # closed without a github merge (e.g. facebook-style tooling that closes
        # PRs externally and adds a "merged" label instead of using github merge)
        if merged_at is None and closed_at is not None and closed_at >= since:
            kind = "pr_merged" if "merged" in labels else "pr_closed"
            events.append({**base_event, "kind": kind, "at": closed_at_str})

    # --- issues ---
    issues = _fetch_issues(client, owner, repo_name, since)
    for issue in issues:
        # github issues endpoint returns PRs too; skip them
        if "pull_request" in issue:
            continue
        created_at = _parse_dt(issue["created_at"])
        closed_at_str = issue.get("closed_at")
        closed_at = _parse_dt(closed_at_str) if closed_at_str else None

        actor = issue["user"]["login"]
        base_event = {
            "repo": full_name,
            "actor": actor,
            "title": issue["title"],
            "url": issue["html_url"],
            "number": issue["number"],
            "sha": None,
        }

        if created_at >= since:
            events.append(
                {**base_event, "kind": "issue_opened", "at": issue["created_at"]}
            )
        if closed_at is not None and closed_at >= since:
            events.append({**base_event, "kind": "issue_closed", "at": closed_at_str})

    # --- releases ---
    releases = _fetch_releases(client, owner, repo_name)
    for release in releases:
        pub_str = release.get("published_at")
        if not pub_str:
            continue
        published_at = _parse_dt(pub_str)
        if published_at < since:
            continue
        events.append(
            {
                "repo": full_name,
                "kind": "release",
                "actor": release["author"]["login"],
                "title": release.get("name") or release["tag_name"],
                "url": release["html_url"],
                "at": pub_str,
                "number": None,
                "sha": None,
            }
        )

    return events


def fetch_all(
    repos: list[str],
    window_hours: int,
    token: str,
    _now: Optional[datetime] = None,
) -> tuple[list[dict], list[str]]:
    """fetch events for all repos within the given time window.

    returns (events, warnings). events is a flat list of normalized event dicts;
    warnings is a list of human-readable per-repo failure strings. auth and
    rate-limit errors are raised immediately and abort the run.

    _now overrides the current UTC time - useful for testing.
    """
    if _now is None:
        _now = datetime.now(timezone.utc)
    since = _now - timedelta(hours=window_hours)

    events: list[dict] = []
    warnings: list[str] = []

    headers = _make_headers(token)
    with httpx.Client(headers=headers, timeout=_TIMEOUT) as client:
        for repo in repos:
            try:
                repo_events = _events_for_repo(client, repo, since)
                events.extend(repo_events)
            except (GitHubAuthError, GitHubRateLimitError):
                # fatal - propagate immediately
                raise
            except GitHubRepoError as exc:
                warnings.append(str(exc))

    return events, warnings
