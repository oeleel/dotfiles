#!/usr/bin/env bash
# PreToolUse hook (Bash): in a uv project, refuse bare interpreter and tool invocations that
# bypass the project environment, and name the `uv run` form. Exit 2 blocks the call and
# shows the message to the agent. A no-op outside a uv project.
set -uo pipefail
input="$(cat 2>/dev/null || true)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
[ -z "$cmd" ] && exit 0
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -f "${cwd:-$PWD}/pyproject.toml" ] || exit 0
# First word of each shell segment (split on newlines, &&, ||, ;, |).
offender="$(printf '%s\n' "$cmd" | perl -pe 's/(&&|\|\||;|\|)/\n/g' \
  | sed -E 's/^[[:space:]]*//' | awk 'NF {print $1}' \
  | grep -E -m1 '^(pip3?|python3?([.][0-9]+)?|pytest|ruff|mypy)$' || true)"
[ -z "$offender" ] && exit 0
cat >&2 <<MSG
Blocked: '$offender' runs outside the project environment. Use the uv form:
  pip install X          -> uv add X   (or uv add --dev X)
  python ...             -> uv run python ...
  pytest / ruff / mypy   -> uv run pytest / uv run ruff / uv run mypy
MSG
exit 2
