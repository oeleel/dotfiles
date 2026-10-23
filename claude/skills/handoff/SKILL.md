---
name: handoff
description: Move the current repo's work to GitHub so another device can continue it - commit what is open, write one handoff line into docs/STATUS.md, push the branch, and print what to do next. Use when Leo says "handoff", "I'm leaving", "switching to the desktop/MacBook", or at the end of a session with unpushed work.
---

# /handoff - leave this repo ready for the other device

GitHub is the single source of truth. The other device pulls on session start (the
`sync-on-start.sh` hook), so the only step that must happen here is the push. Everything
below exists to make that push complete and self-describing.

Optional argument: the next task in Leo's words, e.g. `/handoff finish the pose adapter
tests`. Without it, derive the next task from the session.

## Procedure

1. **Locate.** `git rev-parse --show-toplevel`, current branch, `hostname -s`, today's date.
   Not a git repo: stop and say so.
2. **Protected branch check.** If the branch is `main`, `master`, or origin's default branch
   and the tree is dirty, ask Leo one question: commit directly to `main` (small, sequential
   edit) or move the changes to a new `feature/<slug>` branch. Do not proceed on your own.
3. **Commit the work.** Read `git status` and `git diff`. If the tree is dirty, commit with
   a real Conventional Commit message describing the change (never "checkpoint" or "WIP").
   A clean tree skips this step. Run the repo's quick test command first if one is obvious
   (`uv run pytest -q`, `npm test`); a failing suite does not block the handoff, but the
   handoff line must say the tests fail.
4. **Write the handoff line.** If `docs/STATUS.md` exists, replace (or add) a section:

   ```
   ## Last handoff

   <YYYY-MM-DD>, <host>, `<branch>`: <next task in one sentence>. <State in one sentence:
   tests green/red, anything half-done.>
   ```

   Keep exactly one entry; the previous entry is in git history. If `docs/STATUS.md` does
   not exist (dotfiles, notes repos), skip this step and say so in the summary.
   Commit: `docs: handoff <YYYY-MM-DD> from <host>`.
5. **Push.** `git push -u origin <branch>`. A feature branch needs no approval. `main`
   needs Leo's approval (ask once). If the push is rejected because the remote moved,
   `git pull --rebase` and push again; on a conflict, stop and report.
6. **Report** in four lines: repo and branch; the commits pushed (count and last subject);
   the next task; and the resume instruction: open the repo on the other device, the
   SessionStart hook pulls, read `docs/STATUS.md`.

## Rules

- Never force-push. Never push a branch whose tests you know are red without saying so in
  the handoff line.
- Do not touch other repos. One `/handoff` per repo; Leo runs it where it is needed.
- Do not rewrite the rest of `docs/STATUS.md`. Open loops and state belong to the project's
  own workflow; the handoff line is a pointer, not a status report.
