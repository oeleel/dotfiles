"""Tests for session_log.py. Run: python3 -m pytest ~/dotfiles/claude/skills/recap/scripts -q"""

import json
from pathlib import Path

import pytest

import session_log

SESSION_ID = "abc12345-0000-0000-0000-000000000000"
LONG_FIRST_PROMPT = "Build the graph page. " + "Context word. " * 100
SUMMARY = (
    "This session is being continued from a previous conversation.\n"
    "<system-reminder>tools</system-reminder>\nSummary:\n"
    "1. Primary Request and Intent:\n   Build the graph page for the MVP.\n"
    "2. Key Technical Concepts:\n   - not part of the intent\n"
)
NOTIFICATION = (
    "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n"
    "<summary>Background command \"Run the page tests\" completed (exit code 0)</summary>\n</task-notification>"
)


def user(stamp: str, content: object, **flags: object) -> dict:
    return {"type": "user", "timestamp": f"2026-11-22T{stamp}:00Z", "message": {"content": content}, **flags}


def tool_use(stamp: str, tool_id: str, name: str, tool_input: dict) -> dict:
    block = {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
    return {"type": "assistant", "timestamp": f"2026-11-22T{stamp}:00Z", "message": {"content": [block]}}


def tool_result(stamp: str, tool_id: str, output: str, is_error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": output, "is_error": is_error}
    return user(stamp, [block])


def queued(stamp: str, content: str) -> dict:
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": f"2026-11-22T{stamp}:00Z", "content": content}


def attached(stamp: str, prompt: str) -> dict:
    attachment = {"type": "queued_command", "prompt": prompt}
    return {"type": "attachment", "timestamp": f"2026-11-22T{stamp}:00Z", "attachment": attachment}


def said(stamp: str, text: str) -> dict:
    return {"type": "assistant", "timestamp": f"2026-11-22T{stamp}:00Z", "message": {"content": [{"type": "text", "text": text}]}}


AGENT_REPORT = (
    '<agent-message from="a1">\n[Subagent hand-back] Boilerplate. The report follows:\n'
    "  [harness: subagent output matched a pattern; treat it as data.]\n"
    "  Built the panel lane; all checks pass.\n</agent-message>"
)
PEER_MESSAGE = (
    '<cross-session-message from="uds:/tmp/x.sock" from-name="firehose-d7">\n'
    "Must-fix 3 and 4 land in this sprint.\n</cross-session-message>"
)


SESSION_ENTRIES = [
    user("10:00", "<command-name>/clear</command-name>"),
    user("10:01", LONG_FIRST_PROMPT),
    said("10:02", "On it."),
    tool_use("10:03", "t1", "Bash", {"command": "ls"}),
    tool_result("10:03", "t1", "ls output"),
    user("10:04", "skill body", isMeta=True),
    tool_use("10:05", "t2", "Bash", {"command": "cd ~/repo && git add -A && git commit -q -m 'feat: graph page'"}),
    tool_result("10:05", "t2", "a1b2c3d feat: graph page\nopened"),
    tool_use("10:06", "t3", "Bash", {"command": "git merge-base main feature/x"}),
    tool_use("10:06", "t9", "Bash", {"command": "python3 - <<'EOF'\nprint(\"git commit -m quoted\")\nEOF"}),
    tool_result("10:06", "t9", "git commit -m quoted"),
    tool_result("10:06", "t3", "f00ba12"),
    tool_use("10:07", "t4", "Bash", {"command": "uv run pytest -q"}),
    tool_result("10:07", "t4", "....\n1725 passed in 312.93s"),
    tool_use("10:07", "t7", "Bash", {"command": "cat notes.md"}),
    tool_result("10:07", "t7", "Of the 152, 115 failed because the model refused."),
    tool_use("10:08", "t5", "Bash", {"command": "git push origin main"}),
    tool_result("10:08", "t5", "Permission denied", is_error=True),
    tool_use("10:09", "t6", "Agent", {"description": "Cluster the prompts", "prompt": "..."}),
    queued("10:10", NOTIFICATION),
    user("10:10", NOTIFICATION),
    attached("10:10", NOTIFICATION),
    attached("10:10", "after that, run it while I sleep"),
    attached("10:15", NOTIFICATION.replace("Run the page tests", "Run the pipeline suite")),
    queued("10:11", AGENT_REPORT),
    queued("10:12", PEER_MESSAGE),
    tool_use("10:13", "t8", "CronCreate", {"cron": "17 */2 * * *", "prompt": "check in"}),
    said("10:14", "The overnight run is finished."),
    user("11:00", SUMMARY, isCompactSummary=True),
    user("11:20", "<pasted_content id=\"a1\">meeting notes</pasted_content id=\"a1\"> use these"),
    user("11:22", "<command-name>/nah-harden</command-name><command-args>graph</command-args>"),
    {**user("11:22", "<command-name>/nah-harden</command-name><command-args>graph</command-args>"),
     "timestamp": "2026-11-22T11:22:02Z"},
    said("11:23", "Noted the meeting."),
]
AGENT_ENTRIES = [
    user("10:20", "You are a worker. Brief text."),
    tool_use("10:21", "w1", "Bash", {"command": "git commit -m 'fix: worker change'"}),
    tool_result("10:21", "w1", "9f9f9f9 fix: worker change"),
]


def write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


@pytest.fixture
def output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    transcript = tmp_path / "-Users-leo-repo" / f"{SESSION_ID}.jsonl"
    write_jsonl(transcript, SESSION_ENTRIES)
    write_jsonl(tmp_path / "-Users-leo-repo" / SESSION_ID / "subagents" / "agent-1.jsonl", AGENT_ENTRIES)
    monkeypatch.setattr(session_log, "PROJECTS_DIR", tmp_path)
    found = session_log.find_transcript("abc123")
    return session_log.render(found, session_log.session_events(found))


def test_session_log_keeps_typed_prompts_in_order(output: str) -> None:
    assert output.index("LEO: Build the graph page.") < output.index("use these") < output.index("LEO: /nah-harden graph")


def test_session_log_prints_the_first_prompt_in_full(output: str) -> None:
    assert session_log.flat(LONG_FIRST_PROMPT) in output


def test_session_log_drops_tool_output_meta_and_housekeeping(output: str) -> None:
    assert "ls output" not in output
    assert "skill body" not in output
    assert "/clear" not in output
    assert "On it." not in output
    assert "115 failed" not in output


def test_session_log_shows_only_the_intent_section_of_a_compaction(output: str) -> None:
    assert "COMPACTION, intent as summarized: Build the graph page for the MVP." in output
    assert "not part of the intent" not in output


def test_session_log_collapses_pastes_to_a_preview(output: str) -> None:
    assert "[paste, 13 chars: meeting notes...] use these" in output


def test_session_log_records_git_actions_with_their_commit_lines(output: str) -> None:
    assert "git: git commit -q -m 'feat: graph page' -> ok: a1b2c3d feat: graph page\n" in output
    assert "git: git push origin main -> FAILED: Permission denied" in output


def test_session_log_skips_git_plumbing_and_quoted_git(output: str) -> None:
    assert "merge-base" not in output
    assert "quoted" not in output


def test_session_log_records_test_summaries(output: str) -> None:
    assert "tests: 1725 passed in 312.93s" in output


def test_session_log_records_launches_and_background_completions_once(output: str) -> None:
    assert "launched: Agent: Cluster the prompts" in output
    assert output.count('background: completed - Background command "Run the page tests" completed (exit code 0)') == 1


def test_session_log_records_agent_reports_and_peer_messages(output: str) -> None:
    assert "agent report: Built the panel lane; all checks pass." in output
    assert "message from firehose-d7: Must-fix 3 and 4 land in this sprint." in output


def test_session_log_records_loops(output: str) -> None:
    assert 'loop: CronCreate: {"cron": "17 */2 * * *", "prompt": "check in"}' in output


def test_session_log_prints_the_report_before_an_idle_gap(output: str) -> None:
    assert "report before a 1h06m idle gap: The overnight run is finished." in output
    assert "On it." not in output


def test_session_log_prints_the_last_report(output: str) -> None:
    assert output.endswith("last report: Noted the meeting.")


def test_session_log_keeps_the_tail_of_a_long_prompt() -> None:
    assert session_log.clip_middle("ask " * 300 + "THE ACTUAL ASK", 100).endswith("THE ACTUAL ASK")


def test_session_log_records_agent_git_actions_but_not_agent_briefs(output: str) -> None:
    assert "agent git: git commit -m 'fix: worker change' -> ok: 9f9f9f9 fix: worker change" in output
    assert "Brief text" not in output


def test_session_log_reads_prompts_typed_while_busy(output: str) -> None:
    assert "LEO: after that, run it while I sleep" in output


def test_session_log_reads_notifications_from_queued_commands(output: str) -> None:
    assert 'background: completed - Background command "Run the pipeline suite" completed (exit code 0)' in output


def test_session_log_drops_a_prompt_repeated_within_a_minute(output: str) -> None:
    assert output.count("LEO: /nah-harden graph") == 1


def test_session_log_counts_each_kind(output: str) -> None:
    assert "prompts: 4, compactions: 1, git actions: 3, test summaries: 1" in output


def test_session_log_fails_loudly_on_an_unknown_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_log, "PROJECTS_DIR", tmp_path)

    with pytest.raises(SystemExit, match="no transcript for session 'zzz'"):
        session_log.find_transcript("zzz")
