# Global conventions

## Git workflow (multi-device: Linux desktop + phone remote-control + MacBook)
GitHub is the single source of truth. All three devices sync through it, so keep
every repo committed and pushed frequently — stale local state is what breaks the
flow between devices.

- **Commit at milestones, with real messages.** When a coherent unit of code
  works (compiles/runs/a sub-feature is done), commit it with a clear, descriptive
  message. That is the primary commit mechanism — clean, intentional history. Do
  NOT scatter half-done WIP; a Stop hook safety-nets leftovers on feature branches,
  so you should rarely be the reason work is uncommitted.
- **Protect `main`.** `main`/`master` must stay clean: only intentional,
  milestone-quality, working commits. Never leave junk or half-done state on it.
  The auto-commit hook is hands-off on protected branches by design — do real
  milestone commits there yourself, or do exploratory work on a feature branch.
- **Pushes are for device handoff.** Pushing is how the phone and MacBook get the
  latest code, so push when leaving the desk or switching devices — and otherwise
  when there's a reason to. Only ever push from a working/coherent state so pushed
  branches are never broken or unusable. **Always ask before `git push`** (unless
  I've said "push when done"); direct pushes to `main` are allowed with approval.
- **Pull before you work.** A SessionStart hook auto-rebases onto origin. If you
  start substantial work and haven't synced this session, `git fetch` first so you
  never build on stale code. If a rebase conflicts, stop and surface it.
- **One source of truth.** Prefer working the same branch across devices and
  syncing through GitHub rather than spawning parallel branches that later need
  reconciling.

## Remote-control sessions (driven from the phone while away)
- I can't intervene mid-step, so work to the next milestone, commit it with a real
  message, and then ask to push — rather than stopping (or pushing) half-done.
- Never push a broken/incomplete state; the whole point of the push is that the
  other device can pick up working code.
- Surface anything needing my decision via a notification-worthy summary at the end.
