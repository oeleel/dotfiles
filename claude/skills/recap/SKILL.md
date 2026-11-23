---
name: recap
description: Recap the current session - the original intent and how it changed, what is done with proof, and what still needs to be done, each open item tagged with what it waits on. Use whenever Leo asks "recap", "where are we", "what's the status", "what was the original intent/purpose of this session", "what has been done and what still needs to be done", "what did we do overnight", "what happened while I was gone", "what's left", "catch me up", or "what do I need to do next", even without the word "recap". Session-scoped; for a full NAH project or sprint briefing use nah-project-overview or nah-sprint-overview. For how a job that runs right now is going (progress, ETA, hangs, tell me when done), use run-status.
---

# /recap - purpose, done, still to do

Leo asks for this after a break, after an overnight run, or when a session has drifted. The
answer exists so Leo can pick the next move in under a minute. Recaps fail in three ways:
they lose the original ask after compaction, they report planned work as done, and they
bury the items that wait on Leo. Each step below guards against one of these.

Optional argument: a window or a focus (`/recap overnight`, `/recap the graph work`), or a
session id prefix to recap another tab's session.

## Procedure

1. **Read the session's own record.** Run
   `python3 ~/.claude/skills/recap/scripts/session_log.py [session-id-prefix]`. It prints,
   in time order with local times:
   - every prompt Leo typed (`LEO:`; the first in full, the rest as head and tail),
   - the intent section of each compaction,
   - every git action of the session and its agents, with its result and commit lines,
   - test runner summaries, background-task completions, and agent reports,
   - agent, workflow, and loop calls, and messages to and from other sessions,
   - the last report before each idle gap of an hour or more, and the last report.

   Take the original intent from this output, not from memory: after a compaction, memory
   holds a summary of a summary. "Overnight" or "while I was gone" means the span after
   the matching idle gap.
2. **Collect proof of what is done.** Use read-only checks only:
   - Commits: the log's `git:` lines are this session's own. A hook rebase can change a
     commit's hash after the fact, so find the current hash by subject on the current
     branch (`git log --oneline --since="<started>" | grep -F "<subject>"`). A squash
     merge removes the subject; search the squash commit's body (`git log --grep`).
     Do not count `git log --since` output as this session's work: it also lists
     commits that a rebase rewrote or a merge brought in. Tools such as nah and the Stop
     hook commit without a `git:` line; look for their commits by subject.
   - State: `git status -sb` in each repo the session touched, for uncommitted files and
     ahead/behind counts. On a checkout that other sessions share, also count this
     session's own unpushed commits.
   - Tests: the log's `tests:` and `background:` lines, with their times. A custom check
     that prints no runner summary appears only in its command's output or report. A
     test result older than the last code change is "not rerun since".
   - Agents and loops: a background `launched:` line with no matching `background:`
     completion may still run; check before you say so (a foreground agent finishes
     inline and gets no completion line). A `CronCreate` with no `CronDelete` is a loop
     that may still fire. Never predict the result of a running agent.
   - NAH sprints: `.nah/active/<sprint>/tasks.jsonl` and `events.jsonl` hold task state
     and attestations.
3. **Sort each ask** from step 1 into done (with proof), partly done, not started, dropped
   (Leo changed course; cite the later prompt), or blocked.
4. **Write the recap** in the format below, then stop. Do not start the open items. Leo
   usually answers with "proceed" or a pick.

## Format

```
## Purpose of this session
<The original ask in one or two sentences, close to Leo's words, with the date.>
<If the purpose changed: "Then, <time>: <the new ask>." One line per real change of
direction. Skip small follow-ups.>

## What is done
1. <Result> - <proof: commit sha, test count, file path, screenshot path>.
State: on `<branch>`, <N files uncommitted | all committed>, <N ahead (K from this
session), M behind origin | in sync>.

## What still needs to be done
1. <Item> - waits on <me | you: the decision or approval | external: the agent, CI run, or
   person>.

Next: <the items I can start now without Leo>. Your call: <item numbers, each with the
decision in a few words>.
```

## Rules

- **Proof or it is not done.** An item without a commit, test result, file, or output that
  you checked goes under "still needs to be done", or carries "done, not verified".
- **One line per item, about 8 items per section.** Group the rest by workstream. Leo asks
  for detail when needed; a long recap hides the items that wait on Leo.
- **Concrete.** Real numbers, names, shas, and dates. Never "several tests" or "some
  progress".
- **Quote Leo** where the exact words matter: the original ask and any decision Leo made.
- **State the unknowns:** an agent still running, tests not rerun since the last change.
- **A "you" item names the decision** ("pick A or B for the verb question"), never "needs
  your input".
- **Fresh session:** if the log shows no earlier work, say so in one line. Then recap the
  repo: branch, `docs/STATUS.md` or `AGENTS.md`, recent commits, open branches.
