#!/usr/bin/env python3
"""Deterministic steps of the coverage-audit skill.

source  Save every paste of a Claude Code session to its own file, word for word. The
        audit then quotes the real source, and `check` can test each quote against it.
check   Check an audit file before Leo sees it: every status is one of the five, every
        quote is word for word in the source, every evidence path and commit exists,
        every covered row cites evidence, and every open row has a row in the gaps table.

The model writes the audit; this script only catches what a model gets wrong without
noticing: a paraphrase shown as a quote, a path that does not exist, a gap with no fill.

Usage:
  audit.py source OUT_DIR [--session PREFIX]
  audit.py check AUDIT_MD [--source FILE]... [--root DIR]...
Default session: $CLAUDE_CODE_SESSION_ID (set by Claude Code in every Bash call).
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
STATUSES = ("covered", "partial", "missing", "unverified", "n/a")
OPEN_STATUSES = frozenset({"partial", "missing", "unverified"})  # each needs a row in the gaps table
WAITS_ON = frozenset({"me", "you", "external"})  # the same three owners the recap skill uses
# Extensions that make a bare token a file path. Domains (.ai, .com, .io) are left out on purpose.
FILE_EXTENSIONS = frozenset(
    "md txt pdf pptx docx xlsx csv tsv json jsonl yaml yml toml ini html htm css js mjs cjs ts tsx jsx "
    "py ipynb sh zsh sql r rmd png jpg jpeg svg gif mp4 env lock cfg".split()
)
PREVIEW_CHARS = 80
SHOWN_UNCHECKED = 12

# The harness writes the closing tag with the id too: </pasted_content id="c366">.
PASTE_RE = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)
QUOTE_RE = re.compile(r'"([^"]+)"|“([^”]+)”')
ELLIPSIS_RE = re.compile(r"\[\.\.\.\]|\.\.\.|…")
WORD_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
BACKTICK_RE = re.compile(r"`([^`]+)`")
SHA_RE = re.compile(r"[0-9a-f]{7,40}")
LINE_SUFFIX_RE = re.compile(
    r"(?:::[\w\[\]-]+|:(\d+)(?:-(\d+))?|#[\w-]*)$"
)  # file.py::test, file.md:12-30, page.html#part
HEADLINE_RE = re.compile(r"\b(\d+) asks?:(.*)$", re.M)  # "No. 24 asks: 2 covered, 11 partial, ..."
HEADLINE_COUNT_RE = re.compile(r"(\d+) (covered|partial|missing|unverified|n/a)\b")
TARGET_RE = re.compile(r"^.*checked against:(.*)$", re.I | re.M)
# A place inside the named target ("Slide 7", "p. 4", "section 3.1") also points at evidence.
LOCATION_RE = re.compile(r"\b(?:slides?|p\.|pages?|sections?|§|rows?|lines?|steps?|findings?|items?|questions?)\s*\d+", re.I)
IMAGE_SUFFIXES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
ID_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b|\s)\s*")
PART_RE = re.compile(r"^([A-Za-z]*\d+)[a-z]$")  # 5a -> 5, L3b -> L3


@dataclass(frozen=True, slots=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def column(self, prefix: str) -> list[int]:
        return [i for i, name in enumerate(self.header) if name.lower().startswith(prefix)]


# ---------------------------------------------------------------- source


def find_transcript(session_prefix: str) -> Path:
    matches = list(PROJECTS_DIR.glob(f"*/{session_prefix}*.jsonl"))
    if not matches:
        raise SystemExit(f"no transcript for session {session_prefix!r} under {PROJECTS_DIR}")
    if len(matches) > 1:
        raise SystemExit(f"session prefix {session_prefix!r} is ambiguous: {', '.join(p.stem for p in matches)}")
    return matches[0]


def message_text(entry: dict) -> str:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def session_pastes(transcript: Path) -> list[tuple[str, str]]:
    """Every distinct paste Leo typed, in time order, as (UTC timestamp, text)."""
    pastes: dict[str, str] = {}
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line cut off by a crash; the rest of the transcript still counts
        if entry.get("type") != "user" or entry.get("isMeta"):
            continue
        for body in PASTE_RE.findall(message_text(entry)):
            pastes.setdefault(body.strip("\n"), entry.get("timestamp", ""))
    return [(stamp, body) for body, stamp in pastes.items()]


def session_images(transcript: Path) -> list[tuple[str, str, bytes]]:
    """Every distinct image Leo pasted (a rubric or report screenshot), as (UTC timestamp,
    media type, bytes). Images inside tool results are the agent's own screenshots: skipped."""
    images: dict[str, tuple[str, str]] = {}
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") != "user" or entry.get("isMeta") or not isinstance(content, list):
            continue
        for block in content:
            source = block.get("source") if isinstance(block, dict) and block.get("type") == "image" else None
            if isinstance(source, dict) and source.get("type") == "base64" and source.get("data"):
                images.setdefault(source["data"], (entry.get("timestamp", ""), source.get("media_type", "image/png")))
    return [(stamp, media, base64.b64decode(data)) for data, (stamp, media) in images.items()]


def save_images(images: list[tuple[str, str, bytes]], out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for number, (stamp, media, data) in enumerate(images, start=1):
        path = out_dir / f"image-{number}{IMAGE_SUFFIXES.get(media, '.png')}"
        path.write_bytes(data)
        lines.append(f"{path}  {stamp[:16]}  {len(data)} bytes  image: read it and transcribe it to image-{number}.txt")
    return lines


def save_pastes(pastes: list[tuple[str, str]], out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for number, (stamp, body) in enumerate(pastes, start=1):
        path = out_dir / f"paste-{number}.txt"
        path.write_text(body + "\n", encoding="utf-8")
        preview = " ".join(body.split())[:PREVIEW_CHARS]
        lines.append(f"{path}  {stamp[:16]}  {len(body)} chars  {preview}")
    return lines


# ---------------------------------------------------------------- check


def split_cells(line: str) -> tuple[str, ...]:
    """Split a table row on | outside backticks; \\| is a literal pipe."""
    cells, current, in_code, i = [], [], False, 0
    body = line.strip().removeprefix("|")
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    while i < len(body):
        char = body[i]
        if char == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            current.append("|")
            i += 2
            continue
        if char == "`":
            in_code = not in_code
        if char == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        i += 1
    cells.append("".join(current).strip())
    return tuple(cells)


def parse_tables(text: str) -> list[Table]:
    tables, block = [], []
    for line in [*text.splitlines(), ""]:
        if line.strip().startswith("|"):
            block.append(line)
            continue
        if len(block) >= 2 and set(block[1].replace("|", "").strip()) <= set("-: "):
            header = tuple(cell.strip("*_ ").strip() for cell in split_cells(block[0]))
            tables.append(Table(header, tuple(split_cells(row) for row in block[2:])))
        block = []
    return tables


def find_table(tables: list[Table], prefix: str) -> Table | None:
    for table in tables:
        if table.column(prefix):
            return table
    return None


def words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower().replace("’", "'").replace("‘", "'"))


def quote_fragments(cell: str) -> list[str]:
    fragments = []
    for match in QUOTE_RE.finditer(cell):
        quote = match.group(1) or match.group(2)
        fragments.extend(part for part in ELLIPSIS_RE.split(quote) if words(part))
    return fragments


def parse_status(cell: str) -> str | None:
    plain = cell.strip("*_` ").lower()
    for status in STATUSES:
        if plain == status or plain.startswith((status + " ", status + ",")):
            return status
    return None


def has_known_extension(token: str) -> bool:
    name = token.rstrip("/").rsplit("/", 1)[-1]
    return "." in name.lstrip(".") and name.rsplit(".", 1)[-1].lower() in FILE_EXTENSIONS


def resolve_path(token: str, roots: list[Path]) -> Path | None:
    candidate = Path(token).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for root in roots:
        if (root / candidate).exists():
            return root / candidate
    return None


def is_path_like(token: str, roots: list[Path]) -> bool:
    if token.startswith(("/", "~", "./", "../")) or has_known_extension(token):
        return True
    # A bare dir/name counts only when its first part exists, so r/ClaudeAI and github.com/x do not.
    return "/" in token and any((root / token.split("/", 1)[0]).exists() for root in roots)


def commit_exists(sha: str, roots: list[Path]) -> bool:
    for root in roots:
        probe = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, check=False
        )
        if probe.returncode == 0:
            return True
    return False


def check_evidence(token: str, roots: list[Path]) -> str:
    """Return 'ok', 'unchecked', or a problem sentence for one backticked evidence token."""
    token = token.strip()
    if token.startswith(("http://", "https://")) or (" " in token and not resolve_path(token, roots)):
        return "unchecked"
    if SHA_RE.fullmatch(token):
        if commit_exists(token, roots):
            return "ok"
        if token.isdigit():
            return "unchecked"  # a number such as 20261122, not a commit
        return f"commit `{token}` is not in {', '.join(map(str, roots))}"
    suffix = LINE_SUFFIX_RE.search(token)
    path = token[: suffix.start()] if suffix else token
    if not is_path_like(path, roots):
        return "unchecked"
    found = resolve_path(path, roots)
    if found is None:
        return f"path `{token}` does not exist under {', '.join(map(str, roots))}"
    last_line = int(suffix.group(2) or suffix.group(1)) if suffix and suffix.group(1) else 0
    if last_line and (
        found.is_dir() or last_line > len(found.read_text(encoding="utf-8", errors="replace").splitlines())
    ):
        return f"`{token}` points past the end of {found}"
    return "ok"


def row_id(table: Table, row: tuple[str, ...]) -> str:
    columns = table.column("#") or [0]
    return row[columns[0]].strip("*_ ") if columns[0] < len(row) else ""


def first_word(cell: str) -> str:
    plain = cell.strip("*_` ").split(":")[0].split()
    return plain[0].lower().strip("*_,") if plain else ""


def gap_ids(cell: str) -> set[str]:
    return {part.strip("*_ ") for part in ID_SPLIT_RE.split(cell) if part.strip("*_ ")}


@dataclass
class Tally:
    """What the rows add up to, for the summary and the gaps check."""

    counts: list[Counter[str]]
    open_ids: set[str] = field(default_factory=set)
    unchecked: list[str] = field(default_factory=list)
    checked: int = 0
    fragments: int = 0


def check_row(asks: Table, row: tuple[str, ...], sources: list[str], roots: list[Path], tally: Tally) -> list[str]:
    """Problems with one ask row; adds its statuses and evidence to the tally."""
    rid = row_id(asks, row)
    cells = list(row) + [""] * (len(asks.header) - len(row))
    problems, statuses = [], []
    for position, column in enumerate(asks.column("status")):
        status = parse_status(cells[column])
        if status is None:
            problems.append(f"row {rid}: status {cells[column]!r} is not one of {', '.join(STATUSES)}")
            continue
        tally.counts[position][status] += 1
        statuses.append(status)
    if OPEN_STATUSES & set(statuses):
        tally.open_ids.add(rid)
    if sources:
        fragments = [f for column in asks.column("ask") for f in quote_fragments(cells[column])]
        tally.fragments += len(fragments)
        if not fragments:
            problems.append(f"row {rid}: the ask quotes no source words")
        for fragment in fragments:
            if not any(" " + " ".join(words(fragment)) + " " in source for source in sources):
                problems.append(f"row {rid}: quote {fragment.strip()!r} is not word for word in the source")
    evidence = " ".join(cells[column] for column in asks.column("evidence"))
    tokens = BACKTICK_RE.findall(evidence)
    if "covered" in statuses and not tokens and not LOCATION_RE.search(evidence):
        problems.append(
            f"row {rid}: covered, but the evidence names no file, commit, command, link or place (slide, page, section)"
        )
    for token in tokens:
        verdict = check_evidence(token, roots)
        if verdict == "ok":
            tally.checked += 1
        elif verdict == "unchecked":
            tally.unchecked.append(token)
        else:
            problems.append(f"row {rid}: {verdict}")
    return problems


def preamble(text: str) -> str:
    """The lines above the first table, where the headline and the target line live."""
    lines = text.splitlines()
    first_table = next((i for i, line in enumerate(lines) if line.strip().startswith("|")), len(lines))
    return "\n".join(lines[:first_table])


def check_headline(text: str, total: int, counts: Counter[str]) -> list[str]:
    """The headline Leo reads first must match the table, so a miscount cannot reach him."""
    match = HEADLINE_RE.search(preamble(text))
    if match is None:
        return ["no headline: start with '<Yes | No | Mostly>. <N> asks: <a> covered, ...'"]
    problems = [] if int(match.group(1)) == total else [f"headline says {match.group(1)} asks, the table has {total}"]
    stated = {status: int(number) for number, status in HEADLINE_COUNT_RE.findall(match.group(2))}
    for status in STATUSES:
        if stated.get(status, 0) != counts[status]:
            problems.append(f"headline says {stated.get(status, 0)} {status}, the table has {counts[status]}")
    return problems


def check_target(text: str, roots: list[Path]) -> list[str]:
    """The 'Checked against:' line names the target; a slide or page number means nothing without it."""
    match = TARGET_RE.search(preamble(text))
    if match is None:
        return ["no target: add a 'Checked against: <file, repo or commit in backticks>' line"]
    verdicts = [check_evidence(token, roots) for token in BACKTICK_RE.findall(match.group(1))]
    problems = [f"target: {verdict}" for verdict in verdicts if verdict not in ("ok", "unchecked")]
    if "ok" not in verdicts and not problems:
        problems.append("target: the 'Checked against:' line names no file or commit that exists")
    return problems


def check_audit(text: str, sources: list[str], roots: list[Path]) -> tuple[list[str], list[str]]:
    """Return (problems, summary lines) for one audit file."""
    tables = parse_tables(text)
    asks = find_table(tables, "status")
    if asks is None:
        raise SystemExit("no asks table: expected a markdown table with a 'Status' column")
    if not asks.column("ask") or not asks.column("evidence"):
        raise SystemExit(f"the asks table needs 'Ask' and 'Evidence' columns; its header is {list(asks.header)}")
    status_columns = asks.column("status")
    source_words = [" " + " ".join(words(source)) + " " for source in sources]
    tally = Tally(counts=[Counter() for _ in status_columns])
    problems: list[str] = []
    ids = [row_id(asks, row) for row in asks.rows]
    for rid in sorted({rid for rid in ids if not rid or ids.count(rid) > 1}):
        problems.append(f"row {rid or '?'}: needs a unique id in the # column")
    for row in asks.rows:
        problems.extend(check_row(asks, row, source_words, roots, tally))
    if len(status_columns) == 1:
        problems.extend(check_headline(text, len(asks.rows), tally.counts[0]))
    problems.extend(check_target(text, roots))
    problems.extend(check_gaps(tables, tally.open_ids))
    unchecked = tally.unchecked
    summary = [
        f"asks: {len(asks.rows)}"
        + "".join(
            f"; {asks.header[column]}: " + ", ".join(f"{tally.counts[i][s]} {s}" for s in STATUSES)
            for i, column in enumerate(status_columns)
        ),
        f"evidence: {tally.checked} paths and commits exist; {len(unchecked)} not checkable"
        + (
            f" ({', '.join(unchecked[:SHOWN_UNCHECKED])}{' ...' if len(unchecked) > SHOWN_UNCHECKED else ''})"
            if unchecked
            else ""
        ),
        f"quotes: {tally.fragments} checked against {len(sources)} source file(s)"
        if sources
        else "quotes: not checked (no --source)",
    ]
    return problems, summary


def check_gaps(tables: list[Table], open_ids: set[str]) -> list[str]:
    gaps = find_table(tables, "waits on")
    if gaps is None:
        return (
            [f"no gaps table (a table with a 'Waits on' column) for rows {', '.join(sorted(open_ids))}"]
            if open_ids
            else []
        )
    problems, listed = [], set()
    waits_column = gaps.column("waits on")[0]
    for row in gaps.rows:
        ids = gap_ids(row_id(gaps, row))
        listed |= ids
        owner = first_word(row[waits_column] if waits_column < len(row) else "")
        if owner not in WAITS_ON:
            problems.append(
                f"gap {', '.join(sorted(ids))}: 'Waits on' must start with me, you or external, not {owner!r}"
            )
    for rid in sorted(open_ids):
        part = PART_RE.match(rid)
        if rid not in listed and not (part and part.group(1) in listed):
            problems.append(f"row {rid}: open, but no row in the gaps table says what fills it")
    return problems


# ---------------------------------------------------------------- main


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source", help="save every paste and pasted image of a session to OUT_DIR")
    source.add_argument("out_dir", type=Path)
    source.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    check = commands.add_parser("check", help="check an audit markdown file")
    check.add_argument("audit", type=Path)
    check.add_argument(
        "--source", type=Path, action="append", default=[], help="the ask source as text; repeat for several"
    )
    check.add_argument(
        "--root",
        type=Path,
        action="append",
        default=[],
        help="where evidence paths and commits live; repeat for several",
    )
    args = parser.parse_args(argv)

    if args.command == "source":
        if not args.session:
            raise SystemExit("no session: pass --session PREFIX or run inside Claude Code ($CLAUDE_CODE_SESSION_ID)")
        transcript = find_transcript(args.session)
        pastes, images = session_pastes(transcript), session_images(transcript)
        if not pastes and not images:
            raise SystemExit(f"session {args.session!r} has no pastes or images; save the source to a text file by hand")
        print("\n".join(save_pastes(pastes, args.out_dir) + save_images(images, args.out_dir)))
        return 0

    for path in [args.audit, *args.source]:
        if not path.is_file():
            raise SystemExit(f"not a file: {path}")
    roots = [root.expanduser().resolve() for root in args.root] or [Path.cwd()]
    sources = [path.read_text(encoding="utf-8") for path in args.source]
    problems, summary = check_audit(args.audit.read_text(encoding="utf-8"), sources, roots)
    print("\n".join(summary))
    for problem in problems:
        print(f"FAIL {problem}")
    print(f"result: {len(problems)} problem(s)" if problems else "result: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
