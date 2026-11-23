"""Tests for run_status.py. Run: python3 -m pytest ~/dotfiles/claude/skills/run-status/scripts -q"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import run_status as rs

NOW = datetime(2026, 11, 22, 23, 30, tzinfo=timezone.utc)  # 18:30 EST
SESSION_ID = "abc12345-0000-0000-0000-000000000000"
OTHER_ID = "def67890-0000-0000-0000-000000000000"
STAGE_ID = "5eed0000-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def eastern_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leo's clock: every local time in these tests is US Eastern."""
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()


# ---------------------------------------------------------------- fixture builders


def stamp(minutes_before_now: float) -> str:
    return (NOW - timedelta(minutes=minutes_before_now)).isoformat().replace("+00:00", "Z")


def write_jsonl(path: Path, rows: list[dict], minutes_old: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return touch(path, minutes_old)


def touch(path: Path, minutes_old: float) -> Path:
    moment = (NOW - timedelta(minutes=minutes_old)).timestamp()
    os.utime(path, (moment, moment))
    return path


def tool_use(minutes: float, tool_id: str, name: str, tool_input: dict) -> dict:
    block = {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
    return {"type": "assistant", "timestamp": stamp(minutes), "message": {"content": [block]}}


def tool_result(minutes: float, tool_id: str, text: str) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": text}
    return {"type": "user", "timestamp": stamp(minutes), "message": {"content": [block]}}


def said(minutes: float, text: str) -> dict:
    block = {"type": "text", "text": text}
    return {"type": "assistant", "timestamp": stamp(minutes), "message": {"content": [block]}}


def typed(minutes: float, text: str) -> dict:
    return {"type": "user", "timestamp": stamp(minutes), "message": {"content": text}}


def paths_in(root: Path) -> rs.Paths:
    return rs.Paths(projects=root / "projects", sessions=root / "sessions", jobs=root / "jobs")


def make_agent(root: Path, agent_id: str, meta: dict, rows: list[dict], minutes_old: float) -> Path:
    folder = root / "projects" / "-Users-leo-repo" / SESSION_ID / "subagents"
    write_jsonl(folder / f"agent-{agent_id}.jsonl", rows, minutes_old)
    meta_path = folder / f"agent-{agent_id}.meta.json"
    meta_path.write_text(json.dumps(meta))
    return meta_path


def make_registry_entry(root: Path, pid: int, session_id: str, **fields: object) -> None:
    entry = {"pid": pid, "sessionId": session_id, "cwd": "/Users/leo/repo", "name": f"repo-{pid}"}
    (root / "sessions").mkdir(parents=True, exist_ok=True)
    (root / "sessions" / f"{pid}.json").write_text(json.dumps({**entry, **fields}))


def make_transcript(root: Path, session_id: str, rows: list[dict], minutes_old: float) -> Path:
    return write_jsonl(
        root / "projects" / "-Users-leo-repo" / f"{session_id}.jsonl", rows, minutes_old
    )


def task_row(task_id: str, status: str, **fields: object) -> dict:
    return {"row": "task", "id": task_id, "status": status, "intent": f"build {task_id}", **fields}


def event(minutes: float, kind: str, task_id: str = "", session_id: str = "") -> dict:
    row: dict = {"row": "event", "type": kind, "occurred_at": stamp(minutes), "task_id": task_id}
    if session_id:
        row["actor"] = {"session_id": session_id}
    return row


def make_ledger(repo: Path, sprint: str, tasks: list[dict], events: list[dict]) -> Path:
    ledger = repo / ".nah" / "active" / sprint
    write_jsonl(ledger / "tasks.jsonl", tasks)
    write_jsonl(ledger / "events.jsonl", events)
    return ledger


LAUNCHCTL = """gui/501/com.n2o.firehose.judge = {
\tactive count = 1
\tstate = running
\tstdout path = {log}
\tpid = 4415
\tendpoints = {
\t\t"com.example" = {
\t\t\tstate = active
\t\t}
\t}
}"""


def make_job(root: Path, log_minutes_old: float) -> tuple[rs.LaunchdSpec, str]:
    log = root / "judge.log"
    log.write_text("INFO noise\n2026-11-22T22:31:03Z run-host: pushed the day's rows\nINFO noise\n")
    touch(log, log_minutes_old)
    records = root / "runs"
    records.mkdir()
    old = {"started_at": "2026-11-21T13:02:54Z", "finished_at": "2026-11-21T21:09:52Z"}
    (records / "2026-11-21.json").write_text(json.dumps(old))
    current = {
        "started_at": "2026-11-22T21:17:31Z",
        "finished_at": "2026-11-22T22:30:55Z",
        "stages": [{"name": "collect", "status": "ok"}],
    }
    (records / "2026-11-22.json").write_text(json.dumps(current))
    spec = rs.LaunchdSpec(
        "com.n2o.firehose.judge", re.compile(r"run-host:"), records, "tail -f log"
    )
    return spec, LAUNCHCTL.replace("{log}", str(log))


# ---------------------------------------------------------------- helpers


def test_span_formats_minutes_hours_and_days() -> None:
    texts = [rs.span(timedelta(minutes=m)) for m in (7, 135, 3 * 24 * 60)]
    assert texts == ["7 min", "2h15m", "3 days"]


def test_clock_adds_the_date_only_for_another_day() -> None:
    texts = [rs.clock(NOW - timedelta(hours=h), NOW) for h in (1, 30)]
    assert texts == ["17:30", "11-21 12:30"]


def test_clip_keeps_the_result_and_the_ask() -> None:
    text = "Done: 4 merged. " + "detail " * 40 + "Your call: merge A or B?"

    clipped = rs.clip(text, 60)

    assert clipped == "Done: 4 merged. detail detail detail [...] Your call: merge A or B?"


# ---------------------------------------------------------------- this session


def test_agent_run_reports_a_finished_agent_as_not_active(tmp_path: Path) -> None:
    meta = make_agent(tmp_path, "a1", {"description": "Build lane 1", "finished": True}, [], 40)

    run = rs.agent_run(meta, NOW)

    assert (run.active, run.state, run.title) == (False, "finished 17:50", "Build lane 1")


def test_agent_run_quotes_the_report_of_a_finished_agent(tmp_path: Path) -> None:
    rows = [
        said(9, "Now the tests."),
        tool_use(5, "t9", "SubagentHandback", {"message": "Files: a.py"}),
    ]
    meta = make_agent(tmp_path, "a4", {"description": "Lane 4", "finished": True}, rows, 5)

    run = rs.agent_run(meta, NOW)

    assert run.lines == ("report: Files: a.py",)


def test_agent_run_quotes_the_last_text_of_an_agent_that_died(tmp_path: Path) -> None:
    rows = [
        tool_use(9, "t1", "Write", {"file_path": "/x"}),
        said(8, "You've hit your weekly limit"),
    ]
    meta = make_agent(tmp_path, "a5", {"description": "Lane 5", "finished": True}, rows, 8)

    run = rs.agent_run(meta, NOW)

    assert run.lines == ("said: You've hit your weekly limit",)


def test_agent_run_counts_tool_calls_and_names_the_last_one(tmp_path: Path) -> None:
    rows = [
        typed(30, "You are a worker."),
        tool_use(20, "t1", "Read", {"file_path": "/repo/a.py"}),
        tool_use(10, "t2", "Bash", {"command": "pytest -q", "description": "Run the tests"}),
    ]
    meta = make_agent(tmp_path, "a2", {"description": "Build lane 2"}, rows, 1)

    run = rs.agent_run(meta, NOW)

    assert run.lines[:2] == (
        "started 18:00, last write 1 min ago, 2 tool calls",
        "last call: Bash - Run the tests",
    )


def test_agent_run_flags_a_silent_running_agent(tmp_path: Path) -> None:
    meta = make_agent(tmp_path, "a3", {"description": "Stuck lane"}, [typed(60, "go")], 16)

    run = rs.agent_run(meta, NOW)

    assert run.silent(NOW)


# ---------------------------------------------------------------- other sessions


def test_session_registry_skips_dead_processes_and_unreadable_files(tmp_path: Path) -> None:
    make_registry_entry(tmp_path, 11, OTHER_ID, status="busy")
    make_registry_entry(tmp_path, 12, STAGE_ID, status="busy")
    (tmp_path / "sessions" / "13.json").write_text("{not json")

    registry = rs.session_registry(paths_in(tmp_path), alive=lambda pid: pid == 11)

    assert list(registry) == [OTHER_ID]


def test_sessions_section_lists_busy_sessions_first_and_skips_those_without_a_transcript(
    tmp_path: Path,
) -> None:
    make_registry_entry(tmp_path, 11, OTHER_ID, status="busy")
    make_registry_entry(tmp_path, 12, STAGE_ID, status="idle")
    make_registry_entry(tmp_path, 14, "f00d0000-0000-0000-0000-000000000000", status="busy")
    make_transcript(tmp_path, OTHER_ID, [typed(5, "fix the page")], 1)
    make_transcript(tmp_path, STAGE_ID, [typed(5, "hi"), said(4, "Pick A or B?")], 0)
    paths = paths_in(tmp_path)

    section = rs.sessions_section(
        paths, SESSION_ID, rs.session_registry(paths, lambda _: True), NOW
    )

    assert [run.key for run in section.runs] == ["session:def67890", "session:5eed0000"]
    assert section.runs[1].lines[-1] == "said: Pick A or B?"
    assert section.notes == ("sessions without a transcript: 1, such as claude -p",)


def test_session_run_reports_a_background_job_that_waits_on_leo(tmp_path: Path) -> None:
    make_transcript(tmp_path, OTHER_ID, [typed(5, "run it overnight")], 1)
    job = tmp_path / "jobs" / OTHER_ID[:8] / "state.json"
    job.parent.mkdir(parents=True)
    job.write_text(
        json.dumps({"state": "blocked", "detail": "build done", "needs": "restart the run"})
    )
    entry = {"pid": 11, "sessionId": OTHER_ID, "kind": "bg", "status": "busy", "name": "bg"}

    run = rs.session_run(paths_in(tmp_path), entry, NOW)

    assert (run.state, run.active) == ("blocked (background job)", False)
    assert "waits on Leo: restart the run" in run.lines


def test_last_prompt_reads_a_peer_message_and_skips_tool_results(tmp_path: Path) -> None:
    rows = [
        typed(9, "first ask"),
        typed(8, '<hc from="t4m">Leo answered: merge the graph branch.</hc>'),
        tool_result(7, "x", "tool output"),
        typed(6, "<system-reminder>noise</system-reminder>"),
    ]
    transcript = make_transcript(tmp_path, OTHER_ID, rows, 0)

    prompt = rs.last_prompt(transcript)

    assert prompt == "Leo answered: merge the graph branch.</hc>"


# ---------------------------------------------------------------- NAH


def test_nah_ledgers_prefers_the_copy_with_the_newest_event(tmp_path: Path) -> None:
    main, worktree = tmp_path / "main", tmp_path / "worktree"
    make_ledger(main, "s1", [task_row("t1", "done")], [event(60, "task-finished", "t1")])
    fresh = make_ledger(worktree, "s1", [task_row("t1", "done")], [event(5, "task-finished", "t1")])

    ledgers = rs.nah_ledgers([main, worktree])

    assert ledgers == {"s1": fresh}


def test_nah_ledgers_gives_a_tie_to_the_first_repo(tmp_path: Path) -> None:
    main, worktree = tmp_path / "main", tmp_path / "worktree"
    first = make_ledger(main, "s1", [task_row("t1", "done")], [event(5, "task-finished", "t1")])
    make_ledger(worktree, "s1", [task_row("t1", "done")], [event(5, "task-finished", "t1")])

    ledgers = rs.nah_ledgers([main, worktree])

    assert ledgers == {"s1": first}


SPRINT_TASKS = [
    task_row("t1", "done"),
    task_row("t2", "done"),
    task_row("t3", "in_progress"),
    task_row("t4", "blocked", blocked_reason="needs Leo's approval to run --restore"),
    task_row("t5", "canceled"),
]
SPRINT_EVENTS = [
    event(50, "execution-started", "t1", STAGE_ID),
    event(40, "task-finished", "t1"),
    event(20, "task-finished", "t2"),
    event(18, "execution-started", "t3", STAGE_ID),
]


def test_nah_run_counts_tasks_and_names_the_stage_session(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path / "repo", "s5b", SPRINT_TASKS, SPRINT_EVENTS)
    make_transcript(tmp_path, STAGE_ID, [typed(30, "harden")], 2)
    registry = {STAGE_ID: {"pid": 77, "sessionId": STAGE_ID, "status": "busy"}}

    run = rs.nah_run(ledger, registry, paths_in(tmp_path), NOW, None)

    assert (run.state, run.title) == ("working", "2 of 4 tasks done")
    assert run.lines[1] == "stage session 5eed0000: live (pid 77, busy), wrote 2 min ago"
    assert "blocked: t4 - needs Leo's approval to run --restore" in run.lines


def test_nah_run_flags_a_working_sprint_whose_session_is_silent(tmp_path: Path) -> None:
    ledger = make_ledger(tmp_path / "repo", "s5b", SPRINT_TASKS, SPRINT_EVENTS)
    make_transcript(tmp_path, STAGE_ID, [typed(30, "harden")], 17)

    run = rs.nah_run(ledger, {}, paths_in(tmp_path), NOW, None)

    assert run.silent(NOW)


def test_nah_report_lines_quote_nah_forecast_and_who_it_waits_on() -> None:
    report = {
        "sprint": {
            "timing": {"forecast": {"remaining_wall_hours": 2, "estimate_sample_count": 25}},
            "frontier": {"ready_task_ids": ["merge"], "attestation_ready_task_ids": ["restore"]},
        }
    }

    lines = rs.nah_report_lines(report)

    assert lines == [
        "nah forecast: 2 h of wall time left (NAH's own estimate from 25 timed tasks)",
        "ready to start: merge",
        "waits on Leo to attest: restore",
    ]


def test_nah_report_lines_name_a_forecast_from_the_plan_only() -> None:
    report = {
        "sprint": {"timing": {"forecast": {"remaining_wall_hours": 14, "estimate_sample_count": 0}}}
    }

    lines = rs.nah_report_lines(report)

    assert lines == [
        "nah forecast: 14 h of wall time left (NAH's own estimate from the plan, no timed task yet)"
    ]


# ---------------------------------------------------------------- launchd


def test_parse_etime_reads_days_hours_and_minutes() -> None:
    values = [rs.parse_etime(v) for v in ("00:07", "46:28", "02:00:03", "1-03:00:00")]
    assert values == [
        timedelta(seconds=7),
        timedelta(minutes=46, seconds=28),
        timedelta(hours=2, seconds=3),
        timedelta(days=1, hours=3),
    ]


def test_parse_etime_rejects_a_bad_value() -> None:
    with pytest.raises(ValueError, match="'7 min'"):
        rs.parse_etime("7 min")


def test_launchd_run_reads_the_job_state_and_not_a_nested_one(tmp_path: Path) -> None:
    spec, launchctl = make_job(tmp_path, 25)
    rows = [(4415, 1, timedelta(hours=2, minutes=15), "/bin/bash judge-launchd.sh")]

    run = rs.launchd_run(spec, launchctl, rows, NOW)

    assert (run.active, run.state) == (True, "running 2h15m (pid 4415)")


def test_launchd_run_counts_a_new_child_process_as_activity(tmp_path: Path) -> None:
    spec, launchctl = make_job(tmp_path, 25)
    rows = [
        (4415, 1, timedelta(hours=2), "/bin/bash judge-launchd.sh"),
        (4416, 4415, timedelta(minutes=40), "/usr/bin/python3 -m firehose_p1.run"),
        (4417, 4416, timedelta(seconds=7), "claude -p You read one item for N2O"),
    ]

    run = rs.launchd_run(spec, launchctl, rows, NOW)

    assert not run.silent(NOW)
    assert (
        run.lines[0] == "log written 25 min ago; newest child process started 0 min ago: claude -p"
    )


def test_launchd_run_flags_a_job_with_a_quiet_log_and_no_new_child(tmp_path: Path) -> None:
    spec, launchctl = make_job(tmp_path, 25)
    rows = [(4415, 1, timedelta(hours=2), "/bin/bash judge-launchd.sh")]

    run = rs.launchd_run(spec, launchctl, rows, NOW)

    assert run.silent(NOW)


def test_run_history_leaves_out_the_running_record_and_gives_the_median_end(
    tmp_path: Path,
) -> None:
    spec, _ = make_job(tmp_path, 0)

    lines = rs.run_history(spec.records, started=NOW - timedelta(hours=1), now=NOW)

    assert lines == [
        f"run record {spec.records}/2026-11-22.json: collect ok",
        "earlier runs took: 2026-11-21 8h06m",
        "eta: ends 11-23 01:36 EST if it takes the median earlier run (8h06m) - estimate",
    ]


def test_run_history_counts_every_record_when_the_job_is_not_running(tmp_path: Path) -> None:
    spec, _ = make_job(tmp_path, 0)

    lines = rs.run_history(spec.records, started=None, now=NOW)

    assert lines[1:] == ["earlier runs took: 2026-11-21 8h06m, 2026-11-22 1h13m"]


# ---------------------------------------------------------------- ETA


def test_eta_lines_gives_the_rate_and_a_local_end_time() -> None:
    lines = rs.eta_lines(240, 677, NOW - timedelta(minutes=12), NOW)

    assert lines == [
        "rate: 20.00 per min (derived: 240 in 12.0 min since 18:18)",
        "eta: 677 left, 33 min, ends 19:03 EST - estimate, assumes this rate holds",
    ]


def test_eta_lines_rejects_a_negative_count() -> None:
    with pytest.raises(ValueError, match="done=-1, left=677"):
        rs.eta_lines(-1, 677, NOW - timedelta(minutes=5), NOW)


def test_eta_lines_gives_no_eta_before_the_first_item() -> None:
    lines = rs.eta_lines(0, 917, NOW - timedelta(minutes=5), NOW)

    assert lines == ["no rate yet: 0 done in 5.0 min, so no ETA"]


def test_parse_since_rejects_a_time_without_a_zone() -> None:
    with pytest.raises(ValueError, match="no time zone"):
        rs.parse_since("2026-11-22T18:00:00")


# ---------------------------------------------------------------- wait


# ---------------------------------------------------------------- wait


class FakeClock:
    def __init__(self) -> None:
        self.now = NOW

    def read(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def working(lines: tuple[str, ...] = (), minutes_old: float = 1) -> rs.Run:
    return rs.Run(
        "nah:s5b", "working", "2 of 4 tasks done", True, NOW - timedelta(minutes=minutes_old), lines
    )


def idle() -> rs.Run:
    return rs.Run(
        "nah:s5b", "idle", "4 of 4 tasks done", False, NOW, ("last event 18:40: task-finished t4",)
    )


def replay(runs: list[rs.Run | None]) -> Callable[[datetime], rs.Run | None]:
    replies = iter(runs)
    return lambda _now: next(replies)


def test_wait_for_calls_a_run_done_only_after_it_stays_idle() -> None:
    fake = FakeClock()
    polls = [idle(), working(), idle(), idle(), idle(), idle(), idle()]

    result = rs.wait_for(working(), replay(polls), timedelta(hours=1), fake.read, fake.sleep)

    assert result == (
        rs.Outcome.DONE,
        "nah:s5b idle - 4 of 4 tasks done; last event 18:40: task-finished t4",
    )
    assert fake.now == NOW + timedelta(seconds=3 * rs.POLL_SECONDS) + rs.SETTLE  # idle from poll 3


def test_wait_for_needs_leo_only_for_a_block_that_is_new() -> None:
    fake = FakeClock()
    old = ("blocked: t4 - needs Leo's approval",)
    polls = [working(old), working((*old, "blocked: t3 - approve the restore"))]

    result = rs.wait_for(working(old), replay(polls), timedelta(hours=1), fake.read, fake.sleep)

    assert result == (rs.Outcome.NEEDS_LEO, "nah:s5b: blocked: t3 - approve the restore")


def test_wait_for_reports_a_silent_run() -> None:
    fake = FakeClock()

    result = rs.wait_for(
        working(), replay([working(minutes_old=16)]), timedelta(hours=1), fake.read, fake.sleep
    )

    assert result == (rs.Outcome.SILENT, "nah:s5b says working but last wrote 16 min ago")


def test_wait_for_reports_a_run_that_is_gone() -> None:
    fake = FakeClock()

    outcome, _ = rs.wait_for(working(), replay([None]), timedelta(hours=1), fake.read, fake.sleep)

    assert outcome == rs.Outcome.GONE


def test_wait_for_times_out_with_the_last_state() -> None:
    fake = FakeClock()

    result = rs.wait_for(
        working(), lambda _now: working(), timedelta(minutes=1), fake.read, fake.sleep
    )

    assert result == (
        rs.Outcome.TIMED_OUT,
        "still running after 1 min: working - 2 of 4 tasks done",
    )


def test_find_run_reports_an_archived_sprint_as_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".nah" / "done" / "firehose-v2" / "sprints" / "s5b").mkdir(parents=True)

    run = rs.find_run("nah:s5b", [repo], paths_in(tmp_path), SESSION_ID, NOW)

    assert run is not None
    assert (run.active, run.state, run.title) == (
        False,
        f"closed, archived at {repo}/.nah/done/firehose-v2/sprints/s5b",
        "sprint closed",
    )


def test_find_run_rejects_an_unknown_kind(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="'pid:42'"):
        rs.find_run("pid:42", [], paths_in(tmp_path), SESSION_ID, NOW)


# ---------------------------------------------------------------- render and snapshot


def test_render_flags_a_silent_run_as_a_possible_hang() -> None:
    run = rs.Run("agent:a9", "running", "Lane 9", True, NOW - timedelta(minutes=20))

    text = rs.render([rs.Section("This session", (run,))], NOW)

    assert "- HANG? agent:a9 running - Lane 9" in text


def test_snapshot_reports_a_failed_source_and_keeps_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rs, "LAUNCHD_JOBS", ())

    text = rs.snapshot([], paths_in(tmp_path), SESSION_ID, NOW)

    assert f"source failed: no transcript for session '{SESSION_ID}'" in text
    assert "## Other Claude sessions" in text
