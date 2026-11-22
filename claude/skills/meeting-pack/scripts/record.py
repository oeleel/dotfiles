#!/usr/bin/env python3
"""Print the record a meeting pack is built from, for one repo and one window:
- the window start (the previous report or meeting note, or --since) and where it came from,
- meeting notes (the asks), newest first, with checkbox counts and the open items,
- previous report folders and their section ids,
- commits on HEAD in the window, each with its GitHub link and pushed state,
- other local branches that hold commits in the window,
- files changed in the window (result folders listed, the rest counted),
- the repo's test command, and the GitHub Pages base when the repo publishes one,
- gaps: what the record does not hold, so the page can say so instead of filling it.

The page states only what this record (and the files it points to) supports.

Usage: record.py [--repo DIR] [--since YYYY-MM-DD] [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

NOTES_DIRS = (
    "documentation/meeting-notes",
    "docs/meeting-notes",
    "docs/meetings",
    "context/meetings",
    "meeting-notes",
    "meetings",
)
REPORT_PARENTS = ("documentation/reports", "docs/reports", "reports")
RESULT_DIRS = ("experiments", "results", "reports", "outputs", "evals", "benchmarks")
AUTOSAVE_PREFIX = "checkpoint: WIP autosave"  # the Stop hook's commits; not deliverables
DEFAULT_WINDOW = timedelta(days=7)  # a weekly meeting, when no earlier artifact exists
MAX_NOTES = 5
MAX_COMMITS = 60
MAX_OPEN_ITEMS = 12
MAX_RESULT_PATHS = 40
ITEM_CHARS = 140
DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
CHECKBOX = re.compile(r"^\s*[-*] \[([ xX])\] (.+)$")
SECTION_ID = re.compile(r"^\s*- id:\s*([a-z0-9-]+)\s*$")
HEADING = re.compile(r"^#{2,3} (.+)$")
NUMBERED = re.compile(r"^\d+\. (.+)$")
COMMIT_TYPE = re.compile(r"^([a-z]+)[(:!]")
DELIVERABLE_TYPES = ("feat", "fix", "perf", "refactor")  # listed alone when the window holds too many commits
GITHUB_REMOTE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")


class RecordError(RuntimeError):
    """A git call failed or the input is not usable. The message names the bad value."""


@dataclass(frozen=True)
class Commit:
    sha: str
    day: str
    subject: str
    pushed: bool

    @property
    def autosave(self) -> bool:
        return self.subject.startswith(AUTOSAVE_PREFIX)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RecordError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return result.stdout


def parse_day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise RecordError(f"not a YYYY-MM-DD date: {text!r}") from exc


def date_in_name(name: str) -> date | None:
    match = DATE_IN_NAME.search(name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def github_base(remote_url: str) -> str | None:
    match = GITHUB_REMOTE.search(remote_url.strip())
    if not match:
        return None
    return f"https://github.com/{match.group(1)}/{match.group(2)}"


def pages_base(github: str | None, root: Path) -> str | None:
    """GitHub Pages serves the repo root when .nojekyll marks it; that is the only signal read."""
    if github is None:
        return None
    if not ((root / ".nojekyll").exists() or (root / "docs" / ".nojekyll").exists()):
        return None
    owner, name = github.removeprefix("https://github.com/").split("/")
    return f"https://{owner.lower()}.github.io/{name}/"


def checkbox_summary(text: str) -> tuple[int, list[str]]:
    done, open_items = 0, []
    for line in text.splitlines():
        match = CHECKBOX.match(line)
        if not match:
            continue
        if match.group(1) in "xX":
            done += 1
        else:
            open_items.append(match.group(2).strip())
    return done, open_items


def checkbox_sections(text: str) -> list[tuple[str, int, int]]:
    """(heading, done, total) for each ## or ### heading that holds checkboxes: one line per ask."""
    sections: list[tuple[str, int, int]] = []
    heading, done, total = "(no heading)", 0, 0
    for line in text.splitlines() + ["## (end)"]:
        if match := HEADING.match(line):
            if total:
                sections.append((heading, done, total))
            heading, done, total = match.group(1).strip(), 0, 0
        elif match := CHECKBOX.match(line):
            total += 1
            done += match.group(1) in "xX"
    return sections


def numbered_asks(text: str) -> list[str]:
    """Numbered items under a heading that names asks (Firehose notes list asks this way, no checkboxes)."""
    items, in_asks = [], False
    for line in text.splitlines():
        if match := HEADING.match(line):
            in_asks = "ask" in match.group(1).lower()
        elif in_asks and (match := NUMBERED.match(line)):
            items.append(match.group(1).strip())
    return items


def commit_types(commits: list[Commit]) -> dict[str, int]:
    """Commit counts by conventional type, most common first; a repo with bot commits shows them here."""
    counts: dict[str, int] = {}
    for commit in commits:
        match = COMMIT_TYPE.match(commit.subject)
        kind = match.group(1) if match else "(other)"
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def report_sections(report_yaml: str) -> list[str]:
    return [m.group(1) for line in report_yaml.splitlines() if (m := SECTION_ID.match(line))]


def find_reports(root: Path, today: date) -> list[Path]:
    """Dated report folders before today, newest first. A folder dated today is the one being built."""
    found = []
    for parent in REPORT_PARENTS:
        folder = root / parent
        if not folder.is_dir():
            continue
        for child in folder.iterdir():
            day = date_in_name(child.name)
            if child.is_dir() and day and day < today and DATE_IN_NAME.fullmatch(child.name):
                found.append(child)
    return sorted(found, key=lambda p: p.name, reverse=True)


def find_notes(root: Path) -> list[tuple[Path, date]]:
    """Meeting notes in the repo's notes folders and the <repo>-private sibling, newest first."""
    dirs = [root / d for d in NOTES_DIRS] + [root.parent / f"{root.name}-private"]
    notes = []
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.md"):
            day = date_in_name(path.name) or date.fromtimestamp(path.stat().st_mtime)
            notes.append((path, day))
    return sorted(notes, key=lambda item: (item[1], item[0].name), reverse=True)


@dataclass(frozen=True)
class Window:
    start: date
    basis: str
    base: str | None = None  # the previous report's last commit; the window is base..HEAD

    def log_range(self) -> list[str]:
        if self.base:
            return [f"{self.base}..HEAD"]
        return [f"--since={self.start.isoformat()} 00:00:00", "HEAD"]


def window_start(since: date | None, reports: list[Path], today: date, report_commit: tuple[str, date] | None) -> Window:
    """--since wins. Else the window opens after the previous report's last commit, so the
    previous meeting's own work stays out; by its folder date when that commit is not on HEAD."""
    if since is not None:
        return Window(since, "--since")
    if reports and report_commit:
        sha, day = report_commit
        return Window(day, f"after {sha[:7]}, the last commit to report {reports[0].name}", sha)
    if reports:
        return Window(parse_day(reports[0].name), f"previous report {reports[0].name}, by date")
    return Window(today - DEFAULT_WINDOW, f"default {DEFAULT_WINDOW.days} days, no earlier report")


def last_report_commit(repo: Path, folder: Path) -> tuple[str, date] | None:
    out = git(repo, "log", "-1", "--format=%H %cs", "--", str(folder)).split()
    if not out:
        return None
    ancestor = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", out[0], "HEAD"], capture_output=True)
    return (out[0], parse_day(out[1])) if ancestor.returncode == 0 else None


def commits_in(repo: Path, window: Window) -> list[Commit]:
    pushed = set(git(repo, "rev-list", "--remotes", f"--since={window.start.isoformat()} 00:00:00").split())
    out = git(repo, "log", "--no-merges", "--format=%H%x1f%ad%x1f%s", "--date=short", *window.log_range())
    commits = []
    for line in out.splitlines():
        sha, day, subject = line.split("\x1f", 2)
        commits.append(Commit(sha=sha, day=day, subject=subject, pushed=sha in pushed))
    return commits


def changed_paths(repo: Path, window: Window) -> list[str]:
    out = git(repo, "log", "--name-only", "--format=", *window.log_range())
    return sorted({line for line in out.splitlines() if line.strip()})


def split_paths(paths: list[str]) -> tuple[list[str], dict[str, int]]:
    """Result-folder paths in full; everything else counted by its first two path parts."""
    results, counts = [], {}
    for path in paths:
        parts = path.split("/")
        if any(part in RESULT_DIRS for part in parts[:-1]):
            results.append(path)
            continue
        key = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if len(parts) > 1 else "(root)")
        counts[key] = counts.get(key, 0) + 1
    return results, dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def other_branches(repo: Path, start: date) -> list[tuple[str, int]]:
    after = f"--since={start.isoformat()} 00:00:00"
    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    found = []
    for branch in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split():
        if branch == current:
            continue
        count = int(git(repo, "rev-list", "--count", "--no-merges", after, f"HEAD..{branch}").strip())
        if count:
            found.append((branch, count))
    return found


def test_command(root: Path) -> str | None:
    python = ".venv/bin/python" if (root / ".venv" / "bin" / "python").exists() else "python3"
    if (root / "pytest.ini").exists() or (root / "tests").is_dir() or "pytest" in _read(root / "pyproject.toml"):
        return f"{python} -m pytest -q"
    if '"test"' in _read(root / "package.json"):
        return "npm test"
    return None


def _read(path: Path) -> str:
    return path.read_text(errors="replace") if path.is_file() else ""


def is_ignored(repo: Path, path: Path) -> bool:
    result = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", str(path)], capture_output=True)
    return result.returncode == 0


def branch_state(repo: Path) -> str:
    dirty = len([line for line in git(repo, "status", "--porcelain").splitlines() if line.strip()])
    state = f"{dirty} uncommitted file(s)" if dirty else "clean"
    upstream = subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "@{u}"], capture_output=True, text=True)
    if upstream.returncode != 0:
        return f"{state}, no upstream"
    behind, ahead = git(repo, "rev-list", "--left-right", "--count", "@{u}...HEAD").split()
    return f"{state}, {ahead} ahead and {behind} behind {upstream.stdout.strip()}"


def render(repo: Path, since: date | None, today: date) -> str:
    root = Path(git(repo, "rev-parse", "--show-toplevel").strip())
    remote = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    github = github_base(remote.stdout) if remote.returncode == 0 else None
    pages = pages_base(github, root)
    reports = find_reports(root, today)
    window = window_start(since, reports, today, last_report_commit(root, reports[0]) if reports else None)
    start = window.start
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = git(root, "rev-parse", "--short", "HEAD").strip()
    gaps = []
    lines = [
        f"# Meeting record: {root.name} (today {today.isoformat()})",
        f"repo: {root}",
        f"branch: {branch} at {head}, {branch_state(root)}",
        f"window: since {start.isoformat()} ({window.basis})",
        f"github: {github or 'none (no GitHub origin: commit links unavailable)'}",
        f"pages: {pages or 'none found (no .nojekyll)'}",
        "",
        "## Asks: meeting notes, newest first",
    ]
    notes = find_notes(root)[:MAX_NOTES]
    if not notes:
        gaps.append(f"no meeting notes in {', '.join(NOTES_DIRS)} or ../{root.name}-private: ask Leo for the last meeting's asks")
    for path, day in notes:
        where = "local only" if not path.is_relative_to(root) or is_ignored(root, path) else "tracked"
        done, open_items = checkbox_summary(path.read_text(errors="replace"))
        tally = f": {done} done, {len(open_items)} open" if done or open_items else ""
        in_window = "" if day >= start else ", before the window"
        shown = path.relative_to(root) if path.is_relative_to(root) else path
        lines.append(f"- {shown} ({day.isoformat()}, {where}{in_window}){tally}")
        if day >= start:
            text = path.read_text(errors="replace")
            lines += [f"    {done_n}/{total} done: {heading[:ITEM_CHARS]}" for heading, done_n, total in checkbox_sections(text)]
            asks = numbered_asks(text)
            lines += [f"    ask {n}: {item[:ITEM_CHARS]}" for n, item in enumerate(asks, 1)]
        lines += [f"    open: {item[:ITEM_CHARS]}" for item in open_items[:MAX_OPEN_ITEMS]]
    lines += ["", "## Previous reports"]
    if not reports:
        lines.append("- none")
    for folder in reports[:3]:
        rel = folder.relative_to(root)
        sections = report_sections(_read(folder / "report.yaml"))
        lines.append(f"- {rel}" + (f" sections: {', '.join(sections)}" if sections else ""))
        if pages:
            lines.append(f"    page: {pages}{rel.as_posix()}/")
    commits = commits_in(root, window)
    real = [c for c in commits if not c.autosave]
    lines += ["", f"## Commits on HEAD in the window: {len(real)} (+{len(commits) - len(real)} autosaves not listed)"]
    if not real:
        gaps.append(f"no commits on HEAD in the window ({window.basis}): check the other branches below")
    if real:
        lines.append("by type: " + ", ".join(f"{k} {v}" for k, v in commit_types(real).items()))
    shown = real
    if len(real) > MAX_COMMITS:
        shown = [c for c in real if COMMIT_TYPE.match(c.subject) and COMMIT_TYPE.match(c.subject).group(1) in DELIVERABLE_TYPES]
        lines.append(f"(too many to list: only {', '.join(DELIVERABLE_TYPES)} commits shown; the rest are counted above)")
    for commit in shown[:MAX_COMMITS]:
        link = f" {github}/commit/{commit.sha}" if github else ""
        note = "" if commit.pushed else " (not pushed: the link 404s until it is)"
        lines.append(f"- {commit.day} {commit.sha[:7]} {commit.subject}{link}{note}")
    if len(shown) > MAX_COMMITS:
        lines.append(f"- ... {len(shown) - MAX_COMMITS} more")
    branches = other_branches(root, start)
    if branches:
        lines += ["", "## Other branches with commits in the window, not on HEAD",
                  "(a squash merge leaves its branch here too: compare content before counting it as more work)"]
        lines += [f"- {name}: {count}" for name, count in branches]
    results, counts = split_paths(changed_paths(root, window))
    lines += ["", "## Files changed in the window", "result folders:"]
    lines += [f"- {path}" for path in results[:MAX_RESULT_PATHS]] or ["- none"]
    if len(results) > MAX_RESULT_PATHS:
        lines.append(f"- ... {len(results) - MAX_RESULT_PATHS} more")
    lines.append("other folders (files changed): " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "none"))
    command = test_command(root)
    lines += ["", "## Tests", f"run: {command} (this script does not run it)" if command else "run: no test command found"]
    if command is None:
        gaps.append("no test command found: the page cannot cite a test count")
    lines += ["", "## Gaps"] + ([f"- {gap}" for gap in gaps] or ["- none found by this script"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="any path inside the repo (default: the current folder)")
    parser.add_argument("--since", help="window start, YYYY-MM-DD (default: the previous report's date)")
    parser.add_argument("--today", help="YYYY-MM-DD, for trials on a past state (default: today)")
    args = parser.parse_args(argv)
    try:
        today = parse_day(args.today) if args.today else date.today()
        since = parse_day(args.since) if args.since else None
        print(render(Path(args.repo).resolve(), since, today))
    except RecordError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
