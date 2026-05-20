"""Tests for repo_newz.github.fetch_all."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from repo_newz.errors import GitHubAuthError, GitHubRateLimitError
from repo_newz.github import fetch_all

# ---------------------------------------------------------------------------
# Constants used across all tests
# ---------------------------------------------------------------------------

NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
SINCE = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)  # 24 hours before NOW

# Timestamps that are inside and outside the window
IN_WINDOW = "2026-05-19T00:00:00Z"     # after SINCE
BEFORE_WINDOW = "2026-05-17T00:00:00Z"  # before SINCE

BASE = "https://api.github.com"
TOKEN = "test-token"

OWNER = "owner"
REPO = "repo"
FULL = f"{OWNER}/{REPO}"
REPO_INFO = {"default_branch": "main", "full_name": FULL}


# ---------------------------------------------------------------------------
# Fixture helpers — produce GitHub API shaped dicts
# ---------------------------------------------------------------------------


def make_commit(
    sha: str,
    message: str,
    author_login: str | None,
    date_str: str,
) -> dict:
    """Produce a GitHub commits API item."""
    return {
        "sha": sha,
        "html_url": f"https://github.com/{FULL}/commit/{sha}",
        "author": {"login": author_login} if author_login else None,
        "commit": {
            "message": message,
            "author": {
                "name": "Test Author",
                "date": date_str,
            },
        },
    }


def make_pr(
    number: int,
    title: str,
    user_login: str,
    created_at: str,
    merged_at: str | None = None,
    closed_at: str | None = None,
    state: str = "open",
    labels: list[str] | None = None,
) -> dict:
    return {
        "number": number,
        "title": title,
        "state": state,
        "html_url": f"https://github.com/{FULL}/pull/{number}",
        "user": {"login": user_login},
        "created_at": created_at,
        "merged_at": merged_at,
        "closed_at": closed_at,
        "labels": [{"name": lbl} for lbl in (labels or [])],
    }


def make_issue(
    number: int,
    title: str,
    user_login: str,
    created_at: str,
    closed_at: str | None = None,
    state: str = "open",
) -> dict:
    return {
        "number": number,
        "title": title,
        "state": state,
        "html_url": f"https://github.com/{FULL}/issues/{number}",
        "user": {"login": user_login},
        "created_at": created_at,
        "closed_at": closed_at,
    }


def make_release(
    tag: str,
    name: str,
    author_login: str,
    published_at: str,
) -> dict:
    return {
        "tag_name": tag,
        "name": name,
        "html_url": f"https://github.com/{FULL}/releases/tag/{tag}",
        "author": {"login": author_login},
        "published_at": published_at,
    }


# ---------------------------------------------------------------------------
# Helpers for registering mock routes
# ---------------------------------------------------------------------------


def _repo_url(owner: str = OWNER, repo: str = REPO) -> str:
    return f"{BASE}/repos/{owner}/{repo}"


def _commits_url(owner: str = OWNER, repo: str = REPO) -> str:
    return f"{BASE}/repos/{owner}/{repo}/commits"


def _prs_url(owner: str = OWNER, repo: str = REPO) -> str:
    return f"{BASE}/repos/{owner}/{repo}/pulls"


def _issues_url(owner: str = OWNER, repo: str = REPO) -> str:
    return f"{BASE}/repos/{owner}/{repo}/issues"


def _releases_url(owner: str = OWNER, repo: str = REPO) -> str:
    return f"{BASE}/repos/{owner}/{repo}/releases"


def _register_empty_endpoints(mock: respx.MockRouter, owner: str = OWNER, repo: str = REPO) -> None:
    """Register all four data endpoints to return empty lists."""
    mock.get(_commits_url(owner, repo)).mock(return_value=httpx.Response(200, json=[]))
    mock.get(_prs_url(owner, repo)).mock(return_value=httpx.Response(200, json=[]))
    mock.get(_issues_url(owner, repo)).mock(return_value=httpx.Response(200, json=[]))
    mock.get(_releases_url(owner, repo)).mock(return_value=httpx.Response(200, json=[]))


def _register_repo_info(
    mock: respx.MockRouter,
    owner: str = OWNER,
    repo: str = REPO,
    full_name: str | None = None,
) -> None:
    info = {
        "default_branch": "main",
        "full_name": full_name or f"{owner}/{repo}",
    }
    mock.get(_repo_url(owner, repo)).mock(return_value=httpx.Response(200, json=info))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_commit_happy_path():
    """A commit inside the window appears as a commit event with correct fields."""
    commit = make_commit("abcdef1234567890", "feat: add thing", "alice", IN_WINDOW)
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[commit]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    e = events[0]
    assert e["kind"] == "commit"
    assert e["repo"] == FULL
    assert e["actor"] == "alice"
    assert e["title"] == "feat: add thing"
    assert e["sha"] == "abcdef1"
    assert e["number"] is None
    assert e["at"] == IN_WINDOW


def test_commit_out_of_window():
    """A commit before the window is excluded."""
    commit = make_commit("aabbcc1234567890", "old commit", "alice", BEFORE_WINDOW)
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[commit]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert events == []


def test_pr_opened():
    """PR created inside window → pr_opened event."""
    pr = make_pr(1, "My PR", "bob", IN_WINDOW)
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    kinds = [e["kind"] for e in events]
    assert kinds == ["pr_opened"]
    e = events[0]
    assert e["actor"] == "bob"
    assert e["number"] == 1
    assert e["sha"] is None


def test_pr_merged():
    """PR created before window but merged in window → only pr_merged event."""
    pr = make_pr(2, "Old PR merged", "carol", BEFORE_WINDOW, merged_at=IN_WINDOW, state="closed")
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    kinds = [e["kind"] for e in events]
    assert kinds == ["pr_merged"]
    assert events[0]["at"] == IN_WINDOW


def test_pr_both():
    """PR created AND merged in window → two events."""
    pr = make_pr(3, "Fast PR", "dave", IN_WINDOW, merged_at=IN_WINDOW, state="closed")
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    kinds = sorted(e["kind"] for e in events)
    assert kinds == ["pr_merged", "pr_opened"]


def test_issue_opened():
    """Issue created in window → issue_opened event."""
    issue = make_issue(10, "Bug report", "eve", IN_WINDOW)
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[issue]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    assert events[0]["kind"] == "issue_opened"
    assert events[0]["number"] == 10
    assert events[0]["sha"] is None


def test_issue_closed():
    """Issue closed in window but created before → issue_closed event only."""
    issue = make_issue(11, "Old bug", "frank", BEFORE_WINDOW, closed_at=IN_WINDOW, state="closed")
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[issue]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    kinds = [e["kind"] for e in events]
    assert kinds == ["issue_closed"]


def test_issues_filters_prs():
    """Issues endpoint items with a pull_request key are skipped."""
    real_issue = make_issue(20, "Real issue", "grace", IN_WINDOW)
    pr_as_issue = {**make_issue(21, "PR disguised as issue", "heidi", IN_WINDOW), "pull_request": {"url": "..."}}
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(
            return_value=httpx.Response(200, json=[real_issue, pr_as_issue])
        )
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    assert events[0]["number"] == 20


def test_release_in_window():
    """Release published in window → release event."""
    release = make_release("v1.2.0", "Version 1.2.0", "ivan", IN_WINDOW)
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[release]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    e = events[0]
    assert e["kind"] == "release"
    assert e["title"] == "Version 1.2.0"
    assert e["actor"] == "ivan"
    assert e["number"] is None
    assert e["sha"] is None


def test_release_out_of_window():
    """Release published before window → not returned."""
    release = make_release("v0.9.0", "Old release", "judy", BEFORE_WINDOW)
    with respx.mock:
        _register_repo_info(respx.mock)
        _register_empty_endpoints(respx.mock)
        # Override releases to return the old release
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[release]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert events == []


def test_401_raises_github_auth_error():
    """401 from repo info endpoint raises GitHubAuthError."""
    with respx.mock:
        respx.mock.get(_repo_url()).mock(return_value=httpx.Response(401))

        with pytest.raises(GitHubAuthError):
            fetch_all([FULL], 24, TOKEN, _now=NOW)


def test_403_rate_limit_raises_github_rate_limit_error():
    """403 with X-RateLimit-Remaining: 0 raises GitHubRateLimitError with reset_at."""
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234567890"}
    with respx.mock:
        respx.mock.get(_repo_url()).mock(
            return_value=httpx.Response(403, headers=headers)
        )

        with pytest.raises(GitHubRateLimitError) as exc_info:
            fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert exc_info.value.reset_at == 1234567890


def test_403_generic_adds_warning_continues():
    """403 without rate-limit headers adds warning; other repos still processed."""
    owner2, repo2 = "owner2", "repo2"
    full2 = f"{owner2}/{repo2}"
    commit = make_commit("deadbeef12345678", "fix: something", "kim", IN_WINDOW)

    with respx.mock:
        # repo1 returns a plain 403
        respx.mock.get(_repo_url()).mock(return_value=httpx.Response(403))
        # repo2 is fine
        _register_repo_info(respx.mock, owner2, repo2, full_name=full2)
        respx.mock.get(_commits_url(owner2, repo2)).mock(
            return_value=httpx.Response(200, json=[commit])
        )
        respx.mock.get(_prs_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL, full2], 24, TOKEN, _now=NOW)

    assert len(warnings) == 1
    assert FULL in warnings[0]
    assert len(events) == 1
    assert events[0]["repo"] == full2


def test_404_adds_warning_continues():
    """404 on repo1 adds warning; repo2 events are returned."""
    owner2, repo2 = "owner2", "repo2"
    full2 = f"{owner2}/{repo2}"
    commit = make_commit("cafebabe12345678", "chore: update deps", "leo", IN_WINDOW)

    with respx.mock:
        respx.mock.get(_repo_url()).mock(return_value=httpx.Response(404))
        _register_repo_info(respx.mock, owner2, repo2, full_name=full2)
        respx.mock.get(_commits_url(owner2, repo2)).mock(
            return_value=httpx.Response(200, json=[commit])
        )
        respx.mock.get(_prs_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL, full2], 24, TOKEN, _now=NOW)

    assert len(warnings) == 1
    assert "not found" in warnings[0]
    assert len(events) == 1
    assert events[0]["repo"] == full2


def test_5xx_adds_warning_continues():
    """5xx from commits endpoint (after repo info ok) adds warning; repo2 still processed."""
    owner2, repo2 = "owner2", "repo2"
    full2 = f"{owner2}/{repo2}"
    commit = make_commit("11223344aabbccdd", "test: add tests", "mia", IN_WINDOW)

    with respx.mock:
        # repo1: repo info OK, but commits returns 500 three times
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(500))

        # repo2 is fully fine
        _register_repo_info(respx.mock, owner2, repo2, full_name=full2)
        respx.mock.get(_commits_url(owner2, repo2)).mock(
            return_value=httpx.Response(200, json=[commit])
        )
        respx.mock.get(_prs_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL, full2], 24, TOKEN, _now=NOW)

    assert len(warnings) == 1
    assert "server error" in warnings[0]
    assert len(events) == 1
    assert events[0]["repo"] == full2


def test_connection_error_adds_warning():
    """ConnectError for repo1 adds warning; repo2 is still processed."""
    owner2, repo2 = "owner2", "repo2"
    full2 = f"{owner2}/{repo2}"
    commit = make_commit("99887766aabbccdd", "docs: update readme", "ned", IN_WINDOW)

    with respx.mock:
        respx.mock.get(_repo_url()).mock(side_effect=httpx.ConnectError("refused"))
        _register_repo_info(respx.mock, owner2, repo2, full_name=full2)
        respx.mock.get(_commits_url(owner2, repo2)).mock(
            return_value=httpx.Response(200, json=[commit])
        )
        respx.mock.get(_prs_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url(owner2, repo2)).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL, full2], 24, TOKEN, _now=NOW)

    assert len(warnings) == 1
    assert "connection failed" in warnings[0]
    assert len(events) == 1


def test_empty_commits_response():
    """Empty commits list produces no events."""
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert events == []


def test_actor_fallback_no_author_field():
    """Commit with author=None falls back to commit.commit.author.name."""
    commit = make_commit("fedcba9876543210", "fix: null author", None, IN_WINDOW)
    # make_commit already sets author to None when author_login is None
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[commit]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    # Falls back to commit.commit.author.name which make_commit sets to "Test Author"
    assert events[0]["actor"] == "Test Author"


def test_pr_labels_included():
    """Labels from the PR are included in the event dict."""
    pr = make_pr(5, "Labelled PR", "oscar", IN_WINDOW, labels=["bug", "needs-review"])
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    assert events[0]["labels"] == ["bug", "needs-review"]


def test_pr_closed_in_window():
    """PR closed (not github-merged) in window → pr_closed event."""
    pr = make_pr(6, "Externally merged PR", "pat", BEFORE_WINDOW, closed_at=IN_WINDOW, state="closed")
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    kinds = [e["kind"] for e in events]
    assert kinds == ["pr_closed"]
    assert events[0]["at"] == IN_WINDOW


def test_pr_closed_with_merged_label_emits_pr_merged():
    """PR closed with a 'merged' label emits pr_merged (facebook-style tooling)."""
    pr = make_pr(
        7, "FB-style merged PR", "quinn", BEFORE_WINDOW,
        closed_at=IN_WINDOW, state="closed", labels=["merged", "shipit"],
    )
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert len(events) == 1
    e = events[0]
    assert e["kind"] == "pr_merged"
    assert "merged" in e["labels"]


def test_pr_closed_before_window_excluded():
    """PR closed before the window does not produce a pr_closed event."""
    pr = make_pr(8, "Old closed PR", "riley", BEFORE_WINDOW, closed_at=BEFORE_WINDOW, state="closed")
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    assert events == []


def test_pr_github_merged_does_not_emit_pr_closed():
    """PR merged via github (merged_at set) does not also emit pr_closed."""
    pr = make_pr(
        9, "Normal merge", "sam", BEFORE_WINDOW,
        merged_at=IN_WINDOW, closed_at=IN_WINDOW, state="closed",
    )
    with respx.mock:
        _register_repo_info(respx.mock)
        respx.mock.get(_commits_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_prs_url()).mock(return_value=httpx.Response(200, json=[pr]))
        respx.mock.get(_issues_url()).mock(return_value=httpx.Response(200, json=[]))
        respx.mock.get(_releases_url()).mock(return_value=httpx.Response(200, json=[]))

        events, warnings = fetch_all([FULL], 24, TOKEN, _now=NOW)

    assert warnings == []
    kinds = [e["kind"] for e in events]
    assert kinds == ["pr_merged"]
