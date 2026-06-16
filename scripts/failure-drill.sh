#!/usr/bin/env bash
# Exercises failure paths for repo-newz. Run from the repo root.
# Each scenario prints PASS or FAIL with the expected vs actual exit code.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UV="${UV:-$(command -v uv)}"
RUN="$UV run python -m repo_newz"
PASS=0
FAIL=0

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" -eq "$expected" ]; then
    echo "PASS  [$label] (exit $actual)"
    PASS=$((PASS + 1))
  else
    echo "FAIL  [$label] expected exit $expected, got $actual"
    FAIL=$((FAIL + 1))
  fi
}

cd "$REPO_ROOT"

echo "=== repo-newz failure drill ==="

echo ""
echo "-- scenario: missing ANTHROPIC_API_KEY --"
env -i HOME="$HOME" GITHUB_TOKEN="ghp_test" \
  HUGO_SITE_DIR="/tmp" HUGO_CONTENT_DIR="/tmp/content/repo-newz" HUGO_PUBLISH_DIR="/tmp" \
  $RUN --dry-run 2>/dev/null || rc=$?
check "missing ANTHROPIC_API_KEY -> exit 2" 2 "${rc:-0}"

echo ""
echo "-- scenario: .env file missing and no env vars --"
rc=0
env -i HOME="$HOME" \
  $RUN --env /tmp/nonexistent_repo_newz.env --dry-run 2>/dev/null || rc=$?
check "missing .env and no env vars -> exit 2" 2 "${rc:-0}"

echo ""
echo "-- scenario: malformed config.yaml --"
TMPCONFIG=$(mktemp /tmp/repo_newz_XXXXXX.yaml)
echo ": bad: yaml: [" > "$TMPCONFIG"
rc=0
ANTHROPIC_API_KEY=sk-test GITHUB_TOKEN=ghp_test \
  HUGO_SITE_DIR=/tmp HUGO_CONTENT_DIR=/tmp/content/repo-newz HUGO_PUBLISH_DIR=/tmp \
  $RUN --config "$TMPCONFIG" --dry-run 2>/dev/null || rc=$?
check "malformed config.yaml -> exit 2" 2 "${rc:-0}"
rm -f "$TMPCONFIG"

# a publish-time failure (exit 5) needs a live run: valid config + a real hugo
# site to build, but a non-existent publish target. set HUGO_SITE_DIR/CONTENT_DIR
# to a real hugo site via env before running the drill.
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${ANTHROPIC_API_KEY:-}" ] \
   && [ -d "${HUGO_SITE_DIR:-/nonexistent}" ]; then
  echo ""
  echo "-- scenario: HUGO_PUBLISH_DIR does not exist (live run) --"
  rc=0
  HUGO_PUBLISH_DIR="/tmp/nonexistent_publish_xyz_$$" \
    $RUN --config "$REPO_ROOT/config.yaml.example" 2>/dev/null || rc=$?
  check "missing publish dir -> exit 5" 5 "${rc:-0}"
else
  echo ""
  echo "SKIP  [missing publish dir] -- set GITHUB_TOKEN, ANTHROPIC_API_KEY, HUGO_SITE_DIR, HUGO_CONTENT_DIR in env"
fi

echo ""
echo "=== results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
