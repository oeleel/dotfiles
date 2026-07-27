#!/usr/bin/env bash
# Stop hook: milestone safety-net commit.
#
# Philosophy: Claude makes the real, milestone-quality commits during work.
# This hook only catches leftover uncommitted changes so nothing is lost on a
# device handoff. It NEVER pushes.
#
# main/master are PROTECTED: the hook never commits there — it only nudges — so
# your default branch can never accumulate autonomous WIP commits. On feature
# branches it autosaves leftovers (disposable / squashable before they reach main).
set -euo pipefail

emit() { printf '{"systemMessage":%s,"suppressOutput":true}\n' "$(printf '%s' "$1" | jq -Rs .)"; }

# Resolve the working dir from the hook JSON (fall back to PWD).
input="$(cat 2>/dev/null || true)"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -z "$cwd" ] && cwd="$PWD"
cd "$cwd" 2>/dev/null || exit 0

# Only act inside a git work tree.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Opt-out: drop a .no-auto-commit file in a repo to disable this there.
[ -f "$root/.no-auto-commit" ] && exit 0

# Don't touch a repo mid-merge/rebase/cherry-pick.
gitdir="$(git rev-parse --git-dir 2>/dev/null)"
for m in MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD; do
  [ -e "$gitdir/$m" ] && exit 0
done

# Nothing to do on a clean tree.
[ -z "$(git status --porcelain 2>/dev/null)" ] && exit 0

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

# PROTECTED branches: never auto-commit — just nudge. Includes main, master, and
# whatever origin's default branch is.
default="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
case "$branch" in
  main|master|"$default")
    emit "⚠ Uncommitted changes left on protected branch '$branch' — not auto-committed. Commit at a milestone with a real message (or move to a feature branch)."
    exit 0
    ;;
esac

# Feature branch: safety-net autosave so WIP survives a handoff.
n="$(git status --porcelain | wc -l | tr -d ' ')"
files="$(git status --porcelain | awk '{print $2}' | head -3 | paste -sd', ' -)"
[ "$n" -gt 3 ] && files="$files, +$((n-3)) more"

git add -A
git commit -q --no-verify -m "checkpoint: WIP autosave (${n} file(s): ${files})" \
  -m "Automated safety-net commit by Claude Code Stop hook on feature branch '${branch}'. Not pushed; squash before it reaches main." || exit 0

emit "checkpoint: autosaved ${n} file(s) on '${branch}' (local only, not pushed)"
exit 0
