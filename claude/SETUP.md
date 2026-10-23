# Claude Code setup on a device

How a device gets Leo's agent context. Information lives with its owner and is read on
demand; only `CLAUDE.md`, `preferences.md` and `rules/git.md` load every session.

| What | Where |
|---|---|
| Global instructions, preferences, rules, hooks | this repo, `claude/` (symlinked into `~/.claude/`) |
| A project's state, decisions, research | that repo's `AGENTS.md` and `docs/` (`documentation/` in epiForecasting) |
| Private notes about epiForecasting | `oeleel/epiForecasting-private`, cloned next to epiForecasting |
| n2o notes | `oeleel/n2o-notes`, cloned to `~/N2O/notes` |
| Career (profile, recruiting, resumes, `/apply`) | `oeleel/jobapp`, cloned to `~/jobapp` |

## New device

```bash
ln -sfn ~/dotfiles/claude/CLAUDE.md   ~/.claude/CLAUDE.md
ln -sfn ~/dotfiles/claude/rules       ~/.claude/rules
ln -sfn ~/dotfiles/claude/hooks       ~/.claude/hooks    # then register them: hooks/README.md
mkdir -p ~/.claude/skills && ln -sfn ~/dotfiles/claude/skills/handoff ~/.claude/skills/handoff
gh repo clone oeleel/jobapp ~/jobapp
gh repo clone oeleel/n2o-notes ~/N2O/notes
gh repo clone oeleel/epiForecasting-private <dir next to your epiForecasting clone>
```

Remote is HTTPS through `gh` auth; SSH keys are not required.

## Device handoff

Leaving a repo for another device: run `/handoff` in it (commits, writes one line to
`docs/STATUS.md`, pushes the branch). Arriving: open the repo; the SessionStart hook pulls.
Pushing a feature branch needs no approval (`rules/git.md`).

Pending on the desktop (as of 2026-10-23): move personal repos from `~/dev/` to `~/repos/`
and leave `~/dev` as a symlink, so paths match the MacBook; then drop the `~/dev/` mention
from `CLAUDE.md` and this file, and fix `~/dev/...` links in each repo's `docs/STATUS.md`.

## One-time migration off ~/knowledge (devices set up before 2026-10-21)

`~/knowledge` (`oeleel/knowledge`) is retired and archived; its README maps every old path
to its new home. On each older device (the desktop keeps personal repos in `~/dev/`):

1. `git -C ~/dotfiles pull` (the SessionStart hook usually has already).
2. Rules: if `~/.claude/rules` is a real directory of symlinks into `~/knowledge/style/`,
   remove it, then `ln -sfn ~/dotfiles/claude/rules ~/.claude/rules`.
3. Skills: remove `~/.claude/skills/knowledge` and `~/.claude/skills/apply` if present
   (`/apply` now lives in `~/jobapp/.claude/skills/apply`, available in jobapp sessions).
4. Auto-memory: delete the `autoMemoryDirectory` line from
   `~/dev/parlee/.claude/settings.local.json` and `~/dev/kalshekki/.claude/settings.local.json`
   (delete the file if that was its only key). Their verdicts are now `docs/verdicts.md`.
5. Pull the project repos so they have the new `docs/`: `git -C ~/dev/parlee pull`,
   `~/dev/kalshekki`, `~/dev/golf-coach`.
6. Clone the three private repos from the table above if missing.
7. If `~/repos/` or `~/dev/` holds an old N2O workflow template (a parent `CLAUDE.md`
   asking to "scan the codebase", `.claude/skills/`, `.pm/`, `scripts/`), move it to the
   trash: it loads into every child repo's sessions.
8. Delete `~/knowledge`.
9. Check: start a session anywhere and run `/memory`; the loaded files should be this
   repo's `CLAUDE.md`, `preferences.md` and `rules/git.md`, with nothing from `~/knowledge`.

Still open as of 2026-10-21: epiForecasting branch `docs/agents-md` (lean `AGENTS.md` +
`documentation/STATUS.md`) merges after `feature/weekly-hindcast`; then fix the
`.claude/CLAUDE.md` reference at `scripts/experiments/peak_rectification.py:155`.
