#!/usr/bin/env python3
"""Print the record of one Claude Code session for the recap skill, in time order:
- every prompt Leo typed (the first one in full, since it carries the original intent),
- the intent section of each compaction summary,
- git actions (commit, merge, rebase, push, ...) the session or its agents ran,
- test summary lines ("1725 passed in 312s", "3 failed, 10 passed"),
- agent, workflow and loop calls, messages sent to other sessions,
- background-task completions, agent reports and messages from other sessions,
- the last report before each idle gap, and the session's last report.

The recap reads this instead of the model's memory: compaction rewrites the early
conversation, and git history alone cannot tell this session's commits from rebased ones.

Usage: session_log.py [SESSION_ID_PREFIX]
Default session: $CLAUDE_CODE_SESSION_ID (set by Claude Code in every Bash call).
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
PROMPT_CHARS = 600
INTENT_CHARS = 3000
REPORT_CHARS = 800
MESSAGE_CHARS = 300
PASTE_PREVIEW_CHARS = 150
SNIPPET_CHARS = 160
MAX_COMMIT_LINES = 3
IDLE_GAP = timedelta(minutes=60)  # a gap this long usually means Leo stepped away
SKIP_PREFIXES = (
    "<local-command",
    "<bash-",
    "<system-reminder",
    "Caveat:",
    "[Request interrupted",
    "Base directory for this skill",
)
# Built-in commands that change the harness, not the work; they are not asks.
HOUSEKEEPING_COMMANDS = frozenset({"clear", "compact", "config", "doctor", "exit", "login", "model", "resume"})
TRACKED_TOOLS = {
    "Agent": "launched",
    "Task": "launched",
    "Workflow": "launched",
    "CronCreate": "loop",
    "CronDelete": "loop",
    "ScheduleWakeup": "loop",
    "SendMessage": "sent",
}
COMMAND_RE = re.compile(
    r"<command-name>/?([^<]+)</command-name>(?:.*?<command-args>(.*?)</command-args>)?", re.S
)
# The harness writes the closing tag with the id too: </pasted_content id="c366">.
PASTE_RE = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)
REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
INTENT_RE = re.compile(r"1\. Primary Request and Intent:(.*?)(?:\n\s*2\. |\Z)", re.S)
# Only at a command position (start, after && ; | or a newline), so a script that quotes
# "git commit" is not an action. The lookahead keeps merge-base, merge-tree and commit-tree out.
GIT_ACTION_RE = re.compile(
    r"(?:^|[;&|(]\s*|\n\s*)(git (?:-C \S+ )?(?:commit|merge|rebase|push|pull|cherry-pick|revert|reset --hard))(?![\w-])"
)
# "[main 9cc1da1c] subject" from git commit, or "9cc1da1c subject" from git log --oneline.
COMMIT_LINE_RE = re.compile(r"^(?:\[[^\]\s]+(?: \([^)]*\))? [0-9a-f]{7,40}\]|[0-9a-f]{7,40}) \S.*$", re.M)
# Runner summaries only: "N passed in 2s", "N passed (1.1m)", "3 failed, 10 passed"; not prose.
TEST_SUMMARY_RE = re.compile(r"^.*\b\d+ (?:passed|failed)\b(?=,| in \d| \(\d|\s*=*\s*$).*$", re.M)
NOTIFICATION_RE = re.compile(r"<status>(.*?)</status>.*?<summary>(.*?)</summary>", re.S)
SENDER_NAME_RE = re.compile(r'from-name="([^"]+)"')  # a peer session's readable name
SENDER_ID_RE = re.compile(r'from="([^"]+)"')
OPENING_TAG_RE = re.compile(r"^<[^>]+>\s*")
REPORT_START_RE = re.compile(r"The report follows:\s*", re.S)
HARNESS_NOTE_RE = re.compile(r"^\s*\[harness:[^\]]*\]\s*")  # a warning the harness puts before some reports

Event = tuple[str, str, str]  # (UTC ISO timestamp, kind, text)


def find_transcript(session_prefix: str) -> Path:
    matches = list(PROJECTS_DIR.glob(f"*/{session_prefix}*.jsonl"))
    if not matches:
        raise SystemExit(f"no transcript for session {session_prefix!r} under {PROJECTS_DIR}")
    if len(matches) > 1:
        names = ", ".join(p.stem for p in matches)
        raise SystemExit(f"session prefix {session_prefix!r} is ambiguous: {names}")
    return matches[0]


def parse_time(iso_stamp: str) -> datetime:
    return datetime.fromisoformat(iso_stamp.replace("Z", "+00:00"))


def local_time(iso_stamp: str) -> str:
    """Transcripts store UTC; Leo reads local time, and git takes the offset."""
    if not iso_stamp:
        return "unknown"
    return parse_time(iso_stamp).astimezone().strftime("%Y-%m-%d %H:%M %z")


def flat(text: str) -> str:
    return " ".join(text.split())


def clip(text: str, limit: int) -> str:
    text = flat(text)
    return text if len(text) <= limit else text[:limit] + f"... [+{len(text) - limit} chars]"


def clip_middle(text: str, limit: int) -> str:
    """Keep the head and the tail: dictated prompts often end with the actual ask."""
    text = flat(text)
    if len(text) <= limit:
        return text
    head, tail = limit * 3 // 5, limit * 2 // 5
    return f"{text[:head]} [... {len(text) - head - tail} chars ...] {text[-tail:]}"


def block_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def collapse_pastes(text: str) -> str:
    def preview(match: re.Match[str]) -> str:
        body = flat(match.group(1))
        return f"[paste, {len(body)} chars: {body[:PASTE_PREVIEW_CHARS]}...]"

    return PASTE_RE.sub(preview, text)


def delivered_event(stamp: str, text: str) -> Event | None:
    """A message the harness delivered to the session: task completion, agent report, peer message."""
    if text.startswith("<task-notification"):
        found = NOTIFICATION_RE.search(text)
        return (stamp, "background", f"{found.group(1)} - {flat(found.group(2))}") if found else None
    if text.startswith(("<agent-message", "<cross-session-message")):
        sender = SENDER_NAME_RE.search(text) or SENDER_ID_RE.search(text)
        name = sender.group(1) if sender else "unknown"
        report = HARNESS_NOTE_RE.sub("", REPORT_START_RE.split(OPENING_TAG_RE.sub("", text), maxsplit=1)[-1])
        kind = "agent report" if text.startswith("<agent-message") else f"message from {name}"
        return (stamp, kind, clip(REMINDER_RE.sub("", report), MESSAGE_CHARS))
    return None


def typed_prompt_event(stamp: str, entry: dict, text: str) -> Event | None:
    """Turn a user message that holds typed text into an event, or None if it is not an ask."""
    if entry.get("isCompactSummary"):
        intent = INTENT_RE.search(REMINDER_RE.sub("", text))
        return (stamp, "compaction", intent.group(1) if intent else text)
    if entry.get("isMeta"):
        return None
    text = text.strip()
    delivered = delivered_event(stamp, text)
    if delivered or text.startswith(("<task-notification", "<agent-message", "<cross-session-message")):
        return delivered
    command = COMMAND_RE.search(text)
    if command:
        name = command.group(1).strip()
        if name in HOUSEKEEPING_COMMANDS:
            return None
        return (stamp, "prompt", f"/{name} {(command.group(2) or '').strip()}".strip())
    if text.startswith(SKIP_PREFIXES):
        return None
    return (stamp, "prompt", collapse_pastes(text))


def tool_use_event(stamp: str, block: dict, git_calls: dict[str, str], include_calls: bool) -> Event | None:
    tool_input = block.get("input") or {}
    name = block.get("name", "")
    if name == "Bash":
        found = GIT_ACTION_RE.search(tool_input.get("command", ""))
        if found:
            git_calls[block.get("id", "")] = clip(tool_input["command"][found.start(1):], SNIPPET_CHARS)
        return None
    if name not in TRACKED_TOOLS or not include_calls:
        return None
    label = tool_input.get("description") or tool_input.get("reason") or json.dumps(tool_input)
    if name == "SendMessage":
        label = f"to {tool_input.get('to', '?')}: {tool_input.get('summary') or tool_input.get('message', '')}"
    return (stamp, TRACKED_TOOLS[name], f"{name}: {clip(label, SNIPPET_CHARS)}")


def tool_result_events(stamp: str, result: dict, git_calls: dict[str, str]) -> list[Event]:
    output = block_text(result.get("content"))
    events = []
    if result.get("tool_use_id") in git_calls:
        status = "FAILED" if result.get("is_error") else "ok"
        commits = COMMIT_LINE_RE.findall(output)[:MAX_COMMIT_LINES]
        last_line = next((line for line in reversed(output.splitlines()) if line.strip()), "")
        shown = " | ".join(clip(c, SNIPPET_CHARS) for c in commits) or clip(last_line, SNIPPET_CHARS)
        events.append((stamp, "git", f"{git_calls[result['tool_use_id']]} -> {status}: {shown}"))
    summaries = TEST_SUMMARY_RE.findall(output)
    if summaries:
        events.append((stamp, "tests", clip(summaries[-1], SNIPPET_CHARS)))
    return events


def transcript_events(transcript: Path, is_main: bool) -> list[Event]:
    """Read one transcript. Agent transcripts (is_main=False) add only git and test events:
    their user turns are briefs, not Leo's asks."""
    events: list[Event] = []
    git_calls: dict[str, str] = {}  # tool_use id -> the git part of the command
    last_report: tuple[str, str] | None = None  # (timestamp, text) of the latest assistant text
    for line in transcript.open(errors="replace"):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = entry.get("timestamp") or ""
        kind = entry.get("type")
        if kind == "queue-operation" and is_main and entry.get("operation") == "enqueue":
            delivered = delivered_event(stamp, (entry.get("content") or "").strip())
            if delivered:
                events.append(delivered)
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content")
        blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
        if kind == "assistant":
            for block in blocks:
                if block.get("type") == "tool_use":
                    event = tool_use_event(stamp, block, git_calls, include_calls=is_main)
                    if event:
                        events.append(event)
                elif block.get("type") == "text" and block.get("text", "").strip() and is_main:
                    last_report = (stamp, block["text"])
            continue
        if kind != "user":
            continue
        results = [b for b in blocks if b.get("type") == "tool_result"]
        for result in results:
            events.extend(tool_result_events(stamp, result, git_calls))
        if results or not is_main:
            continue
        text = block_text(content)
        event = typed_prompt_event(stamp, entry, text) if text.strip() else None
        if not event:
            continue
        if event[1] == "prompt" and last_report and stamp and parse_time(stamp) - parse_time(last_report[0]) >= IDLE_GAP:
            gap = parse_time(stamp) - parse_time(last_report[0])
            hours, minutes = divmod(int(gap.total_seconds()) // 60, 60)
            events.append((last_report[0], f"report before a {hours}h{minutes:02d}m idle gap", clip(last_report[1], REPORT_CHARS)))
        events.append(event)
    if last_report and is_main:
        events.append((last_report[0], "last report", clip(last_report[1], REPORT_CHARS)))
    return events


def session_events(transcript: Path) -> list[Event]:
    events = transcript_events(transcript, is_main=True)
    for agent_transcript in sorted(transcript.with_suffix("").glob("subagents/*.jsonl")):
        events += [(s, f"agent {kind}", text) for s, kind, text in transcript_events(agent_transcript, False)]
    unique = list(dict.fromkeys(events))  # a notification can arrive both queued and delivered
    return sorted(unique, key=lambda event: event[0])


def render(transcript: Path, events: list[Event]) -> str:
    prompts = [e for e in events if e[1] == "prompt"]
    counts = {kind: sum(1 for e in events if e[1].endswith(kind)) for kind in ("compaction", "git", "tests")}
    lines = [
        f"transcript: {transcript}",
        f"started: {local_time(events[0][0]) if events else 'unknown'}",
        f"last prompt: {local_time(prompts[-1][0]) if prompts else 'none'}",
        f"prompts: {len(prompts)}, compactions: {counts['compaction']}, "
        f"git actions: {counts['git']}, test summaries: {counts['tests']}",
        "",
    ]
    for stamp, kind, text in events:
        if kind == "prompt":
            # The first prompt is the original intent; print it whole.
            body = flat(text) if prompts and (stamp, kind, text) == prompts[0] else clip_middle(text, PROMPT_CHARS)
            lines.append(f"[{local_time(stamp)}] LEO: {body}")
        elif kind == "compaction":
            lines.append(f"[{local_time(stamp)}] COMPACTION, intent as summarized: {clip(text, INTENT_CHARS)}")
        else:
            lines.append(f"[{local_time(stamp)}] {kind}: {text}")
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    session = argv[1] if len(argv) > 1 else os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not session:
        raise SystemExit("CLAUDE_CODE_SESSION_ID is unset; pass a session id prefix")
    transcript = find_transcript(session)
    print(render(transcript, session_events(transcript)))


if __name__ == "__main__":
    main(sys.argv)
