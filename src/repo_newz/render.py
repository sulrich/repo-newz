from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"
_TEMPLATE_NAME = "repo-activity.md.j2"

_PR_KINDS = {"pr_opened", "pr_merged", "pr_closed"}
_ISSUE_KINDS = {"issue_opened", "issue_closed"}


def render(
    events: list[dict],
    prose: dict,
    warnings: list[str],
    cfg,  # Config
    now: datetime,
) -> str:
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_repo[event["repo"]].append(event)

    repos = []
    for full_name in cfg.repos:
        repo_events = by_repo.get(full_name, [])
        commits = [e for e in repo_events if e["kind"] == "commit"]

        prs = []
        for e in repo_events:
            if e["kind"] in _PR_KINDS:
                entry = dict(e)
                if e["kind"] == "pr_merged":
                    entry["state_label"] = "merged"
                elif e["kind"] == "pr_opened":
                    entry["state_label"] = "opened"
                else:  # pr_closed
                    entry["state_label"] = "closed"
                prs.append(entry)

        issues = []
        for e in repo_events:
            if e["kind"] in _ISSUE_KINDS:
                entry = dict(e)
                entry["state_label"] = "closed" if e["kind"] == "issue_closed" else "opened"
                issues.append(entry)

        releases = [e for e in repo_events if e["kind"] == "release"]

        # per-repo contributor counts
        contrib_counts: dict[str, dict] = defaultdict(
            lambda: {"commits": 0, "prs": 0, "issues": 0, "releases": 0}
        )
        for e in repo_events:
            actor = e["actor"]
            kind = e["kind"]
            if kind == "commit":
                contrib_counts[actor]["commits"] += 1
            elif kind in _PR_KINDS:
                contrib_counts[actor]["prs"] += 1
            elif kind in _ISSUE_KINDS:
                contrib_counts[actor]["issues"] += 1
            elif kind == "release":
                contrib_counts[actor]["releases"] += 1

        contributors = []
        for login, counts in contrib_counts.items():
            total = counts["commits"] + counts["prs"] + counts["issues"] + counts["releases"]
            contributors.append({"login": login, **counts, "_total": total})
        contributors.sort(key=lambda c: c["_total"], reverse=True)
        for c in contributors:
            del c["_total"]

        repo_prose = prose.get("per_repo_prose", {}).get(full_name, "")
        repos.append(
            {
                "full_name": full_name,
                "commits": commits,
                "prs": prs,
                "issues": issues,
                "releases": releases,
                "contributors": contributors,
                "prose": repo_prose,
            }
        )

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template(_TEMPLATE_NAME)

    return template.render(
        date=now.strftime("%Y%m%d"),
        date_pretty=now.strftime("%B %d, %Y"),
        overview_prose=prose.get(
            "overview_prose", "no activity across the watched repos in the last 24h."
        ),
        repos=repos,
        warnings=warnings,
    )
