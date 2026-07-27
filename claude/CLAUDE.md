# Global conventions

## Knowledge base
My personal knowledge system lives at `~/knowledge` — who I am, how I work, what
I'm building, and what's next. Loaded every session:

@~/knowledge/me.md
@~/knowledge/preferences.md
@~/knowledge/projects/_index.md
@~/knowledge/next-actions.md

Coding style loads contextually from `~/.claude/rules/` (symlinked from
`~/knowledge/style/`). On-demand detail (per-project pages, notes) lives in
`~/knowledge` and is read when relevant.

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
- **A feature branch per session for non-trivial work.** Any substantial change —
  and *especially* remote-control / parallel sessions, or when another session may
  already be working the same repo — happens on its own `feature/…` branch, never
  directly on `main`. This keeps two concurrent sessions from interleaving commits
  on `main` (which otherwise tangles history). Direct-to-`main` is fine only for
  small, sequential, solo edits (e.g. a quick dotfiles tweak). Merge feature
  branches into `main` via squash so `main` gets one clean commit per unit.

## Remote-control sessions (driven from the phone while away)
- I can't intervene mid-step, so work to the next milestone, commit it with a real
  message, and then ask to push — rather than stopping (or pushing) half-done.
- Never push a broken/incomplete state; the whole point of the push is that the
  other device can pick up working code.
- Surface anything needing my decision via a notification-worthy summary at the end.
