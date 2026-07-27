# Global conventions

## Git workflow (multi-device: Linux desktop + phone remote-control + MacBook)
GitHub is the single source of truth. All three devices sync through it, so keep
every repo committed and pushed frequently — stale local state is what breaks the
flow between devices.

- **Commit autonomously.** At natural checkpoints (a working unit of code, end of
  a task, before a risky change) commit with a clear, descriptive message. Never
  leave uncommitted work when a task completes. A Stop hook safety-nets anything
  left over, so you should rarely be the reason work is uncommitted.
- **Ask before pushing.** Pushing publishes to the other devices — always ask for
  confirmation before `git push` (unless I've said "push when done" for that task).
  When you finish a unit of work, proactively offer to push.
- **Pull before you work.** A SessionStart hook auto-rebases onto origin. If you
  start substantial work and haven't synced this session, `git fetch` first so you
  never build on stale code. If a rebase conflicts, stop and surface it.
- **One branch per device is not the goal — one source of truth is.** Prefer
  working on the same branch across devices and syncing through it rather than
  spawning parallel branches that later need reconciling.

## Remote-control sessions (driven from the phone while away)
- I can't intervene mid-step, so bias toward finishing a self-contained unit,
  committing it, and then asking to push — rather than stopping half-done.
- Surface anything needing my decision via a notification-worthy summary at the end.
