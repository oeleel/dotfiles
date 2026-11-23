#!/usr/bin/env python3
"""What runs now, for the run-status skill.

Read-only: it reads Claude Code's session files, NAH ledgers and the launchd job's log, and it
runs `ps`, `launchctl print`, `git worktree list` and `nah --json`. It starts, stops and writes
nothing.

  run_status.py snapshot [--repo PATH ...]
      Every run found, with its state, what it builds, its progress, the hang flag and where to
      watch it: the agents of this session, the other live Claude sessions, the NAH sprints of
      every checkout of this repo, and the launchd daily run.
  run_status.py eta --done N --left N --since ISO-TIME
      The rate of N items done since a time, and the time left and end time (local) for the rest.
  run_status.py wait KEY [--repo PATH ...] [--max-hours H]
      Poll one run from the snapshot (KEY such as nah:landscape-mvp) until it ends, needs Leo,
      or goes silent. Print one line and exit with the outcome code. Run it as a background Bash
      command: its exit wakes the session once.

Hang rule: a run whose state says it works but that wrote nothing for SILENT may hang. Each kind
of run names what counts as a write. The flag is a reason to look, never proof of a hang.

Not covered here: Herdr pane states belong to the herdr skill (`hc ls --json`). This session's
own background Bash commands and Monitors notify the session when they end, and `/tasks` lists
them. CI runs belong to `gh`.

The session defaults to $CLAUDE_CODE_SESSION_ID, which Claude Code sets in every Bash call.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from pathlib import Path

__all__ = ["Outcome", "Run", "Section", "eta_lines", "main", "snapshot", "wait_for"]

# A working Claude agent writes its transcript at every tool call and result, and Bash caps a
# foreground command at 10 minutes. The firehose judge starts a `claude -p` call every 10 to 30 s
# (measured 2026-11-16). 15 minutes is past both, so a run that says it works and writes nothing
# for that long is probably stuck or waits on input.
SILENT = timedelta(minutes=15)
# NAH hands a sprint from one stage session to the next with a short gap in which nothing works,
# so `wait` calls a run done only after it stays idle this long. Not measured; the 2026-11-06
# hardening watch used about 90 s.
SETTLE = timedelta(minutes=2)
POLL_SECONDS = 30  # local checks are cheap; the notice comes at most 30 s late
MAX_WAIT_HOURS = 12.0  # the longest daily run so far, 2026-11-21, took 8h06m
LIST_LIMIT = 8  # finished agents and idle sessions listed; the rest are counted
RUN_HISTORY = 5  # earlier daily runs whose durations give the ETA basis
STEP_LINES = 3
TEXT_CHARS = 120
WORDS_CHARS = 240  # the last words of an agent or session hold its result and its ask
TAIL_BYTES = 256_000  # read only the end of a large log or transcript
PROMPT_TAIL_BYTES = 1_000_000  # the last typed prompt can sit far back behind tool output
COMMAND_TIMEOUT = 20  # seconds for one ps, launchctl, git or nah call
REPORT_TOOL = "SubagentHandback"  # the tool a subagent calls to deliver its final report
NEEDS_LEO = ("waits on Leo", "blocked:")  # a new line with one of these prefixes ends a wait

# Messages from other agents arrive as typed text inside a wrapper tag; the text is the ask.
PEER_TAG_RE = re.compile(r"^<(?:hc|cross-session-message|agent-message)\b[^>]*>\s*")
LAUNCHCTL_FIELD_RE = re.compile(r"^\s*(state|pid|stdout path|last exit code) = (.+)$", re.M)
ETIME_RE = re.compile(r"^(?:(?:(\d+)-)?(\d+):)?(\d+):(\d+)$")


@dataclass(frozen=True, slots=True)
class LaunchdSpec:
    label: str
    step_pattern: re.Pattern[str]  # log lines that mark a step of the run
    records: Path  # one JSON record per run, with started_at, finished_at and stages
    watch: str


# The firehose daily run is Leo's only long batch job under launchd (memory note
# firehose-judge-run-worktree). Add a spec when another job needs watching.
LAUNCHD_JOBS = (
    LaunchdSpec(
        label="com.n2o.firehose.judge",
        step_pattern=re.compile(r"run-host:|calls so far|^INFO __main__: stage |placement:"),
        records=Path.home() / "N2O" / "firehose-judge" / "data" / "runs",
        watch="tail -f ~/Library/Logs/firehose-judge.log | grep --line-buffered -E "
        '"run-host|calls so far|stage |placement:"',
    ),
)


@dataclass(frozen=True, slots=True)
class Paths:
    projects: Path  # Claude Code transcripts
    sessions: Path  # one <pid>.json per live Claude Code process
    jobs: Path  # background-session state, keyed by the first 8 characters of the session id

    @classmethod
    def default(cls) -> Paths:
        root = Path.home() / ".claude"
        return cls(projects=root / "projects", sessions=root / "sessions", jobs=root / "jobs")


@dataclass(frozen=True, slots=True)
class Run:
    key: str  # what `wait` takes, such as nah:landscape-mvp
    state: str
    title: str  # what the run builds
    active: bool  # its state says it works
    last_write: datetime | None  # the newest sign of work; the hang rule reads it
    lines: tuple[str, ...] = ()
    watch: str = ""

    def silent(self, now: datetime) -> bool:
        return self.active and self.last_write is not None and now - self.last_write >= SILENT


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    runs: tuple[Run, ...]
    notes: tuple[str, ...] = ()


class Outcome(IntEnum):
    DONE = 0
    NEEDS_LEO = 2
    SILENT = 3
    GONE = 4
    TIMED_OUT = 5


PsRow = tuple[int, int, timedelta, str]  # pid, parent pid, elapsed, command


# ---------------------------------------------------------------- shared helpers


def parse_time(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def clip(text: str, limit: int) -> str:
    """One line that keeps the head and the tail: reports lead with the result and end with the
    ask, and dictated prompts often end with the actual request."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head, tail = limit * 3 // 5, limit * 2 // 5
    return f"{text[:head]} [...] {text[-tail:]}"


def mtime(path: Path | None) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) if path else None
    except FileNotFoundError:
        return None


def clock(moment: datetime, now: datetime) -> str:
    """Local time, with the date only when it is not today. Transcripts store UTC."""
    local = moment.astimezone()
    same_day = local.date() == now.astimezone().date()
    return local.strftime("%H:%M") if same_day else local.strftime("%m-%d %H:%M")


def span(delta: timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours < 48 else f"{hours // 24} days"


def age(moment: datetime | None, now: datetime) -> str:
    return "never" if moment is None else f"{span(now - moment)} ago"


def home(path: Path | str) -> str:
    return str(path).replace(str(Path.home()), "~")


def tail_lines(path: Path, limit: int = TAIL_BYTES) -> list[str]:
    """The last complete lines of a file; a large file is read from its end only."""
    with path.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        handle.seek(max(0, size - limit))
        lines = handle.read().decode(errors="replace").splitlines()
    return lines[1:] if size > limit else lines


def json_rows(lines: list[str]) -> Iterator[dict]:
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            yield row


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path} holds {type(data).__name__}, expected an object")
    return data


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_command(argv: list[str], cwd: Path | None = None) -> str:
    """Run a read-only command; a missing program or a failure raises with the command."""
    try:
        done = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=COMMAND_TIMEOUT
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"{argv[0]} is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{' '.join(argv)} gave no answer in {COMMAND_TIMEOUT} s") from error
    if done.returncode != 0:
        detail = clip(done.stderr or done.stdout, 200)
        raise RuntimeError(f"{' '.join(argv)} exited {done.returncode}: {detail}")
    return done.stdout


def transcript_for(paths: Paths, session_id: str) -> Path | None:
    matches = sorted(paths.projects.glob(f"*/{session_id}*.jsonl"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def last_prompt(transcript: Path) -> str:
    """The latest text a person or a peer agent typed into a session: what it works on."""
    found = ""
    for row in json_rows(tail_lines(transcript, PROMPT_TAIL_BYTES)):
        if row.get("type") != "user" or row.get("isMeta") or row.get("isCompactSummary"):
            continue
        content = (row.get("message") or {}).get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            continue
        text = PEER_TAG_RE.sub("", _block_text(content).strip())
        if text and not text.startswith("<"):
            found = text
    return clip(found, TEXT_CHARS)


def last_words(transcript: Path) -> str:
    """The last report or text of an agent or session: shows whether an agent reported or died,
    and whether an idle session ended its turn with a question for Leo."""
    found = ""
    for row in json_rows(tail_lines(transcript)):
        if row.get("type") != "assistant":
            continue
        for block in (row.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("text", "")).strip():
                found = "said: " + block["text"]
            elif block.get("type") == "tool_use" and block.get("name") == REPORT_TOOL:
                found = "report: " + str((block.get("input") or {}).get("message", ""))
    return clip(found, WORDS_CHARS)


# ---------------------------------------------------------------- agents of this session


def agent_run(meta_path: Path, now: datetime) -> Run:
    meta = read_json(meta_path)
    agent_id = meta_path.name.removeprefix("agent-").removesuffix(".meta.json")
    transcript = meta_path.with_name(f"agent-{agent_id}.jsonl")
    last_write = mtime(transcript)
    key, title = f"agent:{agent_id}", str(meta.get("description") or "(no description)")
    if meta.get("finished") is True:
        state = f"finished {clock(last_write, now)}" if last_write else "finished"
        words = last_words(transcript) if last_write else ""
        return Run(key, state, title, False, last_write, (words,) if words else ())
    started, calls, last_tool = _agent_progress(transcript)
    started_text = clock(started, now) if started else "?"
    lines = [f"started {started_text}, last write {age(last_write, now)}, {calls} tool calls"]
    lines += [f"last call: {last_tool}"] if last_tool else []
    return Run(key, "running", title, True, last_write, tuple(lines))


def agent_runs(paths: Paths, session_id: str, now: datetime) -> list[Run]:
    transcript = transcript_for(paths, session_id)
    if transcript is None:
        raise ValueError(f"no transcript for session {session_id!r} under {paths.projects}")
    metas = (transcript.with_suffix("") / "subagents").glob("agent-*.meta.json")
    return sorted((agent_run(meta, now) for meta in metas), key=_newest_first(now))


def agents_section(paths: Paths, session_id: str, now: datetime) -> Section:
    runs = agent_runs(paths, session_id, now)
    running = [run for run in runs if run.active]
    finished = [run for run in runs if not run.active]
    hidden = len(finished) - LIST_LIMIT
    notes = (f"and {hidden} older finished agents",) if hidden > 0 else ()
    title = f"Agents of this session {session_id[:8]}"
    return Section(title, tuple(running + finished[:LIST_LIMIT]), notes)


# ---------------------------------------------------------------- other Claude sessions


def session_registry(paths: Paths, alive: Callable[[int], bool]) -> dict[str, dict]:
    """Live Claude Code processes by session id, from ~/.claude/sessions/<pid>.json."""
    found = {}
    for path in sorted(paths.sessions.glob("*.json")):
        try:
            entry = read_json(path)
        except ValueError as error:  # a file that is rewritten at this moment
            print(f"note: skipped {error}", file=sys.stderr)
            continue
        if isinstance(entry.get("pid"), int) and entry.get("sessionId") and alive(entry["pid"]):
            found[entry["sessionId"]] = entry
    return found


def session_run(paths: Paths, entry: dict, now: datetime) -> Run:
    session_id = entry["sessionId"]
    transcript = transcript_for(paths, session_id)
    last_write = mtime(transcript)
    state, active = str(entry.get("status", "unknown")), entry.get("status") == "busy"
    lines = [f"pid {entry['pid']}, last write {age(last_write, now)}"]
    job_path = paths.jobs / session_id[:8] / "state.json"
    if entry.get("kind") == "bg" and job_path.exists():
        job = read_json(job_path)
        state, active = f"{job.get('state', '?')} (background job)", job.get("state") == "working"
        lines += [f"detail: {clip(str(job['detail']), TEXT_CHARS)}"] if job.get("detail") else []
        lines += (
            [f"waits on Leo: {clip(str(job['needs']), TEXT_CHARS)}"] if job.get("needs") else []
        )
    prompt = last_prompt(transcript) if transcript else ""
    lines += [f"last prompt: {prompt}"] if prompt else []
    words = last_words(transcript) if transcript else ""
    lines += [words] if words else []
    title = f"{clip(str(entry.get('name', '?')), TEXT_CHARS)} in {home(entry.get('cwd', '?'))}"
    watch = "its own terminal tab; the herdr skill finds a Herdr tab by session"
    return Run(f"session:{session_id[:8]}", state, title, active, last_write, tuple(lines), watch)


def sessions_section(
    paths: Paths, own_id: str, registry: dict[str, dict], now: datetime
) -> Section:
    others = [entry for sid, entry in registry.items() if sid != own_id]
    kept = [entry for entry in others if transcript_for(paths, entry["sessionId"])]
    runs = sorted((session_run(paths, entry, now) for entry in kept), key=_newest_first(now))
    busy, idle = [run for run in runs if run.active], [run for run in runs if not run.active]
    hidden = len(idle) - LIST_LIMIT
    notes = [f"and {hidden} older idle sessions"] if hidden > 0 else []
    if len(kept) < len(others):
        notes.append(f"sessions without a transcript: {len(others) - len(kept)}, such as claude -p")
    return Section("Other Claude sessions", tuple(busy + idle[:LIST_LIMIT]), tuple(notes))


# ---------------------------------------------------------------- NAH


def worktrees() -> list[Path]:
    """Every checkout of the current repo, the main one first: a live ledger can sit in any."""
    try:
        text = run_command(["git", "worktree", "list", "--porcelain"])
    except RuntimeError:
        return []
    prefix = "worktree "
    return [
        Path(line.removeprefix(prefix)) for line in text.splitlines() if line.startswith(prefix)
    ]


def event_time(event: dict) -> datetime | None:
    return parse_time(event["occurred_at"]) if event.get("occurred_at") else None


def latest_event_time(events_path: Path) -> datetime:
    times = [t for t in map(event_time, json_rows(tail_lines(events_path, 20_000))) if t]
    return max(times, default=datetime.min.replace(tzinfo=timezone.utc))


def nah_ledgers(repos: list[Path]) -> dict[str, Path]:
    """Sprint id -> its live ledger. A worktree can hold a stale copy of the main checkout's .nah
    (memory note nah-worktree-ledger), so the copy with the newest event wins; a tie goes to the
    repo listed first."""
    best: dict[str, Path] = {}
    for repo in repos:
        for events_file in sorted((repo / ".nah" / "active").glob("*/events.jsonl")):
            ledger, sprint = events_file.parent, events_file.parent.name
            if not (ledger / "tasks.jsonl").exists():
                continue
            newest = latest_event_time(events_file)
            if sprint not in best or newest > latest_event_time(best[sprint] / "events.jsonl"):
                best[sprint] = ledger
    return best


def nah_tasks(ledger: Path) -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    for row in json_rows((ledger / "tasks.jsonl").read_text(errors="replace").splitlines()):
        if row.get("row") == "task" and row.get("id"):
            tasks[row["id"]] = row  # a later row for the same id replaces the earlier one
    return tasks


def nah_report_lines(report: dict) -> list[str]:
    """NAH's own forecast and frontier, from `nah --json <sprint>`."""
    sprint = report.get("sprint") or {}
    lines = []
    forecast = (sprint.get("timing") or {}).get("forecast") or {}
    if forecast.get("remaining_wall_hours") is not None:
        samples = forecast.get("estimate_sample_count") or 0
        basis = f"from {samples} timed tasks" if samples else "from the plan, no timed task yet"
        hours = forecast["remaining_wall_hours"]
        lines.append(f"nah forecast: {hours} h of wall time left (NAH's own estimate {basis})")
    frontier = sprint.get("frontier") or {}
    for field, label in (
        ("ready_task_ids", "ready to start"),
        ("attestation_ready_task_ids", "waits on Leo to attest"),
        ("waiting_external_task_ids", "waits on someone outside"),
        ("gated_task_ids", "gated"),
    ):
        if frontier.get(field):
            lines.append(f"{label}: {', '.join(frontier[field])}")
    return lines


def nah_report(ledger: Path) -> dict | None:
    """`nah --json <sprint>` in the ledger's checkout, since nah finds the ledger from the cwd."""
    try:
        return json.loads(run_command(["nah", "--json", ledger.name], cwd=ledger.parents[2]))
    except (RuntimeError, json.JSONDecodeError) as error:
        print(f"note: nah --json {ledger.name} failed: {error}", file=sys.stderr)
        return None


def nah_run(
    ledger: Path, registry: dict[str, dict], paths: Paths, now: datetime, report: dict | None
) -> Run:
    sprint, tasks = ledger.name, nah_tasks(ledger)
    events = list(json_rows((ledger / "events.jsonl").read_text(errors="replace").splitlines()))
    statuses = [task.get("status", "?") for task in tasks.values()]
    total, done = len(statuses) - statuses.count("canceled"), statuses.count("done")
    last = events[-1] if events else {}
    last_time = event_time(last)
    session_id = _stage_session(events)
    live = registry.get(session_id)
    session_write = mtime(transcript_for(paths, session_id)) if session_id else None
    in_progress = [task for task in tasks.values() if task.get("status") == "in_progress"]
    active = bool(in_progress) or bool(live and live.get("status") == "busy")
    when = clock(last_time, now) if last_time else "none"
    lines = [f"last event {when}: {last.get('type', '?')} {last.get('task_id', '')}".rstrip()]
    if active and session_id:
        where = f"live (pid {live['pid']}, {live.get('status')})" if live else "not live"
        lines.append(f"stage session {session_id[:8]}: {where}, wrote {age(session_write, now)}")
    lines += [
        f"in progress: {t['id']} - {clip(str(t.get('intent', '')), TEXT_CHARS)}"
        for t in in_progress
    ]
    for task in tasks.values():
        if task.get("status") == "blocked":
            reason = clip(str(task.get("blocked_reason") or task.get("reason") or ""), TEXT_CHARS)
            lines.append(f"blocked: {task['id']} - {reason}")
    lines += nah_report_lines(report) if report else []
    writes = [t for t in (last_time, session_write) if t]
    watch = (
        f"cd {home(ledger.parents[2])} && nah {sprint}; Herdr tabs impl:{sprint}, harden:{sprint}"
    )
    title = f"{done} of {total} tasks done"
    state, last_write = "working" if active else "idle", max(writes, default=None)
    return Run(f"nah:{sprint}", state, title, active, last_write, tuple(lines), watch)


def nah_section(
    ledgers: dict[str, Path],
    registry: dict[str, dict],
    paths: Paths,
    now: datetime,
    reporter: Callable[[Path], dict | None],
) -> Section:
    runs = [nah_run(ledger, registry, paths, now, reporter(ledger)) for ledger in ledgers.values()]
    working = [run for run in runs if run.active]
    idle = sorted((run for run in runs if not run.active), key=_newest_first(now))
    return Section("NAH sprints", tuple(working + idle))


# ---------------------------------------------------------------- launchd


def parse_etime(value: str) -> timedelta:
    found = ETIME_RE.match(value.strip())
    if not found:
        raise ValueError(f"unexpected ps etime {value!r}; expected [[dd-]hh:]mm:ss")
    days, hours, minutes, seconds = (int(part) if part else 0 for part in found.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def parse_ps(text: str) -> list[PsRow]:
    """Rows of `ps -A -o pid=,ppid=,etime=,command=`."""
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            rows.append((int(parts[0]), int(parts[1]), parse_etime(parts[2]), parts[3]))
    return rows


def descendants(pid: int, rows: list[PsRow]) -> list[PsRow]:
    found, parents = [], {pid}
    while parents:
        children = [row for row in rows if row[1] in parents]
        found += children
        parents = {row[0] for row in children}
    return found


def run_history(records: Path, started: datetime | None, now: datetime) -> list[str]:
    """The newest run record's stages, how long the last finished runs took, and, while the job
    runs (`started` is set), its end if it takes as long as the median of those runs. While the
    job runs, the newest record is the current run's, so it is left out of the durations."""
    files = sorted(records.glob("*.json"))
    if not files:
        return []
    stages = [s for s in read_json(files[-1]).get("stages", []) if isinstance(s, dict)]
    stage_text = ", ".join(f"{s.get('name')} {s.get('status')}" for s in stages) or "no stages yet"
    lines = [f"run record {home(files[-1])}: {stage_text}"]
    durations: list[tuple[str, timedelta]] = []
    for path in (files[:-1] if started else files)[-RUN_HISTORY:]:
        record = read_json(path)
        if record.get("started_at") and record.get("finished_at"):
            took = parse_time(record["finished_at"]) - parse_time(record["started_at"])
            durations.append((path.stem, took))
    if not durations:
        return lines
    lines.append(
        "earlier runs took: " + ", ".join(f"{day} {span(took)}" for day, took in durations)
    )
    if started:
        median = sorted(took for _, took in durations)[len(durations) // 2]
        zone = now.astimezone().strftime("%Z")
        lines.append(
            f"eta: ends {clock(started + median, now)} {zone} if it takes the median earlier run"
            f" ({span(median)}) - estimate"
        )
    return lines


def launchd_run(spec: LaunchdSpec, launchctl: str, rows: list[PsRow], now: datetime) -> Run:
    """The judge's log can stay quiet for 15 minutes while its `claude -p` calls run, so a new
    child process counts as a write too (seen 2026-11-22: log quiet 15 min, a call 3 s old)."""
    fields: dict[str, str] = {}
    for name, value in LAUNCHCTL_FIELD_RE.findall(launchctl):
        fields.setdefault(name, value.strip())  # nested blocks repeat "state ="; the job's is first
    running = fields.get("state") == "running"
    pid = int(fields["pid"]) if fields.get("pid", "").isdigit() else None
    log = Path(fields["stdout path"]) if fields.get("stdout path") else None
    log_write = mtime(log)
    own = next((row for row in rows if row[0] == pid), None)
    youngest = min(descendants(pid, rows), key=lambda row: row[2], default=None) if pid else None
    child_start = now - youngest[2] if youngest else None
    activity = f"log written {age(log_write, now)}"
    if youngest:
        activity += (
            f"; newest child process started {age(child_start, now)}: {_program(youngest[3])}"
        )
    lines = [activity]
    if log and log.exists():
        steps = [line for line in tail_lines(log) if spec.step_pattern.search(line)]
        lines += [f"step: {clip(line, TEXT_CHARS)}" for line in steps[-STEP_LINES:]]
    lines += run_history(spec.records, now - own[2] if running and own else None, now)
    if not running and fields.get("last exit code"):
        lines.append(f"last exit code: {fields['last exit code']}")
    state = (
        f"running {span(own[2])} (pid {pid})" if running and own else fields.get("state", "unknown")
    )
    last_write = max((t for t in (log_write, child_start) if t), default=None)
    title = f"scheduled job {spec.label}"
    return Run(f"launchd:{spec.label}", state, title, running, last_write, tuple(lines), spec.watch)


def launchctl_text(label: str) -> str:
    try:
        return run_command(["launchctl", "print", f"gui/{os.getuid()}/{label}"])
    except RuntimeError as error:
        return f"state = not loaded ({error})"


def launchd_runs(now: datetime) -> list[Run]:
    rows = parse_ps(run_command(["ps", "-A", "-o", "pid=,ppid=,etime=,command="]))
    return [launchd_run(spec, launchctl_text(spec.label), rows, now) for spec in LAUNCHD_JOBS]


# ---------------------------------------------------------------- ETA


def parse_since(value: str) -> datetime:
    try:
        moment = parse_time(value)
    except ValueError as error:
        raise ValueError(f"--since {value!r} is not ISO 8601") from error
    if moment.tzinfo is None:
        raise ValueError(f"--since {value!r} has no time zone; add Z or an offset such as -05:00")
    return moment


def eta_lines(done: int, left: int, since: datetime, now: datetime) -> list[str]:
    """Time left at the rate of `done` items since `since`. Run it once from the start and once
    from the start of a recent window, with the same `left`, to get a range."""
    if done < 0 or left < 0:
        raise ValueError(f"need done >= 0 and left >= 0; got done={done}, left={left}")
    if since >= now:
        raise ValueError(f"--since {since.isoformat()} is not in the past (now {now.isoformat()})")
    zone = now.astimezone().strftime("%Z")
    minutes = (now - since).total_seconds() / 60
    if left == 0:
        return ["finished: nothing left"]
    if done == 0:
        return [f"no rate yet: 0 done in {minutes:.1f} min, so no ETA"]
    rate = done / minutes
    end = now + timedelta(minutes=left / rate)
    basis = f"{done} in {minutes:.1f} min since {clock(since, now)}"
    return [
        f"rate: {rate:.2f} per min (derived: {basis})",
        f"eta: {left} left, {span(end - now)}, ends {clock(end, now)} {zone}"
        " - estimate, assumes this rate holds",
    ]


# ---------------------------------------------------------------- snapshot and wait


def render(sections: list[Section], now: datetime) -> str:
    stamp = now.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    out = [f"now: {stamp}. Hang rule: says it works, no write for {span(SILENT)}."]
    for section in sections:
        out += ["", f"## {section.title}"]
        if not section.runs and not section.notes:
            out.append("nothing found")
        for run in section.runs:
            flag = "HANG? " if run.silent(now) else ""
            out.append(f"- {flag}{run.key} {run.state} - {run.title}")
            out += [f"    {line}" for line in run.lines]
            if run.watch and run.active:
                out.append(f"    watch: {run.watch}")
        out += section.notes
    return "\n".join(out)


def snapshot(repos: list[Path], paths: Paths, session_id: str, now: datetime) -> str:
    registry = session_registry(paths, pid_alive)

    def nah() -> Section:
        if not repos:
            return Section("NAH sprints", (), ("not in a git checkout; pass --repo PATH",))
        return nah_section(nah_ledgers(repos), registry, paths, now, nah_report)

    def launchd() -> Section:
        if shutil.which("launchctl") is None:
            return Section("launchd jobs", (), ("no launchctl on this machine",))
        return Section("launchd jobs", tuple(launchd_runs(now)))

    builders: list[tuple[str, Callable[[], Section]]] = [
        ("Agents of this session", lambda: agents_section(paths, session_id, now)),
        ("Other Claude sessions", lambda: sessions_section(paths, session_id, registry, now)),
        ("NAH sprints", nah),
        ("launchd jobs", launchd),
    ]
    sections = []
    for title, build in builders:
        try:
            sections.append(build())
        except (RuntimeError, ValueError, OSError) as error:  # one broken source hides no other
            sections.append(Section(title, (), (f"source failed: {error}",)))
    return render(sections, now)


def find_run(
    key: str, repos: list[Path], paths: Paths, session_id: str, now: datetime
) -> Run | None:
    """The run that `key` names, built the same way as in the snapshot; None when it is gone."""
    kind, _, name = key.partition(":")
    if kind == "agent":
        return next((r for r in agent_runs(paths, session_id, now) if r.key.startswith(key)), None)
    if kind == "session":
        registry = session_registry(paths, pid_alive)
        entry = next((e for sid, e in registry.items() if sid.startswith(name)), None)
        return session_run(paths, entry, now) if entry else None
    if kind == "nah":
        ledger = nah_ledgers(repos).get(name)
        if ledger:
            return nah_run(
                ledger, session_registry(paths, pid_alive), paths, now, nah_report(ledger)
            )
        archived = [path for repo in repos for path in repo.glob(f".nah/done/*/sprints/{name}")]
        state = f"closed, archived at {home(archived[0])}" if archived else ""
        return Run(key, state, "sprint closed", False, None) if archived else None
    if kind == "launchd":
        return next((run for run in launchd_runs(now) if run.key == key), None)
    raise SystemExit(
        f"unknown key {key!r}; use a key from the snapshot: agent:, session:, nah:, launchd:"
    )


def judge(first: Run, current: Run | None, now: datetime) -> tuple[Outcome | None, str]:
    """The outcome of one poll, or None while the run still works."""
    if current is None:
        return Outcome.GONE, f"{first.key} is no longer listed: it ended or its process is gone"
    new = [line for line in current.lines if line.startswith(NEEDS_LEO) and line not in first.lines]
    if new:
        return Outcome.NEEDS_LEO, f"{current.key}: {new[0]}"
    if not current.active:
        detail = f"; {current.lines[0]}" if current.lines else ""
        return Outcome.DONE, f"{current.key} {current.state} - {current.title}{detail}"
    if current.silent(now):
        quiet = age(current.last_write, now)
        return Outcome.SILENT, f"{current.key} says {current.state} but last wrote {quiet}"
    return None, f"{current.state} - {current.title}"


def wait_for(
    first: Run,
    find: Callable[[datetime], Run | None],
    max_wait: timedelta,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[Outcome, str]:
    start = now = now_fn()
    current: Run | None = first
    idle_since: datetime | None = None
    while True:
        outcome, text = judge(first, current, now)
        if outcome is Outcome.DONE:
            idle_since = idle_since or now
            if now - idle_since >= SETTLE:
                return outcome, text
        elif outcome is not None:
            return outcome, text
        else:
            idle_since = None
        if now - start >= max_wait:
            return Outcome.TIMED_OUT, f"still running after {span(max_wait)}: {text}"
        sleep_fn(POLL_SECONDS)
        now = now_fn()
        current = find(now)


def main(argv: list[str]) -> int:
    raw = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=raw)
    parser.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    commands = parser.add_subparsers(dest="command", required=True)
    shot = commands.add_parser("snapshot")
    shot.add_argument("--repo", type=Path, action="append", help="a checkout with .nah/")
    eta = commands.add_parser("eta")
    eta.add_argument("--done", type=int, required=True)
    eta.add_argument("--left", type=int, required=True)
    eta.add_argument("--since", required=True, help="start of the counted work, ISO 8601 with zone")
    wait = commands.add_parser("wait")
    wait.add_argument("key", help="a run key from the snapshot, such as nah:landscape-mvp")
    wait.add_argument("--repo", type=Path, action="append")
    wait.add_argument("--max-hours", type=float, default=MAX_WAIT_HOURS)
    args = parser.parse_args(argv[1:])
    now = _utc_now()
    if args.command == "eta":
        try:
            print("\n".join(eta_lines(args.done, args.left, parse_since(args.since), now)))
        except ValueError as error:
            raise SystemExit(str(error)) from error
        return 0
    if not args.session:
        raise SystemExit("CLAUDE_CODE_SESSION_ID is unset; pass --session <id>")
    paths, repos = Paths.default(), args.repo or worktrees()
    if args.command == "snapshot":
        print(snapshot(repos, paths, args.session, now))
        return 0

    def find(moment: datetime) -> Run | None:
        return find_run(args.key, repos, paths, args.session, moment)

    first = find(now)
    if first is None:
        raise SystemExit(f"no run {args.key!r} now; `snapshot` lists the keys")
    print(
        f"watching {first.key} ({first.state}) from {clock(now, now)}: poll {POLL_SECONDS} s,"
        f" hang flag after {span(SILENT)}, give up after {args.max_hours:g} h",
        flush=True,
    )
    outcome, text = wait_for(first, find, timedelta(hours=args.max_hours), _utc_now)
    print(f"{outcome.name} at {clock(_utc_now(), now)}: {text}")
    return int(outcome)


# ---------------------------------------------------------------- private helpers


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _newest_first(now: datetime) -> Callable[[Run], float]:
    return lambda run: -(run.last_write or now).timestamp()


def _block_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", ""))
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _agent_progress(transcript: Path) -> tuple[datetime | None, int, str]:
    """(first timestamp, tool calls so far, the last tool call) of an agent transcript."""
    started, calls, last_tool = None, 0, ""
    if not transcript.exists():
        return started, calls, last_tool
    with transcript.open(errors="replace") as handle:
        for line in handle:
            if started is not None and '"tool_use"' not in line:
                continue
            for row in json_rows([line]):
                if started is None and row.get("timestamp"):
                    started = parse_time(row["timestamp"])
                for block in (row.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        calls, last_tool = calls + 1, _tool_label(block)
    return started, calls, last_tool


def _tool_label(block: dict) -> str:
    tool_input = block.get("input") or {}
    detail = (
        tool_input.get("description") or tool_input.get("command") or tool_input.get("file_path")
    )
    name = str(block.get("name", "?"))
    return clip(f"{name} - {detail}" if detail else name, TEXT_CHARS)


def _stage_session(events: list[dict]) -> str:
    """The session of the latest NAH stage event: the one that should write now."""
    for event in reversed(events):
        data, actor = event.get("data") or {}, event.get("actor") or {}
        if data.get("session_id") or actor.get("session_id"):
            return str(data.get("session_id") or actor.get("session_id"))
    return ""


def _program(command: str) -> str:
    """`claude -p <long prompt>` -> `claude -p`: the program and its first flag only."""
    parts = command.split()
    head = Path(parts[0]).name if parts else "?"
    return f"{head} {parts[1]}" if len(parts) > 1 and parts[1].startswith("-") else head


if __name__ == "__main__":
    sys.exit(main(sys.argv))
