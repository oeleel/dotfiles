---
name: meeting-pack
description: Prepare Leo for an upcoming meeting - a report page built from the record (what was asked, what was delivered, a proof of concept, results, decisions needed, next steps) with a linked quick summary on top, checked headless and opened for Leo, then talking points and a time plan in chat, and a local-only demo script on request. Use whenever Leo is about to meet the advisor (epiForecasting, weekly), Wiley (N2O, Firehose) or a class team (cs4501), or says "weekly report", "report page for the meeting", "the deliverable for the meeting", "quick summary" or "rundown", "talking points", "need to knows", "what do I tell <name>", "speaker notes", "I have 15 minutes with <name>", "demo script", or "open what I need for the meeting", even without the word "meeting". After the meeting (transcript to actions and todo), use meeting-to-actions. To audit a list of asks (rubric, PRD, email) against what exists, use coverage-audit. For this session's own status, use recap.
---

# /meeting-pack - the page, the quick summary, the talking points

Leo walks into a meeting with one page to show and a plan for the time. The page reports
the week: "what i've done in the past week, what was asked of me, what i delivered, some
sort of interactable or proof of concept work, and then next steps" (Leo, 2026-10-01).
Packs fail in five ways, and the steps below guard against each one: the page lists every
decision instead of the week, a claim has no proof, the page has too much text, a link
404s during the meeting, and the agent fills a thin record with guesses.

Optional argument: who, when, and how long (`/meeting-pack aniruddha thursday 30 min`).
Do only the parts Leo asks for. "Talking points" alone is steps 1-3 and 8. "Open what I
need" is: find the latest page and notes, open them, and list them.

## The page depends on the meeting

| Meeting | Page | Where it lives |
|---|---|---|
| Advisor, epiForecasting (weekly) | The repo's report system: `documentation/reports/YYYY-MM-DD/report.yaml`, built by `scripts/reports/build_report.py`. Section kinds and marks: `documentation/reports/README.md` | Committed with the rebuilt index, served on GitHub Pages |
| Wiley, N2O (Firehose) | Load the `framework-page` and `diagram` skills and follow them. Start from the previous Wiley page of the same type (rule 11; Firehose: `firehose-status.html`), else from `spec-shell/` | Next to the previous Wiley page |
| Class team (cs4501) or other school work | Usually no page: the product is the demo. If Leo asks for one, copy epiForecasting's `documentation/reports/_template/` and build with its builder and `--reports-dir` | Outside the shared repo, unless Leo says to commit it |

Leo accepted the epiForecasting shell over seven weekly reports (shadcn look, square
corners, precompiled Tailwind inlined, desktop only) and asked for one "standardized design
language and layout for all of them". N2O pages follow Wiley's rules, which live in
framework-page and diagram; do not restate them here.

## Procedure

1. **Locate the meeting.** Run `date`. Name the attendee, the date, and the length. If the
   length is unknown, use the last known length and say so: advisor 30 min, Wiley 15 min,
   class deep dive 12 min. Read the repo's `AGENTS.md` or `CLAUDE.md` for its conventions.
2. **Pull the record.** Run
   `python3 ~/.claude/skills/meeting-pack/scripts/record.py [--since YYYY-MM-DD]`. It prints
   the window (from the previous report), the meeting notes (one tally line per checkbox
   section, or each numbered ask), commits by type with GitHub links and pushed state,
   result files, the test command, the Pages base, and the gaps. A flooded window (Firehose:
   1,183 commits, 870 of them `map:` bot commits) lists only feat, fix, perf and refactor.
   Then:
   - Read the newest notes file in full: it holds the last meeting's asks. Firehose keeps
     them in `context/meetings/`.
   - Run the test command and note the count.
   - Read the result files of the window for the numbers.
3. **Map each ask to its proof.** Give each ask a status: done, partly, not started,
   blocked (on whom), or dropped (by whom). Attach its proof: a commit, a file, a run
   output, or a test count, each as a link. An ask without proof is not done. Work outside
   the asks goes under "also delivered". If the record cannot support a line, write the
   gap on the page as `[Not in the record: <what>]` and never fill it.
4. **Write the page** in the fixed order below. Copy the previous page of the same venue,
   keep its section ids so weeks compare, and replace the content. The order is fixed, so
   state it in one line and build; it needs no new agreement.
5. **Check it headless.** Build it, then run both checks until they are clean:
   - `python3 ~/.claude/skills/meeting-pack/scripts/check_links.py <page> --summary quick`
     (anchors, files, a link on every summary line, no em dash).
   - `node ~/.claude/skills/diagram/shoot.mjs <page> <outdir> 1440 <free port>`: it must
     report `pageOverflow: 0` and `errors: []`. N2O pages also need 860 wide and `DARK=1`,
     as framework-page says.

   Open every screenshot and look for wrapped labels, empty panels, and blocks of prose.
6. **Publish a shared page.** Commit it on the current branch. A push to `main` needs Leo's
   approval (git rules). After the push, wait until
   `check_links.py <page> --remote` or `curl -s -o /dev/null -w '%{http_code}' <url>`
   gives 200. Pages deploys about 40 s after a push; on 2026-11-05 Leo clicked early and
   got a 404.
7. **Open it for Leo.** Run plain `open <path or URL>` so it lands in Dia, then confirm the
   frontmost app (memory note `open-pages-in-dia.md`). Give the full path and the URL.
8. **Give the talking points in chat** (format below). They are private: they never go on
   the page.
9. **Write a demo script or prep notes only on request, and keep them local.** Use the
   repo's gitignored notes folder (prove it with `git check-ignore -v <file>`), else
   `../<repo>-private/`. Never commit them (Leo, 2026-11-12: "don't commit keep on local").

## Page format

The same order in every venue:

| # | Section (id) | Content | Budget |
|---|---|---|---|
| 0 | Quick summary (`quick`) | One line per result in few words: sign-colored numbers, a status badge, and a link to its proof. Then at most 4 stat tiles | About 180 words, at most 8 lines |
| 1 | What was asked (`asked`) | Each ask from the last meeting, with its date and status | About 100 words |
| 2 | What was delivered (`delivered`) | Item, where, and a proof link | About 100 words |
| 3 | Proof of concept (`proof`) | One interactive or worked example that the attendee can follow without running anything: a viewer, a stepper, a side-by-side run in one format | Detail in tabs or collapsed |
| 4 | Results (`results`) | Numbers with their source; caveats marked amber | A table |
| 5 | Decisions needed (`decisions`) | Only what needs the attendee's input, one question each | At most 5 |
| 6 | Next steps (`next`) | Numbered | At most 5 |
| A | Reproduce (`reproduce`) | The commands | Collapsed |

The budgets are measured: Leo called the 2026-11-19 report "too much text" at 4,366
visible words. The version Leo accepted has 2,835, with the quick summary at 179, "asked"
at 75 and "delivered" at 83, and most of the rest inside tabs.

- **Neutral voice.** The attendee reads the page after the meeting. Write "questions yet to
  be answered", never "questions for my advisor" (Leo, 2026-10-01).
- **The week, not the process.** No decision ids, no list of every change, no file paths in
  the summary.
- **Every fact links to its record.** Every quick-summary line opens its proof (Leo,
  2026-11-19: "create a link for each of the items in the quick summary").
- **Color carries meaning only:** gain green, loss red, caveat amber. In the epiForecasting
  builder these are `[[+ ]]`, `[[- ]]` and `[[! ]]`.
- **Name the limits on the page** before the attendee finds them.
- **In Firehose, every number carries its evidence label** (repo `CLAUDE.md`).

## Talking points format (chat)

```
## Opening line (30 s)
"<the result in two sentences>. <the one decision you need>."

## Time plan (<N> min)
| Time | Block | Show | Point |
|---|---|---|---|
| 0:00-0:30 | Opening | top of the page | ... |
| ... | <one block per page section, in page order> | <#section link> | ... |
| <N-3>:00-<N>:00 | Decisions | #decisions | ask, then stop talking |
If time is short: cut <block>; keep <block> and the decisions.

## Need-to-knows
- <a number in plain words> - <its source>

## Get a decision on
1. <question> - <your recommendation in one line>

## Where <name> will push
| Question | Answer |
|---|---|

## Say first
- <a caveat or limit>
```

- **Time plan.** Lead with the result. Give about half the time to the main finding, and
  pause there for a reaction. Keep the last 15-20% for the decisions and never cut it. Leo
  accepted this shape on 2026-09-28 (15 min with Wiley) and 2026-11-05 (30 min, advisor).
  If the page order differs from the talk track, offer to reorder the page (Leo,
  2026-09-28: "build the page to match this order").
- **Define a term the first time** you use it. On 2026-10-29 Leo had to ask "what is the
  quantiles thing you are mentioning".
- **Every number comes from step 2, with its source.** On 2026-09-28 the talk track gave a
  $180 X API cost that was an estimate shown as fact; Leo caught it before the meeting.

## Rules

- **Record first, never memory.** A number or status that step 2 did not produce does not
  go on the page or into the talking points.
- **Report what you checked:** the test count, the check results, the screenshot folder,
  and whether the live link gave 200.
- **Do not push `main`, send the page, or message the attendee** without Leo's approval.
