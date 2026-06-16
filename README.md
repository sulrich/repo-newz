# repo-newz

fetches 24h of github activity across a configured repo list, writes a daily
summary into a hugo site, rebuilds and publishes the site, and posts the
summary to slack with a link to the rendered page. sonnet writes the prose; the
code handles fact gathering.

## setup

### 1. install dependencies

```text
uv sync
```

### 2. configure secrets

copy `.env.example` to `.env` and fill in your values:

```text
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
HUGO_SITE_DIR=/path/to/your/hugo/site
HUGO_CONTENT_DIR=/path/to/your/hugo/site/content/repo-newz
HUGO_PUBLISH_DIR=/path/to/served/www/root
```

`GITHUB_TOKEN` needs `repo` scope. grab your current token with:

```text
gh auth token
```

`HUGO_SITE_DIR` is the hugo project root (where `config.toml` lives); the
published site's `baseURL` is read from there to build page links.
`HUGO_CONTENT_DIR` is where the daily markdown is written - it must live under
`<HUGO_SITE_DIR>/content/`, and its path under `content/` becomes the URL
section (e.g. `content/repo-newz` -> `/repo-newz/`). `HUGO_PUBLISH_DIR` is the
directory the built site is copied into for serving.

> note: the hugo site's home page must be `content/_index.md`, not
> `content/index.md`. a root `index.md` is a leaf bundle and silently prevents
> child sections like `repo-newz/` from rendering.

### 3. configure repos

copy `config.yaml.example` to `~/.config/repo-newz/config.yaml` and edit
the repo list:

```text
mkdir -p ~/.config/repo-newz
cp config.yaml.example ~/.config/repo-newz/config.yaml
```

```yaml
window_hours: 24
model: claude-sonnet-4-6
repos:
  - anthropics/claude-code
  - owner/other-repo
```

you can override the location at runtime with `--config PATH`.

### 4. test a run

```text
./repo-newz --dry-run
```

this prints the resolved paths, page url, and repo list without actually
calling anthropic, building, or writing anything. for a live run:

```text
./repo-newz
```

the markdown lands at `$HUGO_CONTENT_DIR/repo-activity-YYYYMMDD.md`, the site is
rebuilt and copied into `$HUGO_PUBLISH_DIR`, and the page is reachable at
`<baseURL>/<section>/repo-activity-YYYYMMDD/`.

### 5. schedule with cron

add this line to `crontab -e` (adjust the path as needed):

```text
0 6 * * * $HOME/repo-newz/repo-newz >> $HOME/repo-newz/logs/repo-newz.log 2>&1
```

runs daily at 06:00 local time. log output piles up in `logs/repo-newz.log`.

to smoke-test the cron wiring, temporarily change to `*/5 * * * *`, watch the
log file for a few minutes, then restore to daily.

## how it works

1. reads `config.yaml` and `.env` for the repo list and credentials
2. hits the github REST API for each repo - commits, PRs, issues, releases - over
   the configured window (default: last 24h)
3. passes the raw event data to sonnet, which writes prose summaries into two
   named slots: an overview and a per-repo narrative
4. renders everything into a jinja template (with hugo front matter) and writes
   the markdown to `$HUGO_CONTENT_DIR/repo-activity-YYYYMMDD.md`
5. runs `hugo` to rebuild the site, then merge-copies `public/` into
   `$HUGO_PUBLISH_DIR` - additive only, so files the build did not produce
   (other served trees, static assets, etc.) are never deleted or overwritten
6. posts the summary to slack with a link to the published page

on empty days (zero activity across all repos), it still writes a stub file so
you get a consistent presence on the site.

## options

```text
./repo-newz [options]

  --dry-run          print resolved paths and repo list; no API calls, no writes
  --since HOURS      override the window_hours from config
  --config PATH      use a different config.yaml (default: ~/.config/repo-newz/config.yaml)
  --env PATH         use a different .env file
  -v, --verbose      enable debug logging
```

## failure drill

`scripts/failure-drill.sh` exercises the error paths manually:

```text
bash scripts/failure-drill.sh
```

## exit codes

| code | meaning |
|---|---|
| 0 | success |
| 1 | unexpected error |
| 2 | config / env var error |
| 3 | github 401 - bad token |
| 4 | github rate limit exhausted |
| 5 | hugo content dir, build, or publish target failure |

per-repo failures (404, timeouts, permission errors on a single repo) don't stop
the run - they get collected as warnings and appear in a `## warnings` section at
the bottom of the output file.

## running tests

```text
uv run pytest -v
```
