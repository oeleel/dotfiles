# Claude Code hooks (synced via dotfiles)

These scripts implement the multi-device git workflow (see `../CLAUDE.md`).

- **`checkpoint-commit.sh`** — `Stop` hook. Safety-net commit of leftover WIP on
  **feature branches only**; on `main`/`master`/default it refuses to commit and
  just nudges. Never pushes. Opt out per-repo with a `.no-auto-commit` file.
- **`sync-on-start.sh`** — `SessionStart` hook. `fetch` + `pull --rebase --autostash`
  so you never build on stale code. Never pushes. Opt out with `.no-auto-sync`.

## Activate on a new machine
The scripts sync automatically, but each machine's `~/.claude/settings.json` must
register them (settings.json is machine-local — it isn't symlinked). Symlink this
dir and add the hooks block:

```bash
ln -s ~/dotfiles/claude/hooks ~/.claude/hooks   # if not already linked
```

```jsonc
// ~/.claude/settings.json
"hooks": {
  "SessionStart": [{ "matcher": "startup|resume", "hooks": [
    { "type": "command", "command": "bash ~/.claude/hooks/sync-on-start.sh", "timeout": 45 }
  ]}],
  "Stop": [{ "hooks": [
    { "type": "command", "command": "bash ~/.claude/hooks/checkpoint-commit.sh", "timeout": 30 }
  ]}]
}
```

Then open `/hooks` once (or restart) so Claude Code reloads the config.
