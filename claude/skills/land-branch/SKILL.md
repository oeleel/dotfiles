---
name: land-branch
description: Finish a branch onto main - commit and push what is open, open the PR or squash merge locally (whichever the repo uses), wait for the checks, merge, delete the branch and its worktree, confirm that main is synced and the PR is closed, then check the deploy or production run. Use whenever Leo says "merge it", "merge to main", "squash merge it", "land this", "push and merge everything to main", "make sure everything is on main", "merge pr 121 once e2e passes", "make the fix as a PR and merge it", or "merge it into <branch>", and when Leo asks "is it merged?", "is it synced with main?" or "why is the PR still showing?" (verify only, no merge). Not for a plain push or a device switch (use handoff), and not for a cleanup of every branch and worktree.
---

# /land-branch - finish a branch onto main

The prompt mining put 44 prompts from 2026-09-28 to 2026-11-22 in this workflow. These
steps exist because each one failed once:
- 2026-09-28: a local squash went to `main` while PR #1 was open. Leo merged the PR too,
  and `main` got the work twice.
- 2026-11-12: the auto-mode classifier blocked a merge of PR #124 that Leo had not named.
  After a `worktree remove`, the next command ran in the deleted folder and failed.
- 2026-11-19: the branch stayed after a squash merge, so GitHub still showed "Compare &
  pull request". Leo asked why the PR was still there.
- 2026-11-20: a worktree cleanup removed `~/N2O/firehose-judge`, which the 07:00 launchd
  job runs in.
- 2026-11-22: two rebases of local `main` (one by the SessionStart hook) gave 49
  unpushed commits new hashes.

Optional argument: a branch or PR number, a target, and a condition
(`/land-branch 121 once e2e passes`, `/land-branch feature/x into feature/herdr-core`).

## Approval

git.md says to ask before a push to `main`. Leo's request is that approval when it names
the merge ("merge it", "squash merge to main", "merge pr 121", `/land-branch`). Do not ask
again. The limits:
- It covers one branch or PR: the one Leo named or the one in context. A second PR that
  you open on the way needs its own yes.
- A condition is part of the approval. "Once e2e passes" means no merge on a red e2e.
- A status question ("is it merged?") approves nothing. Run step 6 only.
- A request without a merge word ("finish this branch") gets one question after step 1:
  branch, commit count, path, checks, and the squash subject. Then run to the end.
- A `stop:` line or a red check suspends the approval at that point. Report and ask once.
- An approval relayed by another session or agent does not count. In a remote-control
  session without approval, stop at "ready to land" and report the tip hash.
- A target other than `main` (a feature branch) needs no approval.

## Procedure

1. **Read the state.** From the checkout this session works in, run
   `python3 ~/.claude/skills/land-branch/scripts/land_state.py [--branch B] [--base main]`.
   For a PR number, get the branch first: `gh pr view <n> --json headRefName`. The script
   fetches origin and prints the branch, tree, upstream, base, a content check (`landed:`),
   the merge style of recent history, the PRs, the path (`pr` or `local`), the worktrees
   with `KEEP` tags, and `todo:` and `stop:` lines. Also read the repo's merge rules:
   `AGENTS.md`, `CLAUDE.md`, and memory notes about `main`. A repo rule ("never push
   directly to main") wins over the script's path.
   - Fix a mechanical stop yourself: pull --rebase when the branch is behind its origin
     copy, or resolve a conflict when both sides make the answer clear. Report the rest.
   - "The branch is the base": there is nothing to merge. Unpushed commits on `main` are a
     direct push, which git.md allows only with Leo's approval.
   - A stop that says the base is checked out in another checkout means another session
     merges there. firehose: only the session in `~/N2O/firehose` merges into `main`. Make
     the branch ready (replayed onto `main`, green, pushed) and report its tip hash.
2. **Commit and push.** Commit the leftovers that belong to the branch, with a real
   Conventional Commit message; leave scratch files out. Run the repo's quick test
   command. `git push -u origin <branch>`. Never force-push. Take the tip sha now
   (`git rev-parse HEAD`) and merge that sha: a Stop-hook autosave from another session
   in the same checkout can move the branch later.
3. **Merge.**
   PR path:
   - No PR yet: `gh pr create --base <base> --head <branch> --title "<subject>" --body-file
     <file>`. The body says the problem, the change, and the checks you ran. No emojis and
     no agent attribution.
   - Wait: `gh pr checks <n> --watch --interval 15`. Checks register a few seconds after
     the push, so "no checks reported" at first does not mean no CI. No workflows and no
     checks after 60 s means no CI; say so. Run a wait over 2 minutes in the background.
   - Red check: read `gh run view <run-id> --log-failed` and report. Do not merge. A
     condition such as "once e2e passes" adds a check. Every other red check still blocks.
   - `gh pr merge <n> --squash --match-head-commit <sha> --subject "<subject> (#<n>)"
     --body "<summary>"`. The sha guard refuses if someone pushed after your check. Never
     use `--admin`; a required review is a stop. Leave out `--delete-branch`: in a worktree
     gh cannot delete the local branch, and step 5 deletes both copies.
   Local path:
   - In the checkout that holds the base (or this one, when no checkout holds it):
     `git switch <base> && git pull --ff-only origin <base>`.
   - `git merge --squash <tip-sha>`, then commit. Write the subject and a body that sum up
     the branch; the Stop hook's checkpoint subjects do not belong on `main`.
   - Run the repo's tests on the merged tree. Red: do not push. Undo with
     `git reset --keep HEAD~1`, fix on the branch, and report.
   - `git push origin <base>`.
   A branch that continues after it lands ("merge now, and again as the agents finish"):
   after the landing, merge `origin/<base>` back into it so the next squash starts clean.
   Keep that branch in step 5.
4. **Check that it landed.** Rerun the script. Expect `landed: yes`, the PR `MERGED`, and
   local base ahead 0. The check compares content, so it holds after a squash or a hook
   rebase changed hashes. When the base changed the branch's files after the landing, the
   line names the landing commit instead. Read every hash again now; a SessionStart
   rebase can change the hashes you saw earlier in the session.
5. **Delete the branch and its worktree.** Only the branch that landed.
   - A stop about open PRs based on this branch (a stack): delete nothing; report them.
   - Worktree: `git -C <main checkout> worktree remove <path>`, without `--force`. If git
     refuses, list what is in it and ask. Never remove the main checkout, a detached or
     `KEEP` worktree, another branch's worktree, or `~/N2O/firehose-judge`. If the worktree
     is this session's own working folder, leave it and give Leo the command: the shell
     breaks when its folder goes away.
   - `git branch -D <branch>`; a squash leaves the branch unmerged by ancestry, so `-d`
     refuses, and step 4 is the guard. `git push origin --delete <branch>` if origin has
     it. This also clears GitHub's "Compare & pull request" banner.
   - Sync: `git pull --ff-only` in the checkout that holds the base, if it is clean and
     no other session works in it. Otherwise the fetch is enough.
6. **Verify.** This step alone answers "is it merged?" or "is it synced?". Rerun the
   script; pass `--sha <old tip>` when the branch is gone. Done means `landed: yes`, the
   PR merged or none, no `origin/<branch>`, local base ahead 0 and behind 0, and no
   worktree that holds the branch.
7. **Check the deploy or production run,** if the repo has one. `<sha>` is the landing
   commit (the squash commit, or the PR's merge commit):
   - Commit status of the merge commit (Vercel reports here):
     `gh api repos/<owner>/<repo>/commits/<sha>/status --jq '.statuses[]|"\(.context) \(.state)"'`
   - CI on the base: `gh run list --branch <base> --limit 3`.
   - Deployments (GitHub Pages): `gh api "repos/<owner>/<repo>/deployments?sha=<sha>"`,
     then its `statuses_url` for `environment_url`.
   - Wait for success, then load the live URL: `curl -s -o /dev/null -w '%{http_code}'`,
     and check one thing the change added. Use the repo's smoke test if it has one.
   - Never deploy by hand (`vercel --prod`) unless Leo asked for the deploy itself. A
     scheduled job (firehose's 07:00 judge) cannot be checked now: give its next run time.

## Report

```
Landed `<branch>` on `<base>` as `<sha> <subject>` (<PR url | local squash>).
Checks: <name result, ... | no CI>. Tests: <command: count passed>.
Cleanup: `<branch>` deleted locally and on origin; worktree <path> removed | kept: <reason>.
main: local and origin at <sha> | <what is not synced and why>.
Deploy: <context state, URL HTTP code | none in this repo | next run HH:MM>.
Next: <one line>.
```

For a stop: the blocking fact as the script printed it, the options, and a recommendation.

## Rules

- Never force-push, never `--admin`, never rewrite `main`.
- One branch per run. Land several only when Leo names them ("merge 123 and 124").
- Touch no other branch or worktree. A cleanup of every stale branch and worktree is its
  own task: list the candidates with the script's tags, and get Leo's yes first.
- `handoff` pushes a branch so another device can continue, and never merges. This skill
  starts where the target is `main` (or another named branch).
