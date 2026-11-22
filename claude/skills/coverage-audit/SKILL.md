---
name: coverage-audit
description: Check a full list of asks - a meeting transcript, a Loom, a rubric, assignment instructions, a PRD, a review or red-team report, an email - against what exists. One row per ask in the source's own words, each marked covered, partial, missing, unverified or n/a with evidence that was opened or run, then what fills each gap and what it waits on. Use whenever Leo asks "does it address all his asks", "does this satisfy Wiley's ask", "are all our bases covered", "map the asks against what we have", "did you check it against the rubric", "would it check all the boxes", "does the document cover everything they sent", "cross reference it with what we have done", "does this count as a complete beta per the PRD", "does it match the deck", or "list everything Wiley asked for", even without the word audit. Not for one session's progress (recap) or for turning a fresh meeting into actions and todos (meeting-to-actions).
---

# /coverage-audit - every ask against what exists

Leo asks this before a deadline or a review: Wiley's asks before a demo, a rubric before a
submission, a red-team report before the response. Audits fail in four ways. They check a
summary of the source and call it complete. They paraphrase the asks, so a requirement
gets lost. They mark an ask covered from a claim that nobody checked. They bury the
decisions that Leo must make. Each step below guards against one of these.

Optional argument: the source and the target (`/coverage-audit the rubric against the deck`).

## Procedure

1. **Get the source itself.** Make a scratch folder in the session scratchpad.
   - Pasted in this session: run
     `python3 ~/.claude/skills/coverage-audit/scripts/audit.py source <scratch>`. It saves
     each paste word for word as `paste-<n>.txt` and prints an index. Pick the source. Run
     it even when you think nothing was pasted: a compaction hides old pastes (cs4501,
     2026-11-05: the agent said it had no rubric, but Leo had pasted it 7 hours before).
   - A file or a doc: read all of it (`pdftotext -layout` for a PDF). Save the text in the
     scratch folder. Transcribe images to a text file.
   - Not found: say so in one line and ask for it. A meeting note, an issue that sums up a
     report, or a PRD line about a rubric is a proxy, and proxies drop asks (2026-11-17:
     issue #133 left out a red-team gap and a recommendation). Use a proxy only when Leo
     cannot answer (remote session), and title the table "against <proxy>, not the source".
   - Several sources (a spec and its update, a Loom and a call): give each a letter and
     number its asks (L1, M3). When a later source changes an ask, keep the later words
     and cite both.
   - Transcripts: check who speaks. In a Granola transcript "Me" is the person who
     recorded. Quote only the asker's lines.
2. **List every ask in the source's words.** The Ask cell quotes the shortest span that
   carries the requirement, with its place (timestamp, row, section). Use `...` to skip
   filler inside a quote.
   - Preferences, constraints, and quality bars are asks too ("I don't know that we need
     that automatic tagging", "within the 8-minute limit", "at the quality of the current
     Prism thing"). A target can break them.
   - An ask that the source repeats gets one row. Quote the clearest instance.
   - Split an ask into lettered rows (5a, 5b) when its parts can get different statuses: a
     list of topics, sources or metrics, or "X and Y" where each part is checked alone.
     Keep it whole when the parts only make sense together ("which LLM do we use inside
     which harness").
   - Rubric: the bar is the top level of each row, unless Leo names another. Read every
     level, because a lower level can name a requirement that the top level omits
     (cs4501 alpha: "issue burn-down" is only in level 2). Give each named requirement a row,
     and add one line under the headline with the likely level and the weight per category.
   - Talk that asks for nothing here goes in one "Left out:" line with the reason, so
     the cut is visible.
3. **Name the target** in the "Checked against:" line, in backticks: the repo path and
   commit, the file, the deck. If Leo asks about two targets ("the system and the status
   page"), give each its own Status column.
4. **Find the evidence for each row.** Open the file, read the slide, run the test, load
   the page. Put each file, commit, command, and link in backticks. A slide, page, or
   section number points into the target. Cite a line number only from a line you printed.
   - A claim is not evidence: a decision record, a commit message, a status page, an
     agent report, a teammate's message. Its row is unverified until you open or run the
     thing it describes.
   - A missing row names where you searched (folders and grep terms).
   - If the target works against an ask (it asks again a question the source answered,
     or it does what the source rejected), mark it missing and start with "conflicts:".
   - Run greps and counts as code. To read many files, batch the rows into a few Explore
     agents.
5. **Check the table.** Write both tables to `<scratch>/audit.md`, then run
   `python3 ~/.claude/skills/coverage-audit/scripts/audit.py check <scratch>/audit.md --source <scratch>/paste-1.txt --root <repo>`.
   Repeat `--source` and `--root` for several. Pass the real repo as a root, so commit ids resolve (a file copy has no git history). It fails on a status outside the five, a
   quote that is not word for word in the source, a path, line or commit that does not
   exist, a covered row that points at nothing, an open row with no gap row, a missing or
   wrong target, and a headline whose counts do not match the table. Fix and rerun until
   the result is ok. It cannot tell whether a cited line says what you claim.
6. **List what fills each gap** (every partial, missing, and unverified row): the work,
   what it waits on, and its size in agents, hours, and dollars. Put every decision that
   Leo must make in one numbered "Your call" block, so Leo can answer them all at once and
   the rest can run without Leo.
   Split a gap that waits on a choice: the part that works for any answer (the mechanism, a rough
   mock) waits on `me`. Only the part that the answer changes waits on `you`. In the 2026-11-22
   Firehose case, Leo started every gap overnight in the next prompt, including the one marked `you`.
7. **Report, then stop.** Do not start the gaps. When Leo says go, load the `parallelize`
   skill (and `overnight` if Leo is leaving). Start every gap that waits on `me`, and the
   part of each other gap that does not need the answer.

## Statuses

| Status | Meaning |
|---|---|
| covered | Evidence that you opened or ran this session meets every word of the ask, including dates, counts, and "measurable". |
| partial | Part of the ask is met. The evidence says which part is not. A rubric row below the bar. |
| missing | Nothing meets it after a search, or the target conflicts with it. |
| unverified | Only a claim says it is met. The gap is a check, not a build. |
| n/a | The ask needs no work here (a permission, background, another project). Say why. |

## Format

```
<Yes | No | Mostly>. <N> asks: <a> covered, <b> partial, <c> missing, <d> unverified, <e> n/a.
Source: <what, date, `file`>. Checked against: <`repo or file`, branch, `sha`>.

## <Who>'s asks against <target>
| # | Ask (source words) | Status | Evidence |
|---|---|---|---|
| 3 | "if I only tracked 20% of the sources, which 20 would be the best" (call, 11-20) | missing | No ranking exists. Searched `research/`, `context/` for "backtest", "20%". |

Left out: <talk that asks for nothing here, and why>.

## What fills the gaps
| # | What fills it | Waits on | Size |
|---|---|---|---|
| 3 | A script over the traces: first sighting per source, then the smallest set that sees most hits early. | me | 1 agent, about 1 h, $0 |

Your call:
1. <The decision and my recommendation> (rows 5d, 6b).
Next: say go and I start rows <ids> in parallel.
```

"Waits on" is `me` (I can start now), `you: <the decision>`, or `external: <who or what>`.

## When the audit also needs a file

Chat is the default, because Leo reads tables there. Write a file when the table has more
than about 30 rows, when Leo asks to keep it, or when the gap work starts (the agents need
one shared list). Over 30 rows, chat shows the headline, the rows that are not covered, and
the gaps table, and the file holds every row. Put it at
`docs/audits/<YYYY-MM-DD>-<source-slug>.md` in the repo that the asks are about. Use the
repo's own home if it has one (Firehose: `context/`, per `context/CLAUDE.md`). For a shared
repo where the audit is private (a course team repo, a client repo), use the
`<repo>-private` sibling folder.

## Rules

- **Source words.** A summary is where requirements get lost. On 2026-11-11 the meeting
  notes recorded decision D64, but only the Loom transcript held Wiley's lean against
  automatic tags.
- **Proof or it is not covered.** Say what you did not check ("test files confirmed by
  name, not run").
- **Every ask gets a row.** Do not merge two different asks to shorten the table.
- **Short cells.** One plain clause and its reference. Leo stopped a long answer on
  2026-11-12, and asked only for what is done, what is not done, and what is unsure.
- **Read-only until go.** Fix nothing during the audit. Write only the scratch files and
  the audit file.
- **Labels.** Follow the repo's evidence rules for numbers that feed a decision (Firehose:
  `measured`, `derived`, `policy`, and the other labels in its CLAUDE.md).
