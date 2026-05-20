#!/usr/bin/env bash
# Exercises failure paths for repo-newz. Run from the repo root.
# Each scenario prints PASS or FAIL with the expected vs actual exit code.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UV="${UV:-/Users/sulrich/.local/bin/uv}"
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
env -i HOME="$HOME" GITHUB_TOKEN="ghp_test" OBSIDIAN_HOME="/tmp" \
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
ANTHROPIC_API_KEY=sk-test GITHUB_TOKEN=ghp_test OBSIDIAN_HOME=/tmp \
  $RUN --config "$TMPCONFIG" --dry-run 2>/dev/null || rc=$?
check "malformed config.yaml -> exit 2" 2 "${rc:-0}"
rm -f "$TMPCONFIG"

if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo ""
  echo "-- scenario: OBSIDIAN_HOME does not exist (live run) --"
  rc=0
  OBSIDIAN_HOME="/tmp/nonexistent_vault_xyz_$$" \
    $RUN --config "$REPO_ROOT/config.yaml.example" 2>/dev/null || rc=$?
  check "missing vault -> exit 5" 5 "${rc:-0}"
else
  echo ""
  echo "SKIP  [missing vault] -- GITHUB_TOKEN or ANTHROPIC_API_KEY not set in env"
fi

echo ""
echo "=== results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
