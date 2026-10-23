#!/usr/bin/env bash
# Stop hook: "done" cannot be red. In a uv Python project it runs the fast checks (ruff,
# format, mypy, the non-slow tests) and blocks the stop with the failing output so the agent
# fixes it before completing. Bails out when stop_hook_active is set (it already fired once
# on this stop), so it can never loop. Register per project; a no-op without pyproject.toml.
#
# Test guard, dumb and loud: uncommitted edits to tests/ that remove assertions, add skips or
# expected failures, or touch a tolerance are reported once and block until the agent states
# the reason in its reply (the second stop passes through the bailout).
set -uo pipefail
input="$(cat 2>/dev/null || true)"
[ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ] && exit 0
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -z "$cwd" ] && cwd="$PWD"
cd "$cwd" 2>/dev/null || exit 0
[ -f pyproject.toml ] || exit 0
command -v uv >/dev/null 2>&1 || exit 0

fail() { printf '%s\n%s\n' "$1" "$2" >&2; exit 2; }

out="$(uv run --no-sync ruff check . 2>&1)" \
  || fail "Stop gate: ruff check fails. Fix before completing:" "$(printf '%s' "$out" | tail -30)"
out="$(uv run --no-sync ruff format --check . 2>&1)" \
  || fail "Stop gate: ruff format --check fails. Run 'uv run ruff format .' before completing:" "$(printf '%s' "$out" | tail -10)"
if grep -q '^\[tool\.mypy\]' pyproject.toml; then
  out="$(uv run --no-sync mypy 2>&1)" \
    || fail "Stop gate: mypy fails. Fix before completing:" "$(printf '%s' "$out" | tail -30)"
fi
out="$(uv run --no-sync pytest -x -q -m 'not slow' 2>&1)" \
  || fail "Stop gate: fast tests fail. Fix before completing (uv run pytest -x -q -m 'not slow'):" "$(printf '%s' "$out" | tail -40)"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
[ -d tests ] || exit 0
diff="$(git diff HEAD -- tests 2>/dev/null || true)"
removed="$(printf '%s\n' "$diff" | grep -E '^-[[:space:]]*(assert\b|np\.testing\.|pytest\.raises)' || true)"
skips="$(printf '%s\n' "$diff" | grep -E '^\+.*(pytest\.mark\.(skip|xfail)|pytest\.(skip|xfail)\()' || true)"
tols="$(printf '%s\n' "$diff" | grep -E '^[-+].*\b(rtol|atol|[A-Z_]*TOL[A-Z_]*)\b' | grep -Ev '^(\+\+\+|---)' || true)"
untracked_skips="$(git ls-files --others --exclude-standard -- tests 2>/dev/null \
  | xargs -r grep -lE 'pytest\.mark\.(skip|xfail)|pytest\.(skip|xfail)\(' 2>/dev/null || true)"
if [ -n "$removed$skips$tols$untracked_skips" ]; then
  fail "Stop gate: uncommitted test changes weaken or bypass checks. State the reason in your reply (and the commit body), or restore them:" \
"$(printf '%s\n%s\n%s\n%s\n' "$removed" "$skips" "$tols" "$untracked_skips" | sed '/^$/d' | head -40)"
fi
exit 0
