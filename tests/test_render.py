from __future__ import annotations

import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from repo_newz.config import Config
from repo_newz.render import render

_NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)

_EVENTS = [
    {
        "repo": "owner/repo",
        "kind": "commit",
        "actor": "alice",
        "actor_url": "https://github.com/alice",
        "title": "fix bug",
        "url": "https://github.com/owner/repo/commit/abc1234",
        "at": "2026-05-19T06:00:00Z",
        "number": None,
        "sha": "abc1234",
    },
    {
        "repo": "owner/repo",
        "kind": "pr_merged",
        "actor": "bob",
        "actor_url": "https://github.com/bob",
        "title": "add feature",
        "url": "https://github.com/owner/repo/pull/42",
        "at": "2026-05-19T07:00:00Z",
        "number": 42,
        "sha": None,
        "labels": [],
    },
    {
        "repo": "owner/repo",
        "kind": "pr_opened",
        "actor": "carol",
        "actor_url": "https://github.com/carol",
        "title": "draft work",
        "url": "https://github.com/owner/repo/pull/43",
        "at": "2026-05-19T08:00:00Z",
        "number": 43,
        "sha": None,
        "labels": ["needs-review"],
    },
    {
        "repo": "owner/repo",
        "kind": "pr_closed",
        "actor": "dave",
        "actor_url": "https://github.com/dave",
        "title": "declined pr",
        "url": "https://github.com/owner/repo/pull/44",
        "at": "2026-05-19T08:30:00Z",
        "number": 44,
        "sha": None,
        "labels": ["wontfix"],
    },
    {
        "repo": "owner/repo",
        "kind": "issue_opened",
        "actor": "alice",
        "actor_url": "https://github.com/alice",
        "title": "bug report",
        "url": "https://github.com/owner/repo/issues/10",
        "at": "2026-05-19T09:00:00Z",
        "number": 10,
        "sha": None,
    },
    {
        "repo": "owner/repo",
        "kind": "issue_closed",
        "actor": "bob",
        "actor_url": "https://github.com/bob",
        "title": "old issue",
        "url": "https://github.com/owner/repo/issues/5",
        "at": "2026-05-19T10:00:00Z",
        "number": 5,
        "sha": None,
    },
    {
        "repo": "owner/repo",
        "kind": "release",
        "actor": "alice",
        "actor_url": "https://github.com/alice",
        "title": "v1.2.0",
        "url": "https://github.com/owner/repo/releases/tag/v1.2.0",
        "at": "2026-05-19T11:00:00Z",
        "number": None,
        "sha": None,
    },
]


@pytest.fixture
def cfg():
    return Config(
        repos=["owner/repo", "other/proj"],
        model="claude-sonnet-4-6",
        window_hours=24,
        anthropic_api_key="sk-ant-test",
        github_token="ghp_test",
        hugo_site_dir=Path("/site"),
        hugo_content_dir=Path("/site/content/repo-newz"),
        hugo_publish_dir=Path("/www"),
        hugo_base_url="https://dyn.botwerks.net",
        hugo_section="repo-newz",
    )


@pytest.fixture
def output(cfg):
    return render(_EVENTS, {}, [], cfg, _NOW)


def test_renders_front_matter(output):
    assert output.startswith("+++")
    assert 'title = "repo activity: 20260519"' in output
    assert "date =" in output
    assert "tags =" in output


def test_front_matter_parses_as_toml(output):
    # extract the front matter block between the first +++ and second +++
    parts = output.split("+++", 2)
    fm = tomllib.loads(parts[1])
    assert fm["draft"] is False
    assert "repo-newz" in fm["tags"]
    assert fm["title"] == "repo activity: 20260519"


def test_repo_section_headers_present(output):
    assert "### [owner/repo](https://github.com/owner/repo)" in output
    assert "### [other/proj](https://github.com/other/proj)" in output


def test_commit_line_format(output):
    assert "`abc1234` fix bug — alice" in output


def test_pr_merged_state_label(output):
    assert "[#42]" in output
    assert "merged" in output


def test_pr_opened_state_label(output):
    assert "[#43]" in output
    assert "opened" in output


def test_pr_closed_state_label(output):
    assert "[#44]" in output
    assert "closed" in output


def test_pr_labels_rendered(output):
    assert "needs-review" in output
    assert "wontfix" in output


def test_issue_closed_state_label(output):
    assert "[#5]" in output
    assert "closed" in output


def test_issue_opened_state_label(output):
    assert "[#10]" in output
    assert "opened" in output


def test_per_repo_contributor_table_has_alice(output):
    # alice has 1 commit, 1 issue_opened, 1 release in owner/repo
    lines = output.splitlines()
    alice_lines = [l for l in lines if "alice" in l and "|" in l]
    assert len(alice_lines) >= 1
    # row format: | [alice](...) | commits | prs | issues | releases |
    cells = [c.strip() for c in alice_lines[0].split("|") if c.strip()]
    assert cells[1] == "1"  # commits
    assert cells[2] == "0"  # prs
    assert cells[3] == "1"  # issues
    assert cells[4] == "1"  # releases


def test_contributor_link_uses_actor_url(output):
    assert "| [alice](https://github.com/alice) |" in output


def test_contributor_without_actor_url_is_not_linked(cfg):
    """A git display name (no linked account) renders as plain text, not a link.

    Regression: the row used to be built as [<actor>](https://github.com/<actor>),
    producing broken URLs with spaces for unlinked commit authors.
    """
    events = [
        {
            "repo": "owner/repo",
            "kind": "commit",
            "actor": "Ashutosh Grewal",
            "actor_url": None,
            "title": "fix bug",
            "url": "https://github.com/owner/repo/commit/abc1234",
            "at": "2026-05-19T06:00:00Z",
            "number": None,
            "sha": "abc1234",
        },
    ]
    out = render(events, {}, [], cfg, _NOW)
    assert "| Ashutosh Grewal | 1 | 0 | 0 | 0 |" in out
    assert "https://github.com/Ashutosh Grewal" not in out
    assert "[Ashutosh Grewal](" not in out


def test_contributor_url_uses_api_value_for_bots(cfg):
    """The row links wherever the API said, not github.com/<login>."""
    events = [
        {
            "repo": "owner/repo",
            "kind": "pr_opened",
            "actor": "dependabot[bot]",
            "actor_url": "https://github.com/apps/dependabot",
            "title": "bump dep",
            "url": "https://github.com/owner/repo/pull/50",
            "at": "2026-05-19T06:00:00Z",
            "number": 50,
            "sha": None,
            "labels": [],
        },
    ]
    out = render(events, {}, [], cfg, _NOW)
    assert "[dependabot[bot]](https://github.com/apps/dependabot)" in out


def test_contributor_url_recovered_from_later_event(cfg):
    """If one event lacks a profile but another for the same actor has one, link it."""
    events = [
        {
            "repo": "owner/repo",
            "kind": "commit",
            "actor": "alice",
            "actor_url": None,
            "title": "fix bug",
            "url": "https://github.com/owner/repo/commit/abc1234",
            "at": "2026-05-19T06:00:00Z",
            "number": None,
            "sha": "abc1234",
        },
        {
            "repo": "owner/repo",
            "kind": "pr_opened",
            "actor": "alice",
            "actor_url": "https://github.com/alice",
            "title": "add feature",
            "url": "https://github.com/owner/repo/pull/51",
            "at": "2026-05-19T07:00:00Z",
            "number": 51,
            "sha": None,
            "labels": [],
        },
    ]
    out = render(events, {}, [], cfg, _NOW)
    assert "| [alice](https://github.com/alice) | 1 | 1 | 0 | 0 |" in out


def test_no_global_contributor_roundup_section(output):
    assert "## contributor roundup" not in output


def test_contributor_table_inside_repo_section(output):
    # the contributors table must appear after the repo heading, not before it
    owner_repo_pos = output.index("### [owner/repo](https://github.com/owner/repo)")
    assert "alice" in output[owner_repo_pos:]


def test_empty_day(cfg):
    out = render([], {}, [], cfg, _NOW)
    assert "no activity" in out
    # contributor table has no data rows (only header rows)
    lines = out.splitlines()
    table_data_rows = [
        l for l in lines
        if "|" in l and "login" not in l and "---" not in l and l.strip().startswith("|")
    ]
    assert len(table_data_rows) == 0
    assert "### [other/proj](https://github.com/other/proj)" in out


def test_prose_injected(cfg):
    out = render(_EVENTS, {"overview_prose": "test summary"}, [], cfg, _NOW)
    assert "test summary" in out


def test_warnings_section(cfg):
    out = render(_EVENTS, {}, ["repo/bad: not found (404)"], cfg, _NOW)
    assert "## warnings" in out
    assert "repo/bad: not found (404)" in out


def test_no_warnings_section_when_empty(output):
    assert "## warnings" not in output
