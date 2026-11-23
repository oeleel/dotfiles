#!/usr/bin/env python3
"""Deterministic steps for the meeting-to-actions skill. The model reads the meeting; these
commands fetch and check, so nothing here depends on judgment.

  paste --list [--session ID]       every paste Leo made in the session, with the words after it
  paste --out FILE [--index N]      save one paste verbatim (default: the longest paste of the
                                    latest prompt that has one); refuses a path git could publish
  profile FILE                      speaker labels and word shares, header, timestamps, end check
  records [REPO]                    the repo's meeting rules, meeting folders, todo files, ignores
  todo FILE                         done/total per section and every open item, with its owner
  quotes NOTE SOURCE [SOURCE ...]    every quoted phrase in NOTE must appear word for word in a
                                    source (the transcript, or a page Leo was given)

Default session: $CLAUDE_CODE_SESSION_ID (Claude Code sets it in every Bash call).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
# The harness writes the closing tag with the id too: </pasted_content id="c366">.
PASTE_RE = re.compile(r"<pasted_content[^>]*>\n?(.*?)\n?</pasted_content[^>]*>", re.S)
LABEL_CHARS = 60  # Leo names a paste in the words after it: "[paste] sept 9 [paste] aug 27"
PREVIEW_CHARS = 70
RULE_LINE_CHARS = 160
MAX_RULE_LINES_PER_FILE = 12
NEWEST_FILES_SHOWN = 5
TODO_FILES_SHOWN = 3
OPEN_ITEM_CHARS = 140
SEARCH_DEPTH = 4
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "dist",
        "build",
        ".next",
        ".nah",
    }
)
RULE_FILE_NAMES = frozenset({"CLAUDE.md", "AGENTS.md"})
ROOT_RULE_FILE_NAMES = RULE_FILE_NAMES | {
    "README.md"
}  # a notes folder keeps its rules in its README
RULE_TOPIC_RE = re.compile(
    r"meeting|transcript|\btodo|action item", re.I
)  # not "minutes": README time estimates
IGNORE_TOPIC_RE = re.compile(r"meeting|transcript|minutes|todo|notes|private", re.I)
MEETING_DIR_RE = re.compile(r"^(meetings?|meeting[-_ ]notes|minutes|transcripts?)$", re.I)
TODO_FILE_RE = re.compile(r"^todo.*\.md$", re.I)

HEADER_KEYS = frozenset(
    {
        "date",
        "time",
        "title",
        "meeting title",
        "meeting participants",
        "participants",
        "attendees",
        "transcript",
        "agenda",
        "summary",
        "notes",
        "link",
        "http",
        "https",
    }
)
HEADER_LINES = 8
SPEAKER_RE = re.compile(r"^\s*([A-Za-z][\w .'()-]{0,40}?):\s")
TIMESTAMP_RE = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s")
# Labels that do not say who spoke. "(You)" is the recorder, usually Leo, but say so.
GENERIC_LABEL_RE = re.compile(r"^(me|them|you|unknown|speaker \d+|.*\(you\))$", re.I)
MIN_TURNS_SHOWN = 2
GOODBYE_RE = re.compile(
    r"\b(bye|goodbye|see you|talk (to you )?(soon|later)|take care|drive safe)\b", re.I
)
TAIL_LINES_ALLOWED = 10  # lines after the last goodbye before the end looks like a second recording
EDGE_LINES = 2

HEADING_RE = re.compile(r"^#{1,4}\s+(.*)$")
ITEM_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$")
WAITING_SECTION_RE = re.compile(r"waiting", re.I)
ADDED_RE = re.compile(r"\(added\)", re.I)
LEO_ITEM_RE = re.compile(r"^(\*\*)?(leo\b|ask\b)", re.I)

# An opening mark is not glued to a word on its left and a quote does not start or end with a
# space, so the gap between two short quotes ("Me" ... "Them") is not read as a quote.
QUOTE_RE = re.compile(r"(?<!\w)[\"“](\S[^\"“”\n]{6,298}\S)[\"”](?!\w)")
TAG_RE = re.compile(r"<[^>]+>")
ELLIPSIS_RE = re.compile(r"\.\.\.|…")
MIN_QUOTE_WORDS = 3
WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True, slots=True)
class Paste:
    index: int
    stamp: str
    text: str
    label: str
    prompt_number: int


@dataclass(frozen=True, slots=True)
class TodoItem:
    line: int
    done: bool
    text: str
    section: str
    owner: str


def fail(message: str) -> None:
    raise SystemExit(f"meeting.py: {message}")


def flat(text: str) -> str:
    return " ".join(text.split())


def clip(text: str, limit: int) -> str:
    text = flat(text)
    return text if len(text) <= limit else text[:limit] + "..."


def local_time(iso_stamp: str) -> str:
    if not iso_stamp:
        return "unknown"
    return (
        datetime.fromisoformat(iso_stamp.replace("Z", "+00:00"))
        .astimezone()
        .strftime("%Y-%m-%d %H:%M %z")
    )


# ---------------------------------------------------------------- paste


def find_transcript(session_prefix: str) -> Path:
    if not session_prefix:
        fail(
            "no session id: pass --session or run inside Claude Code "
            "($CLAUDE_CODE_SESSION_ID is empty)"
        )
    matches = sorted(PROJECTS_DIR.glob(f"*/{session_prefix}*.jsonl"))
    if not matches:
        fail(f"no transcript for session {session_prefix!r} under {PROJECTS_DIR}")
    if len(matches) > 1:
        fail(
            f"session prefix {session_prefix!r} is ambiguous: {', '.join(p.stem for p in matches)}"
        )
    return matches[0]


def prompt_text(entry: dict) -> str:
    """Text Leo typed or queued. Prompt snapshots and sidechains repeat old text: skip them."""
    if entry.get("isSidechain") or entry.get("isMeta"):
        return ""
    if entry.get("type") == "attachment":
        attachment = entry.get("attachment") or {}
        return attachment.get("prompt", "") if attachment.get("type") == "queued_command" else ""
    if entry.get("type") != "user":
        return ""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def read_pastes(path: Path) -> list[Paste]:
    pastes: list[Paste] = []
    seen: set[str] = set()
    prompt_number = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        text = prompt_text(entry)
        matches = list(PASTE_RE.finditer(text))
        digests = [hashlib.sha256(m.group(1).encode()).hexdigest() for m in matches]
        if all(digest in seen for digest in digests):  # also: a queued prompt logged again
            continue
        prompt_number += 1
        for position, (match, digest) in enumerate(zip(matches, digests, strict=True)):
            if digest in seen:
                continue
            seen.add(digest)
            label_end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            label = clip(text[match.end() : label_end], LABEL_CHARS)
            pastes.append(
                Paste(len(pastes), entry.get("timestamp", ""), match.group(1), label, prompt_number)
            )
    return pastes


def default_paste(pastes: list[Paste]) -> Paste:
    """The transcript is the longest paste of Leo's latest prompt that has pastes."""
    latest = max(p.prompt_number for p in pastes)
    return max((p for p in pastes if p.prompt_number == latest), key=lambda p: len(p.text))


def git_root(directory: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def is_ignored(repo: Path, path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "-q", str(path)], capture_output=True
    )
    return result.returncode == 0


def nearest_existing(path: Path) -> Path:
    for candidate in [path, *path.parents]:
        if candidate.exists():
            return candidate if candidate.is_dir() else candidate.parent
    return Path("/")


def check_local_only(path: Path) -> None:
    """A transcript can hold client or personal detail. Inside a repo, only an ignored path is safe:
    the Stop hook commits leftovers on feature branches, and /handoff pushes them."""
    repo = git_root(nearest_existing(path))
    if repo and not is_ignored(repo, path):
        fail(
            f"refusing to write {path}: it is inside the git repo {repo} and not ignored, "
            "so a commit "
            f"could publish the transcript. Use an ignored folder or {repo}-private/."
        )


def save_paste(paste: Paste, out: Path) -> None:
    out = out.expanduser().resolve()
    check_local_only(out)
    if out.exists() and out.read_text(encoding="utf-8") != paste.text:
        fail(f"{out} exists with different content; choose another name")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(paste.text, encoding="utf-8")
    digest = hashlib.sha256(paste.text.encode()).hexdigest()[:12]
    print(f"saved paste {paste.index} -> {out}")
    print(
        f"  {len(paste.text)} chars, {len(paste.text.splitlines())} lines, sha256 {digest}, "
        f"pasted {local_time(paste.stamp)}"
    )


def run_paste(args: argparse.Namespace) -> None:
    pastes = read_pastes(find_transcript(args.session))
    if not pastes:
        fail(f"session {args.session!r} has no pasted text")
    if args.list:
        for p in pastes:
            print(
                f"[{p.index}] prompt {p.prompt_number}, {local_time(p.stamp)}, {len(p.text)} chars"
            )
            print(f"    starts: {clip(p.text, PREVIEW_CHARS)}")
            print(f"    after:  {p.label or '-'}")
        return
    if not args.out:
        fail("pass --list or --out FILE")
    if args.index is None:
        paste = default_paste(pastes)
    elif 0 <= args.index < len(pastes):
        paste = pastes[args.index]
    else:
        fail(f"--index {args.index} is out of range: the session has pastes 0 to {len(pastes) - 1}")
    save_paste(paste, Path(args.out))


# ---------------------------------------------------------------- profile


def speaker_label(line: str) -> str | None:
    if TIMESTAMP_RE.match(line):
        return None
    found = SPEAKER_RE.match(line)
    if not found:
        return None
    label = found.group(1).strip()
    if label.lower() in HEADER_KEYS or len(label.split()) > 4:
        return None
    return label


def run_profile(args: argparse.Namespace) -> None:
    path = Path(args.file).expanduser()
    if not path.is_file():
        fail(f"no such file: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        fail(f"{path} is empty")
    print(f"{path}: {len(text)} chars, {len(lines)} lines, {len(text.split())} words")

    header = [
        line.strip()
        for line in lines[:HEADER_LINES]
        if line.split(":", 1)[0].strip().lower() in HEADER_KEYS
    ]
    print(
        "header: "
        + (
            " | ".join(header)
            if header
            else "none (date the meeting from Leo's words or the paste time)"
        )
    )

    turns: Counter[str] = Counter()
    words: Counter[str] = Counter()
    current = ""
    for line in lines:
        label = speaker_label(line)
        if label:
            current = label
            turns[label] += 1
        if current:
            words[current] += len(line.split())
    shown = [label for label, count in turns.most_common() if count >= MIN_TURNS_SHOWN]
    total_words = sum(words[label] for label in shown) or 1
    if shown:
        print("speakers (turns, share of words):")
        for label in shown:
            print(f"  {label}: {turns[label]} turns, {round(100 * words[label] / total_words)}%")
        generic = [label for label in shown if GENERIC_LABEL_RE.match(label)]
        if generic:
            print(
                f"  generic labels: {', '.join(generic)} - state who each one is and the evidence"
            )
    else:
        print("speakers: no labels found (one speaker, such as a Loom, or an unlabeled paste)")

    stamps = [m.group(1) for m in map(TIMESTAMP_RE.match, lines) if m]
    if stamps:
        print(f"timestamps: {len(stamps)} lines, {stamps[0]} to {stamps[-1]}")

    goodbyes = [n for n, line in enumerate(lines, 1) if GOODBYE_RE.search(line)]
    if not goodbyes:
        print("end: no goodbye found - the paste may be cut short")
    elif len(lines) - goodbyes[-1] > TAIL_LINES_ALLOWED:
        print(
            f"end: last goodbye at line {goodbyes[-1]}, {len(lines) - goodbyes[-1]} lines follow "
            "it - check they belong to the meeting"
        )
    else:
        print(f"end: last goodbye at line {goodbyes[-1]} of {len(lines)}")
    print("first: " + " / ".join(clip(line, PREVIEW_CHARS) for line in lines[:EDGE_LINES]))
    print("last:  " + " / ".join(clip(line, PREVIEW_CHARS) for line in lines[-EDGE_LINES:]))


# ---------------------------------------------------------------- records


def walk(root: Path) -> list[tuple[Path, list[str]]]:
    found = []
    for directory, subdirs, files in os.walk(root):
        depth = len(Path(directory).relative_to(root).parts)
        subdirs[:] = sorted(d for d in subdirs if d not in SKIP_DIRS and depth < SEARCH_DEPTH)
        found.append((Path(directory), sorted(files)))
    return found


def count_items(path: Path) -> tuple[int, int]:
    items = [
        ITEM_RE.match(line)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
    ]
    marks = [m.group(1) for m in items if m]
    return sum(1 for mark in marks if mark in "xX"), len(marks)


def date_of(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def print_rule_lines(root: Path, tree: list[tuple[Path, list[str]]]) -> None:
    print("rules that mention meetings, transcripts or todos:")
    shown = 0
    for directory, files in tree:
        for name in files:
            allowed = ROOT_RULE_FILE_NAMES if directory == root else RULE_FILE_NAMES
            if name not in allowed:
                continue
            path = directory / name
            hits = [
                (n, line)
                for n, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                )
                if RULE_TOPIC_RE.search(line)
            ]
            for n, line in hits[:MAX_RULE_LINES_PER_FILE]:
                print(f"  {path.relative_to(root)}:{n}: {clip(line, RULE_LINE_CHARS)}")
            shown += len(hits)
    if not shown:
        print("  none")


def exclude_file(root: Path) -> Path:
    """In a worktree .git is a file; git resolves the shared info/exclude."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "info/exclude",
        ],
        capture_output=True,
        text=True,
    )
    return (
        Path(result.stdout.strip())
        if result.returncode == 0
        else root / ".git" / "info" / "exclude"
    )


def shown_path(root: Path, path: Path) -> str:
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def print_ignore_lines(root: Path) -> None:
    print("ignore rules on that topic:")
    shown = 0
    for path in (root / ".gitignore", exclude_file(root)):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for n, line in enumerate(lines, 1):
            if line.strip() and not line.startswith("#") and IGNORE_TOPIC_RE.search(line):
                reason = lines[n - 2].strip() if n >= 2 and lines[n - 2].startswith("#") else ""
                print(
                    f"  {shown_path(root, path)}:{n}: {line.strip()}"
                    + (f"   ({reason})" if reason else "")
                )
                shown += 1
    if not shown:
        print("  none")


def visibility(root: Path, folder: Path, in_git: bool) -> str:
    if not in_git:
        return "outside git, local only"
    if is_ignored(root, folder):
        return "ignored, local only"
    return "tracked by git, pushed with the repo"


def print_folders(root: Path, tree: list[tuple[Path, list[str]]], in_git: bool) -> list[Path]:
    """Print each meeting folder; return the ones that hold files."""
    print("meeting folders:")
    used = []
    folders = [d for d, _ in tree if MEETING_DIR_RE.match(d.name)]
    for folder in folders:
        files = sorted(
            (p for p in folder.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        print(
            f"  {folder.relative_to(root)}/ - {len(files)} files, "
            f"{visibility(root, folder, in_git)}"
        )
        for file in files[:NEWEST_FILES_SHOWN]:
            print(f"    {date_of(file)}  {file.name}")
        if files:
            used.append(folder)
    if not folders:
        print("  none")
    return used


def print_todos(root: Path, tree: list[tuple[Path, list[str]]]) -> None:
    print("todo files (newest first):")
    todos = sorted(
        (d / name for d, files in tree for name in files if TODO_FILE_RE.match(name)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for todo in todos[:TODO_FILES_SHOWN]:
        done, total = count_items(todo)
        print(f"  {date_of(todo)}  {todo.relative_to(root)}  {done}/{total} done")
    if not todos:
        print("  none")


def print_records(root: Path) -> list[Path]:
    """Print the record layout of one folder; return its meeting folders that hold files."""
    in_git = git_root(root) is not None  # a notes folder can sit inside another repo
    tree = walk(root)
    print_rule_lines(root, tree)
    if in_git:
        print_ignore_lines(root)
    used = print_folders(root, tree, in_git)
    print_todos(root, tree)
    return used


def print_conflict(used: list[Path]) -> None:
    # Two folders that both hold notes leave the record ambiguous; the skill has Leo settle it.
    if len(used) > 1:
        print(f"\nconflict: meeting notes in {len(used)} places: {', '.join(str(f) for f in used)}")


def run_records(args: argparse.Namespace) -> None:
    start = Path(args.repo).expanduser().resolve()
    if not start.is_dir():
        fail(f"no such directory: {start}")
    root = git_root(start) or start
    print(f"repo: {root}" + ("" if git_root(start) else " (not a git repo)"))
    used = print_records(root)
    # Leo's rule: private notes about a shared repo live in a <repo>-private sibling folder.
    private = root.parent / f"{root.name}-private"
    if not private.is_dir():
        print(f"\nprivate sibling: {private} does not exist")
        print_conflict(used)
        return
    print(
        f"\nprivate sibling: {private}"
        + (" (own git repo)" if git_root(private) == private else " (not a git repo)")
    )
    used += print_records(private)
    print_conflict(used)


# ---------------------------------------------------------------- todo


def read_todo(path: Path) -> list[TodoItem]:
    items: list[TodoItem] = []
    section = "(top)"
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        heading = HEADING_RE.match(line)
        if heading:
            section = heading.group(1).strip()
            continue
        item = ITEM_RE.match(line)
        if not item:
            continue
        text = item.group(2).strip()
        if WAITING_SECTION_RE.search(section):
            owner = "others"
        elif LEO_ITEM_RE.match(text):
            owner = "Leo"
        elif ADDED_RE.search(text):
            owner = "proposed"  # the agent's own idea, not an ask: it waits for Leo's yes
        else:
            owner = "agent"
        items.append(TodoItem(n, item.group(1) in "xX", text, section, owner))
    return items


def run_todo(args: argparse.Namespace) -> None:
    path = Path(args.file).expanduser()
    if not path.is_file():
        fail(f"no such file: {path}")
    items = read_todo(path)
    if not items:
        fail(f"{path} has no checkbox items (- [ ] or - [x])")
    sections = list(dict.fromkeys(item.section for item in items))
    for section in sections:
        in_section = [item for item in items if item.section == section]
        print(f"{section}: {sum(item.done for item in in_section)}/{len(in_section)} done")
    open_items = [item for item in items if not item.done]
    owners = Counter(item.owner for item in open_items)
    print(
        f"total: {len(items) - len(open_items)}/{len(items)} done; open: "
        + ", ".join(f"{owners[o]} {o}" for o in ("agent", "proposed", "Leo", "others") if owners[o])
    )
    for item in open_items:
        print(f"  L{item.line} [{item.owner}] {clip(item.text, OPEN_ITEM_CHARS)}")


# ---------------------------------------------------------------- quotes


def normalized(text: str) -> str:
    """Words only: a quote may drop a comma or change case, never a word."""
    return " ".join(WORD_RE.findall(text.lower().replace("’", "'").replace("‘", "'")))


def source_words(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        text = TAG_RE.sub(" ", text)
    return normalized(text)


def run_quotes(args: argparse.Namespace) -> None:
    note = Path(args.note).expanduser()
    sources = [Path(source).expanduser() for source in args.sources]
    for path in (note, *sources):
        if not path.is_file():
            fail(f"no such file: {path}")
    texts = [source_words(path) for path in sources]
    checked, missing = 0, []
    for n, line in enumerate(note.read_text(encoding="utf-8").splitlines(), 1):
        for match in QUOTE_RE.finditer(line):
            parts = [
                part for part in (normalized(p) for p in ELLIPSIS_RE.split(match.group(1))) if part
            ]
            if len(" ".join(parts).split()) < MIN_QUOTE_WORDS:
                continue
            checked += 1
            if not any(all(part in text for part in parts) for text in texts):
                missing.append(f'  L{n}: "{match.group(1)}"')
    names = ", ".join(path.name for path in sources)
    print(f"{checked - len(missing)}/{checked} quotes found word for word in {names}")
    if missing:
        print("not found (copy the exact words, mark a cut with ..., or drop the quote marks):")
        print("\n".join(missing))
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    paste = commands.add_parser("paste")
    paste.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    paste.add_argument("--list", action="store_true")
    paste.add_argument("--out")
    paste.add_argument("--index", type=int)
    commands.add_parser("profile").add_argument("file")
    commands.add_parser("records").add_argument("repo", nargs="?", default=".")
    commands.add_parser("todo").add_argument("file")
    quotes = commands.add_parser("quotes")
    quotes.add_argument("note")
    quotes.add_argument("sources", nargs="+")
    args = parser.parse_args(argv)
    runners = {
        "paste": run_paste,
        "profile": run_profile,
        "records": run_records,
        "todo": run_todo,
        "quotes": run_quotes,
    }
    runners[args.command](args)


if __name__ == "__main__":
    main()
