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
ln -sfn ~/dotfiles/claude/skills/recap ~/.claude/skills/recap
ln -sfn ~/dotfiles/claude/skills/land-branch ~/.claude/skills/land-branch
ln -sfn ~/dotfiles/claude/skills/meeting-to-actions ~/.claude/skills/meeting-to-actions
ln -sfn ~/dotfiles/claude/skills/meeting-pack ~/.claude/skills/meeting-pack
ln -sfn ~/dotfiles/claude/skills/coverage-audit ~/.claude/skills/coverage-audit
ln -sfn ~/dotfiles/claude/skills/run-status ~/.claude/skills/run-status
git clone https://github.com/Leonxlnx/taste-skill.git ~/repos/taste-skill   # third-party; git pull updates
ln -sfn ~/repos/taste-skill/skills/taste-skill ~/.claude/skills/design-taste-frontend
# taste skill's WebP photos: Homebrew's plain ffmpeg has no libwebp; check with ffmpeg -encoders | grep libwebp
brew install ffmpeg-full && brew link --force ffmpeg-full   # macOS (keg-only, so link it)
gh repo clone oeleel/jobapp ~/jobapp
gh repo clone oeleel/n2o-notes ~/N2O/notes
gh repo clone oeleel/epiForecasting-private <dir next to your epiForecasting clone>
```

Remote is HTTPS through `gh` auth; SSH keys are not required.

n2o-kit: run only steps 1 and 2 of `~/N2O/n2o-kit/install.sh`. Step 3 appends the kit's rules
line to the global `CLAUDE.md`, which is this repo's file; the rules load from `~/N2O/CLAUDE.md`
instead (`docs/macbook-dev-inventory.md` section 4). To pick up new kit skills after a pull:

```bash
for d in ~/N2O/n2o-kit/skills/*/; do ln -sfn "$d" ~/.claude/skills/"$(basename "$d")"; done
```

Herdr agents panel rebuild: on macOS install `herdr/dev.leolee.herdr-remod.plist`; on Linux
install the systemd user units in `herdr/systemd/` (commands in `herdr-remod.service`).

Updates on the Arch desktop: `omarchy-update` updates the system, AUR and mise tools, then runs
`omarchy/hooks/post-update.d/dev-tools.hook` for npm global CLIs, treg, claude-swap and a clean
`main` of each skill clone. Native Claude Code updates itself. Two machine-local files go with it:

- `~/.default-npm-packages`, one per line: `pnpm`, `vercel`, `neonctl`, `heroku`, `pm2`, and the
  absolute paths of `~/N2O/nah` and `~/N2O/nak`. mise installs them into each new Node.
- `~/.config/mise/config.toml`: `disable_tools = ["claude"]` under `[settings]`, so Omarchy's mise
  entry does not replace the native Claude Code, and `supabase = "latest"` under `[tools]`.

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
