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
ln -sfn ~/dotfiles/claude/skills/herdr ~/.claude/skills/herdr
gh repo clone oeleel/jobapp ~/jobapp
gh repo clone oeleel/n2o-notes ~/N2O/notes
gh repo clone oeleel/epiForecasting-private <dir next to your epiForecasting clone>
```

Remote is HTTPS through `gh` auth; SSH keys are not required.

## Device handoff

Leaving a repo for another device: run `/handoff` in it (commits, writes one line to
`docs/STATUS.md`, pushes the branch). Arriving: open the repo; the SessionStart hook pulls.
Pushing a feature branch needs no approval (`rules/git.md`).

Both devices use the same layout: personal repos in `~/repos/`, n2o work in `~/N2O/` (one
folder per repo, one `<repo>-<topic>` sibling per git worktree).

## Open items

Still open as of 2026-10-21: epiForecasting branch `docs/agents-md` (lean `AGENTS.md` +
`documentation/STATUS.md`) merges after `feature/weekly-hindcast`; then fix the
`.claude/CLAUDE.md` reference at `scripts/experiments/peak_rectification.py:155`.
