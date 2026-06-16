# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`repo-newz` fetches the last 24h of GitHub activity across a configured repo
list, writes a daily markdown summary into a Hugo site, rebuilds and publishes
the site, and posts the summary to Slack with a link to the rendered page.
Deterministic code does all fact-gathering; an Anthropic model writes only the
prose narrative. The hard rule baked into the system prompt is that the model
may not invent any repo, user, number, or detail not present in the supplied
event JSON.

## Commands

```text
uv sync                  # install deps (incl. dev group)
./repo-newz --dry-run    # resolve config + output path, no API calls or writes
./repo-newz              # live run
./repo-newz --since 48   # override window_hours
uv run pytest -v         # run the full test suite
uv run pytest tests/test_github.py -v          # single test file
uv run pytest tests/test_github.py::test_name  # single test
bash scripts/failure-drill.sh                  # manually exercise error paths
```

The `./repo-newz` launcher just execs `.venv/bin/repo-newz`; the real entry
point is `repo_newz.cli:main`.

## Pipeline (cli.py `_run`)

The flow is a fixed sequence, each stage in its own module:

1. **config.py** — `load()` reads env vars (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`,
   `HUGO_SITE_DIR`, `HUGO_CONTENT_DIR`, `HUGO_PUBLISH_DIR`) and `config.yaml`,
   returning a `Config` dataclass. It also derives `hugo_base_url` (parsed from
   the site's `config.toml`/`hugo.toml` via `tomllib`) and `hugo_section` (the
   content dir's path relative to `<site>/content`).
2. **github.py** — `fetch_all()` hits the GitHub REST API per repo and returns
   `(events, warnings)`: a flat list of normalized event dicts plus per-repo
   failure strings.
3. **summarize.py** — `fill_prose_slots()` sends the events to the model and
   returns prose. Skipped entirely when there are no events.
4. **render.py** — `render()` groups events by repo, computes contributor
   counts, and fills the Jinja template (Hugo TOML front matter + body).
5. **hugo.py** — `write_post()` writes the markdown into the content dir;
   `build_and_publish()` runs `hugo` then merge-copies `public/` into the
   publish target; `page_url()` builds the page link.
6. **slack.py** — `post_summary()` posts to Slack if configured, appending the
   page URL when one is passed.

## Key design decisions to preserve

- **Two-tier error handling.** Auth (401) and rate-limit (exhausted 403) errors
  are *fatal* and propagate up to abort the whole run with a distinct exit code.
  All other per-repo failures (404, 5xx after retries, timeouts, generic 403)
  become `GitHubRepoError` warnings — collected, surfaced in a `## warnings`
  section of the output, and the run continues. Exit codes are defined in
  `cli.py` and documented in the README's exit-code table; keep them in sync.

- **The model is fail-soft and isolated.** Every Anthropic failure in
  `summarize.py` is caught and returns `{}` (empty prose) rather than aborting —
  the run still produces a fact-only file. The model response is expected to be
  JSON with exactly `overview_prose` and `per_repo_prose`; `_parse_response`
  strips markdown code fences and defensively coerces types.

- **Publishing is additive, never destructive.** `build_and_publish` uses
  `shutil.copytree(public, publish_dir, dirs_exist_ok=True)` — it overwrites
  files Hugo regenerated but leaves everything else in the target intact (the
  served site shares its root with non-Hugo trees like `/stats`, `/prometheus`,
  `/drop-dir`). Never switch this to a delete-sync (`rsync --delete`, etc.).

- **The Hugo site's home must be `content/_index.md`.** A root `content/index.md`
  is a leaf bundle and silently stops child sections (`repo-newz/`) from
  rendering — the post files build to nothing. This bit us once; if published
  pages go missing, check this first.

- **Empty days still write a file.** Zero activity across all repos produces a
  stub file (prose stays `{}`, render uses fallback text) for consistent site
  presence. Don't short-circuit this.

- **Event normalization is the contract.** Every event dict carries the same
  shape (`repo`, `kind`, `actor`, `title`, `url`, `at`, `number`, `sha`, and PRs
  additionally `labels`). `kind` is one of `commit`, `pr_opened`, `pr_merged`,
  `pr_closed`, `issue_opened`, `issue_closed`, `release`. render.py and the
  template depend on this shape — extend it carefully.

- **PR "merged" detection has a special case.** A PR closed without a GitHub
  merge but carrying a `merged` label is treated as `pr_merged` (handles
  Facebook-style external tooling). See the comment in `github.py:_events_for_repo`.

- **GitHub pagination is capped at one page** (`per_page=100`, no Link-header
  following). Noted as a known limitation in `github.py`'s module docstring.

## Config and secrets

- `config.yaml` lives at `~/.config/repo-newz/config.yaml` by default
  (`--config` overrides). Keys: `window_hours`, `model`, `repos` (validated
  against `owner/repo` regex; empty/malformed → `ConfigError`).
- Secrets/paths come from `.env` (default: repo root, override with `--env`):
  `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, and the three `HUGO_*` paths. Slack is
  opt-in via `SLACK_WEBHOOK_URL` (+ optional `SLACK_USER_ID` for a mention);
  absent webhook = no-op.
- Output filename is always `repo-activity-YYYYMMDD.md`, written flat into
  `HUGO_CONTENT_DIR`. The published URL is
  `<baseURL>/<hugo_section>/repo-activity-YYYYMMDD/`, where `baseURL` comes from
  the site's `config.toml` and `hugo_section` is derived from the content dir.

## Testing

Tests use `pytest` with `respx` to mock the GitHub HTTP layer and
`pytest-mock` for the Anthropic client. `fetch_all()` accepts a `_now`
parameter to make the time window deterministic in tests.
