#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): format and autofix the Python file just written, silently.
# Uses the project's own ruff through `uv run --no-sync` so it is fast and never installs
# anything. A no-op outside a uv project. Never blocks: every exit path is 0.
set -uo pipefail
input="$(cat 2>/dev/null || true)"
f="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)"
case "$f" in *.py) ;; *) exit 0 ;; esac
[ -f "$f" ] || exit 0
command -v uv >/dev/null 2>&1 || exit 0
dir="$(dirname "$f")"
while [ "$dir" != "/" ] && [ ! -f "$dir/pyproject.toml" ]; do dir="$(dirname "$dir")"; done
[ -f "$dir/pyproject.toml" ] || exit 0
cd "$dir" || exit 0
uv run --no-sync ruff format "$f" >/dev/null 2>&1 || true
uv run --no-sync ruff check --fix "$f" >/dev/null 2>&1 || true
exit 0
