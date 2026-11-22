---
name: meeting-to-actions
description: Turn a meeting transcript into confirmed understanding, next steps, a todo and finished work - save the transcript, repeat back what was agreed, split the actions into what the agent can do now, what Leo decides or does, and what waits on another person (the advisor, Wiley, a teammate), write the note and the todo where the repo keeps them, then run the agent items and tick each one with proof. Use whenever Leo pastes a transcript (Granola, Teams, Loom) or meeting notes and says "process this transcript", "ingest transcript", "set forth action items", "extract next steps", "make a todo list from this", "new todolist for next week", or "repeat back what we're building", even without the word "meeting". Also for an existing meeting todo: "get started on the todos", "check off items as we finish", "how far can you get without my input". Not for preparing the next meeting (meeting-pack), mapping a full list of asks against evidence (coverage-audit), or a recap of this session (recap).
---

# /meeting-to-actions - transcript to understanding, actions, todo, done

Leo meets an advisor, Wiley or a team, pastes the transcript, and wants the work moving the
same day. Past sessions failed in six ways. The agent guessed the meeting date and Leo had
to say "it is tomorrow". It built work nobody asked for ("I don't know if I ever mentioned
anything about actions"). It tried to commit notes that Leo keeps private. It read "Me" as
Leo when Wiley had recorded the call. It put changed words inside quote marks. It forgot to
tick the todo, and Leo had to remind it twice in one session. Each step below guards
against one of these.

Script: `~/.claude/skills/meeting-to-actions/scripts/meeting.py` (`--help` lists commands).

## Procedure - a new transcript

1. **Locate.** Run `date`. Run `meeting.py records <repo>`. It prints the repo's meeting
   rules, ignore rules, meeting folders (tracked or local only), recent todo files, and the
   `<repo>-private` sibling with its README. Read every rule file it names before you
   write. A repo rule beats this skill.
2. **Capture.** Run `meeting.py paste --list` to see each paste and the words Leo typed
   after it ("sept 9", "aug 27"). Pick the transcript and save it verbatim to a local-only
   path as `YYYY-MM-DD-<who>-transcript.txt` (see "Where things go"):
   `meeting.py paste --index <n> --out <path>`. The script refuses a path that git could
   publish. Then run `meeting.py profile <path>`. Do not read the saved file back: the
   paste is already in the conversation.
3. **Fix the facts first.**
   - Speakers: map every generic label (`Me`, `Them`, `You`, `Speaker 1`) to a person, with
     evidence. `Me` is whoever ran Granola, which is not always Leo. On 2026-11-20 it was
     Wiley.
   - Meeting date: the header, Leo's words, or the paste time, in that order. Say which.
   - Next meeting: an absolute date and time. Take it from the transcript, or read Google
     Calendar if the transcript is vague. Count the working hours until then from `date`.
   - End of the paste: if `profile` reports lines after the last goodbye, check them.
4. **Read the context.** Read the newest earlier meeting note and the last todo; their open
   items are carry-over candidates. Read the other pastes (Teams messages, older
   transcripts) and the files Leo named. Open older notes only when the transcript refers
   back to them.
5. **Repeat back** in the format below. Keep it short. The detail goes in the files.
6. **Extract the actions.** Make each one a single step with a done-when check. Cover every
   ask, advice and carry-over, including small ones (a practice rule, an admin item). A trial
   gave 5 coarse items where Leo's accepted todo had 28 steps in 9 workstreams. Aim for
   2 to 5 steps per workstream. Give each one an owner and a source:
   - **agent:** needs nothing from a person (code, runs, analysis, drafts of messages).
   - **Leo:** a decision (give the options and a recommendation) or an act only Leo can do
     (send a message, log in with Duo, attend).
   - **waits on <person>:** what they owe, and when they said it would arrive.
   - Source: the transcript (who asked), a carry-over, or "(added)" for your own idea. Keep
     additions few. When only part of a task waits on someone, cut it there. The rest stays
     agent work (the parallelize skill, wait 6).
7. **Write the files.** Write the meeting note in the repo's own format and the todo in the
   format below. Then run `meeting.py quotes <note> <transcript> [<pages Leo gave>] [<earlier todo or note>]`. Add
   the earlier file when the note quotes it.
   Fix every miss: copy the exact words, mark a cut with `...`, or drop the quote marks.
8. **Gate.** Leo asks for the repeat-back so a wrong reading is caught before agents build
   on it. So stop here and wait for "proceed" or corrections, unless one of these is true:
   - Leo already said to start ("and start on it", "get as far as you can").
   - Leo cannot answer: remote control from the phone, or Leo said they will be away.

   Then start step 9 at once with the items that no "Please confirm" point changes. In
   remote control, put the repeat-back at the top of the todo as "Understanding
   (unconfirmed)", commit at milestones, and end with what needs Leo's decision.
9. **Run** as in the next section.

## Procedure - working the todo (also a later session)

1. Run `meeting.py todo <file>`. It lists open items by owner with line numbers. For "how
   far can you get without me", answer with the agent items in order and the first point
   that needs Leo. Then start.
2. Load the parallelize skill. State the estimate in one line and fan out the agent items.
   Put the items the next meeting needs first.
3. **Tick each item the moment it finishes.** Change `[ ]` to `[x]` and append the proof:
   a commit sha, a test count, a job id, a file path, or the number found. Leo works from
   this list, often in a pane next to the session. A partial item stays `[ ]` with
   "Partly: <done>; left: <rest>". Before you tick older items ("anything done that wasn't
   checked"), check each one against git, files or job state. Never tick from memory.
4. An item that needs Leo's hands (VPN, password, Duo) stops alone. Give Leo the exact
   command, such as `! ssh-copy-id <id>@<host>`, and keep the other lanes running.
5. Ask before anything that sends, spends (paid API, cluster allocation), pushes to `main`,
   or deletes. Draft messages to the advisor or Wiley in the note. Leo sends them.

## Where things go

| What | First match wins | Why |
|---|---|---|
| Meeting note | The repo's rules (Firehose: `context/CLAUDE.md`). Then the newest earlier note's folder, naming and layout. Then `<repo>-private/meetings/` (proposed). | A rule in the repo carries Leo's decision about who reads it. |
| Todo | The folder of earlier todos, same naming (`todo-week-<Monday>.md`). Then a local-only meeting folder. Then `<repo>-private/`. | It holds Leo's own items. The Stop hook commits stray files on feature branches. |
| Transcript | Next to earlier saved transcripts. Then a local-only meeting folder. Then `<repo>-private/transcripts/`. Never tracked. | It can hold client or personal detail. Later meetings use it as context and for the quote check. |

When two places both claim to hold the record, follow the rule file and list the conflict
for Leo. Todoist and Calendar are outward-facing. You can propose Todoist tasks for Leo's
dated items. Write them only after a clear yes, and never create events.

If the session runs in Herdr, offer the todo in a split pane (herdr skill, A1:
`hc_pane.sh open todo -- yazi <todo>`). Open it when Leo asks for "a visual as I work".

## Format - repeat-back (chat)

```
## What I understood - <who>, <meeting date> (<how the date was found>)
Goal for <next meeting, YYYY-MM-DD HH:MM>: <one sentence>. <N> working hours from now.
1. <Decision or ask> - <who> (<"exact short quote"> where the words matter).
Speakers: <label> = <person> (<evidence>).

## Please confirm or correct
1. <A point you are not sure of: a garbled name, an inferred ask, a date, a speaker.>

## Actions - <a> agent, <b> Leo, <c> waiting; full list: <todo path>
Agent, can start now: <items, short>.
Leo: <decide X: options, recommendation> | <do Y>.
Waiting on <person>: <thing>, expected <date>.
Files: <note path>, <todo path>, <transcript path> (local only | tracked, not pushed).
```

## Format - todo file

```
# Todo - week of <YYYY-MM-DD>

Source: <who> meeting transcript, <YYYY-MM-DD>. Next meeting: **<YYYY-MM-DD HH:MM>**.
Goal for the next meeting: **<one line>**.

Mark a finished item with `[x]` and its proof.

## 1. <Workstream, in priority order> (carry-over)
- [ ] <One verifiable step> (added)
- [ ] **Leo:** <decision or act>
- [x] <Step> (<proof>)

## <N>. Waiting on others
- [ ] <Person>: <what they owe>, expected <date>
```

`meeting.py todo` reads this layout. An item that starts with "Leo" or "Ask" belongs to
Leo. A "Waiting" section belongs to others. Everything else is agent work.

## Rules

- **Trace every item to its source.** Do not build past what was asked. Leo corrected
  this on 2026-10-01.
- **An ask is not a decision.** A request from Wiley or the advisor stays "asked" until Leo
  accepts it. Use the repo's label set when it has one (Firehose: approved, asked,
  proposed, open).
- **Absolute dates only.** "Next Thursday" becomes `2026-11-26` from `date`.
- **Quotes are exact** (N2O rule 5). `meeting.py quotes` must pass before you report.
- **Write shared files for every reader.** In a file that others can read, use "Open
  questions", never "Questions for the advisor" (Leo, 2026-10-01).
- **Keep sensitive detail out of tracked files.** This covers client names, prices and
  personal matters. Follow the repo's care rules (N2O: `~/N2O/notes/README.md`). Ask Leo
  before you record new client-specific detail.
- **Short chat.** Leo rejects long write-ups. The chat carries the repeat-back and counts.
  The files carry the rest.
