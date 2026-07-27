#!/usr/bin/env bash
# SessionStart hook: pull the latest so you never start on stale code.
# Fetches origin and rebases the current branch (autostash handles a dirty
# tree). On conflict it aborts cleanly and warns instead of leaving a mess.
# Never pushes. Always exits 0 so it can't block a session.
set -uo pipefail

input="$(cat 2>/dev/null || true)"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -z "$cwd" ] && cwd="$PWD"
cd "$cwd" 2>/dev/null || exit 0

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -f "$root/.no-auto-sync" ] && exit 0

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ "$branch" = "HEAD" ] && exit 0   # detached; leave it alone

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || true)"
[ -z "$upstream" ] && exit 0        # no tracking branch; nothing to sync

# Fetch (bounded so a network hiccup can't hang the session start).
timeout 20 git fetch --quiet 2>/dev/null || { echo "[sync] fetch failed/offline — skipping"; exit 0; }

behind="$(git rev-list --count HEAD..@{u} 2>/dev/null || echo 0)"
ahead="$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)"

if [ "$behind" = "0" ]; then
  [ "$ahead" != "0" ] && echo "[sync] $(basename "$root") is ${ahead} commit(s) ahead of ${upstream} (unpushed)"
  exit 0
fi

echo "[sync] $(basename "$root") is ${behind} behind ${upstream} — rebasing…"
if timeout 30 git pull --rebase --autostash --quiet 2>/dev/null; then
  echo "[sync] up to date with ${upstream}"
else
  git rebase --abort >/dev/null 2>&1 || true
  echo "[sync] ⚠ auto-rebase hit a conflict and was aborted. Resolve manually: git pull --rebase"
fi
exit 0
