# Claude Code hooks (synced via dotfiles)

These scripts implement the multi-device git workflow (see `../CLAUDE.md`).

- **`checkpoint-commit.sh`** — `Stop` hook. Safety-net commit of leftover WIP on
  **feature branches only**; on `main`/`master`/default it refuses to commit and
  just nudges. Never pushes. Opt out per-repo with a `.no-auto-commit` file.
- **`sync-on-start.sh`** — `SessionStart` hook. `fetch` + `pull --rebase --autostash`
  so you never build on stale code. Never pushes. Opt out with `.no-auto-sync`.

## Activate on a new machine
Full device setup (links, private repos, the ~/knowledge migration): `../SETUP.md`.

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

## Python project hooks (added 2026-10-23, from the golf-coach agent playbook)

- **`format-python.sh`** - `PostToolUse` on `Edit|Write`, registered globally. Runs the
  project's `ruff format` and `ruff check --fix` on the edited `.py` file, silently. No-op
  outside a uv project.
- **`stop-gate.sh`** - `Stop` hook, registered **per project** in `.claude/settings.json`.
  ruff check, ruff format --check, mypy (if configured), `pytest -m "not slow"`; blocks the
  stop with the failing output. Also flags uncommitted test edits that remove assertions, add
  skips, or touch tolerances. Bails out on `stop_hook_active`, so it fires once per stop.
- **`enforce-uv.sh`** - `PreToolUse` on `Bash`, registered per project. Blocks bare `pip`,
  `python`, `pytest`, `ruff`, `mypy` and prints the `uv run` form.

Stop hooks run concurrently, so `checkpoint-commit.sh` may autosave a red tree on the first
stop; the gate then makes the agent fix it and the next stop autosaves the fix. Checkpoints
are squashed before `main`, so this is harmless.
