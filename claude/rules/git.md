# Git - Leo

Loaded in every session (no path scope). GitHub is the single source of truth across the
desktop, the MacBook, and the phone.

## Commits

- Conventional Commits, imperative present tense, lowercase after the colon: `feat:`,
  `fix:`, `perf:`, `refactor:`, `docs:`, `test:`, `chore:`, `ops:`. Add a scope in
  parentheses when it sharpens the message, such as `fix(adapters): ...`.
- Subject of about 50 to 70 characters. Add a body when the reason is not obvious from the
  subject.
- Never add an agent co-author or any agent attribution line to a commit.
- Commit at milestones: when a coherent unit works (builds, runs, a sub-feature is done).
  One logical change per commit; no half-done WIP. A Stop hook commits leftovers on feature
  branches, so an agent should rarely be the reason work is uncommitted.

Examples from Leo's history:
- `fix(oracle): paginate crypto discovery - hourly clock was ~50x under-recorded`
- `feat(web): Today bankroll headline reflects disjoint paper P&L`
- `test: cover the losses branch in day-grouped history (review nit)`

## Branches

- `main` holds only intentional, working, milestone-quality commits. The auto-commit hook
  does not touch protected branches.
- Non-trivial work happens on its own `feature/<name>` branch per session, especially in
  remote-control or parallel sessions. Merge into `main` by squash. Direct commits to `main`
  are fine only for small, sequential, solo edits.
- Keep working the same branch across devices instead of creating parallel branches.

## Sync

- A SessionStart hook rebases onto origin. Before substantial work, run `git fetch` if the
  repo has not been synced this session. If a rebase conflicts, stop and report it.
- Pushing the current feature branch needs no approval: the push is the device handoff,
  and work that stays on one machine is lost to the other. Ask before any push to `main`,
  unless Leo has said "push when done". Direct pushes to `main` are allowed with approval.
- Leaving a repo for the day or for another device: run `/handoff` (commit, one status
  line, push).
- Push only from a working state. A pushed branch must be usable from another device.
