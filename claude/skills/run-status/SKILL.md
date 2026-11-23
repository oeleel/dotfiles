---
name: run-status
description: Report on the work that runs right now - this session's agents, other Claude sessions, NAH sprints, the launchd daily run, CI - with what each builds, progress as counts, an ETA with its basis, what it waits on, whether anything hangs, and where to watch it; on request, tell Leo once when it finishes. Use whenever Leo asks "how is the run going", "how long until it is finished", "how close are we", "what are we waiting on", "is anything hanging", "status update on the subagents/lanes", "what is being built right now", "is it still running", "is it done yet", "check hardening progress", "where can I watch the run", or "tell me when hardening finishes". A bare "what's the status" while something runs belongs here; with nothing running, use recap. Not for this session's intent and to-do (recap), driving Herdr panes (herdr), or a full NAH sprint briefing (nah-sprint-overview).
---

# /run-status - what runs, how far, when it ends, is it stuck

Leo asks this while long work runs: a daily collection, a NAH hardening round, a fan-out of
agents. The answer exists so Leo can choose in under a minute: wait, step in, or walk away.
Status answers fail in five ways: they describe an agent from the outside without looking in,
give an ETA with no basis or in UTC, call a quiet run healthy, miss what waits on Leo, and
stream progress after Leo asked only for the end. Each step below guards against one of these.

Optional argument: a target (`/run-status hardening`, `/run-status the daily run`) or a
request to be told (`/run-status tell me when s5b finishes`).

## Procedure

1. **Take a snapshot.** From the repo, run
   `python3 ~/.claude/skills/run-status/scripts/run_status.py snapshot` (read-only, about 2 s;
   `--repo PATH` adds a repo). It prints one entry per run, each with a key for `wait`:
   - agents of this session: running ones with tool calls so far, the last call and the last
     write; finished ones with their report, or the last text when they died (a usage limit);
   - other live Claude sessions, busy ones first, with the last prompt and the last words
     (an idle session often ended its turn with a question for Leo);
   - NAH sprints in every checkout of the repo: tasks done of total, in progress, blocked,
     NAH's forecast and frontier, and whether the stage session is live;
   - the launchd daily run: state, the newest step lines (UTC), the run record's stages, how
     long the last 5 runs took, and while it runs, the end time at their median.

   `HANG?` marks a run that says it works but wrote nothing for 15 minutes. The snapshot
   does not cover these; check them yourself when the question is about them:
   - your own background Bash commands: read the tail of the output file that the launch
     reported; Leo sees them in `/tasks`;
   - CI and PRs: `gh run list --limit 3`, `gh pr checks <n>`;
   - Herdr panes: the herdr skill (`hc ls --json`; `blocked` means it waits on input).
2. **Look inside before you describe.** Keep only the runs that Leo's question is about. For
   each, take what it builds from the snapshot (agent description, task intent, stage, last
   prompt). Get progress as a count with a denominator from the run's own record: the log,
   the output file, `nah <sprint>`, the run record, `git log` on the agent's branch. When you
   infer what an agent does from outside, say that it is an inference.
3. **Give an ETA with its basis.** Use the first basis that exists:
   - the run's own forecast: the `nah forecast` line, or the daily run's `eta:` line;
   - a measured rate: `run_status.py eta --done <done> --left <left> --since <ISO start>`.
     Run it a second time with the count done since the start of a recent window (the last
     15 to 30 minutes) and the same `--left`. When the two rates differ, give the range.
   - no count at all: say there is no basis, and give the time of the next check instead.

   Give times in local time with the zone; logs and transcripts store UTC. Call the result an
   estimate, and name what it leaves out (a later hardening round, the next stage, a usage
   limit reset).
4. **Name what it waits on, and check for hangs.** Each wait is on me (the agent's next step),
   on Leo (a `blocked:` or `waits on Leo` line, an attestation, a question in a pane), or
   external (CI, a person, a usage limit reset). A hang has evidence: a `HANG?` flag, a stage
   session that is not live while a task is in progress, a finished agent whose last words
   are an error. Before you say a run hangs, check one more source: the log tail, `ps`, or
   the pane. Silence is a reason to look, never proof.
5. **Say where to watch.** Copy the run's `watch:` line as a command Leo can paste, and name
   where the result lands (the run record, the page, the PR).
6. **Tell Leo when it finishes,** only when Leo asks.
   - Agents and background commands of this session need no watcher: the harness wakes you
     when each ends. Say that, and arm nothing.
   - Anything else: start `run_status.py wait <key>` as a Bash command with
     `run_in_background`. It polls every 30 s and exits once with one line: `DONE`,
     `NEEDS_LEO` (a new blocked or waits-on-Leo line), `SILENT` (the hang rule), `GONE`, or
     `TIMED_OUT` after 12 h. A run must stay idle for 2 minutes before `DONE`, so a NAH
     handoff from one stage session to the next does not end the watch.
   - CI: `gh run watch <id> --exit-status` as the background command.
   - When the wait exits, check before you report: a NAH `DONE` can be a handoff to a stage
     that has not started yet. If open tasks remain and a new stage session starts, arm the
     wait again and say nothing. Then report once. If the PushNotification tool exists and
     Leo may be away, also push that one line.
   - Use Monitor only when Leo asks for each event ("tell me every time a task finishes"). It
     expires after at most 30 minutes, so arm it again on expiry.

## Format

Answer only what Leo asked. "Is it done yet" gets one line. A full status uses this shape:

```
<One or two sentences: what runs, healthy or not, and when it ends or how it ended.>

## What runs
1. <What it builds> (`<key>`) - <N of M done> (measured), <state>, last write <age>.

## When it ends
<HH:MM ZONE, or HH:MM to HH:MM> - estimate. Basis: <forecast, or the eta output>. Leaves
out: <what is not counted>.

## What it waits on
1. <Item> - waits on <me | you: the decision | external: who or what>.

## Is anything hanging
No - checked <the sources>. | <Run> - <the evidence>; I suggest <the action>.

Watch: `<command>`. Result: <where it lands>.
```

Leave out a section that has nothing in it.

## Rules

- **Read-only.** A status check starts, stops, restarts, and resumes nothing. Propose the
  action, and wait for Leo. The only process it starts is the `wait` that Leo asked for.
- **One message per outcome.** After "tell me when", report the end and anything that needs
  Leo, nothing in between. Leo had to repeat "tell me when hardening is done" after an
  agent posted each task change (session dabb5e14, 2026-11-06).
- **Counts, not adjectives.** "240 of 917 rows", never "good progress". Label each number:
  measured (read from a record), derived (computed, with the arithmetic shown), or estimate.
- **Never predict a running agent's result.** Report its last call and its last write.
- **Short.** About 15 lines, unless Leo asks for detail.
- **Hang rule constants** live in `scripts/run_status.py`: `SILENT` (15 min) with its reason,
  `SETTLE` (2 min), `POLL_SECONDS` (30 s) and `MAX_WAIT_HOURS` (12 h).
