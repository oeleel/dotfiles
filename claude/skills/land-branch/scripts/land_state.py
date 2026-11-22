#!/usr/bin/env python3
"""Report what landing one branch on its base needs, or whether it has landed, for the
land-branch skill. Read-only, except `git fetch --prune origin` (skip it with --no-fetch).

It prints facts only:
- the branch, its checkout, uncommitted files, and its upstream,
- the base: origin's tip, and local commits that a push of the base would carry,
- landed: whether origin's base holds the branch's content (by history, by a merge that
  would change nothing, or at an earlier base commit). It compares content, so it holds
  after a squash merge or a hook rebase changed the hashes,
- the merge style of origin's recent history and the GitHub PRs for the branch,
- the path to take (pr or local), the worktrees and which of them to keep,
- stop lines: facts that block a merge until someone decides.

Usage: land_state.py [--repo PATH] [--branch NAME] [--base NAME] [--sha REV] [--no-fetch] [--no-gh]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HISTORY_DEPTH = 30  # about one to three weeks of first-parent commits in Leo's repos
PR_SHARE_FOR_PR_PATH = 0.5  # half or more of recent landings went through PRs
FETCH_TIMEOUT_SECONDS = 30
GH_TIMEOUT_SECONDS = 30
MAX_LISTED_FILES = 8
MAX_LANDING_SCAN = 300  # base commits since the fork point to search for the landing
# Scheduled jobs run in fixed folders (firehose's 07:00 judge runs in ~/N2O/firehose-judge).
# A worktree named in one of these files is load-bearing, even when it looks stale.
SCHEDULER_GLOBS = (  # relative to the home folder
    "Library/LaunchAgents/*.plist",
    ".config/systemd/user/*.service",
    ".config/systemd/user/*.timer",
)
IN_PROGRESS_MARKERS = {
    "MERGE_HEAD": "merge",
    "rebase-merge": "rebase",
    "rebase-apply": "rebase",
    "CHERRY_PICK_HEAD": "cherry-pick",
}
SQUASH_PR_RE = re.compile(r"\(#\d+\)\s*$")
MERGE_PR_RE = re.compile(r"^Merge pull request #\d+")
GITHUB_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str
    branch: str | None
    locked: bool


@dataclass(frozen=True)
class PullRequest:
    number: int
    state: str
    draft: bool
    head: str
    base: str
    head_sha: str
    author: str
    url: str


def run(args: list[str], cwd: Path, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def git(repo: Path, *args: str) -> str:
    result = run(["git", *args], repo)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def git_maybe(repo: Path, *args: str) -> str | None:
    result = run(["git", *args], repo)
    return result.stdout.strip() if result.returncode == 0 else None


def repo_root(path: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], path)
    if result.returncode != 0:
        raise SystemExit(f"not a git repository: {path}")
    return Path(result.stdout.strip()).resolve()


def parse_worktrees(porcelain: str) -> list[Worktree]:
    trees = []
    for block in porcelain.strip().split("\n\n"):
        fields = dict((line.split(" ", 1) + [""])[:2] for line in block.splitlines())
        branch = fields.get("branch", "").removeprefix("refs/heads/") or None
        path = Path(fields["worktree"]).resolve()
        trees.append(Worktree(path, fields.get("HEAD", "")[:8], branch, "locked" in fields))
    return trees


def default_base(repo: Path) -> str:
    head = git_maybe(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.removeprefix("origin/")
    for name in ("main", "master"):
        if git_maybe(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}"):
            return name
    raise SystemExit(f"no base branch: origin/HEAD is unset and origin has no main or master in {repo}")


def classify_subject(subject: str, parents: int) -> str:
    if MERGE_PR_RE.match(subject):
        return "pr-merge"
    if SQUASH_PR_RE.search(subject):
        return "squash-pr"
    if parents > 1:
        return "local-merge"
    return "direct"


def history_style(repo: Path, ref: str) -> Counter[str]:
    # The hash leads each line, so a root commit's empty parent list survives the strip in git().
    log = git(repo, "log", "--first-parent", f"-{HISTORY_DEPTH}", "--format=%H%x09%P%x09%s", ref)
    styles: Counter[str] = Counter()
    for line in log.splitlines():
        _, parents, subject = line.split("\t", 2)
        styles[classify_subject(subject, len(parents.split()))] += 1
    return styles


def github_slug(origin_url: str) -> str | None:
    match = GITHUB_RE.search(origin_url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def parse_prs(gh_json: str) -> list[PullRequest]:
    return [
        PullRequest(
            number=item["number"],
            state=item["state"],
            draft=item["isDraft"],
            head=item["headRefName"],
            base=item["baseRefName"],
            head_sha=item["headRefOid"][:8],
            author=(item.get("author") or {}).get("login", "?"),
            url=item["url"],
        )
        for item in json.loads(gh_json)
    ]


def gh_prs(repo: Path, slug: str, flag: str, branch: str, state: str) -> list[PullRequest]:
    fields = "number,state,isDraft,headRefName,baseRefName,headRefOid,author,url"
    args = ["gh", "pr", "list", "-R", slug, flag, branch, "--state", state, "--limit", "20", "--json", fields]
    try:
        result = run(args, repo, timeout=GH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"gh pr list gave no answer in {GH_TIMEOUT_SECONDS}s for {slug}; rerun or pass --no-gh"
        ) from None
    if result.returncode != 0:
        raise SystemExit(f"gh pr list failed for {slug} {flag} {branch}: {result.stderr.strip()}")
    return parse_prs(result.stdout)


def choose_path(open_prs: list[PullRequest], styles: Counter[str], on_github: bool) -> tuple[str, str]:
    if open_prs:
        return "pr", f"open PR #{open_prs[0].number}; a local merge would leave it open"
    if not on_github:
        return "local", "origin is not GitHub or gh is unavailable"
    total = sum(styles.values())
    pr_count = styles["squash-pr"] + styles["pr-merge"]
    if total and pr_count / total >= PR_SHARE_FOR_PR_PATH:
        return "pr", f"{pr_count} of the last {total} landings on the base went through PRs"
    return "local", f"{pr_count} of the last {total} landings on the base went through PRs"


def merge_result(repo: Path, base_ref: str, tip: str) -> tuple[str, tuple[str, ...]]:
    """'no-op' when a merge of tip into base_ref yields base_ref's own tree, else 'clean' or 'conflict'."""
    result = run(["git", "merge-tree", "--write-tree", "--name-only", base_ref, tip], repo)
    lines = result.stdout.splitlines()
    if result.returncode == 1:
        conflicted = []
        for line in lines[1:]:
            if not line:
                break
            conflicted.append(line)
        return "conflict", tuple(conflicted)
    if result.returncode != 0:
        raise SystemExit(f"git merge-tree {base_ref} {tip} failed in {repo}: {result.stderr.strip()}")
    return ("no-op" if lines[0] == git(repo, "rev-parse", f"{base_ref}^{{tree}}") else "clean"), ()


def landing_commit(repo: Path, base_ref: str, tip: str) -> str | None:
    """The first commit on the base's first-parent line whose tree already holds the branch.
    Main can change the branch's files after the landing; a check at the tip alone then
    reports a landed branch as unlanded (PR #192 in cs4501, 2026-11-22)."""
    fork = git(repo, "merge-base", base_ref, tip)
    candidates = git(
        repo, "rev-list", "--first-parent", f"--max-count={MAX_LANDING_SCAN}", f"{fork}..{base_ref}"
    ).split()
    for commit in reversed(candidates):
        if merge_result(repo, commit, tip)[0] == "no-op":
            return commit
    return None


def ahead_behind(repo: Path, ours: str, theirs: str) -> tuple[int, int]:
    left, right = git(repo, "rev-list", "--left-right", "--count", f"{ours}...{theirs}").split()
    return int(left), int(right)


def in_progress(worktree: Path) -> str | None:
    gitdir = Path(git(worktree, "rev-parse", "--absolute-git-dir"))
    for marker, name in IN_PROGRESS_MARKERS.items():
        if (gitdir / marker).exists():
            return name
    return None


def scheduled_job_text() -> str:
    texts = [p.read_text(errors="replace") for pattern in SCHEDULER_GLOBS for p in Path.home().glob(pattern)]
    if shutil.which("crontab"):
        texts.append(run(["crontab", "-l"], Path.home()).stdout)
    return "\n".join(texts)


def named_in_schedule(path: Path, schedule_text: str) -> bool:
    # A bare substring test would also match ~/N2O/firehose inside ~/N2O/firehose-judge.
    return re.search(re.escape(str(path)) + r"(?=$|[/\s<\"'])", schedule_text, re.M) is not None


def resolve_tip(repo: Path, branch: str, sha: str | None) -> tuple[str | None, str]:
    for ref, where in ((f"refs/heads/{branch}", "local"), (f"refs/remotes/origin/{branch}", "origin only")):
        if git_maybe(repo, "rev-parse", "--verify", "--quiet", ref):
            return ref, where
    if sha:
        return git(repo, "rev-parse", "--verify", f"{sha}^{{commit}}"), "gone; using --sha"
    return None, "gone locally and on origin"


def fetch(repo: Path) -> str:
    try:
        result = run(["git", "fetch", "--prune", "--quiet", "origin"], repo, timeout=FETCH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"FAILED: no answer from origin in {FETCH_TIMEOUT_SECONDS}s"
    return "done" if result.returncode == 0 else f"FAILED: {result.stderr.strip()}"


def short_list(items: list[str]) -> str:
    extra = len(items) - MAX_LISTED_FILES
    return ", ".join(items[:MAX_LISTED_FILES]) + (f", +{extra} more" if extra > 0 else "")


@dataclass(frozen=True)
class Section:
    lines: tuple[str, ...]
    todos: tuple[str, ...] = ()
    stops: tuple[str, ...] = ()


@dataclass(frozen=True)
class Context:
    root: Path
    trees: tuple[Worktree, ...]
    branch: str
    base: str
    base_ref: str
    tip: str | None
    tip_where: str


def dirty_files(worktree: Path) -> list[str]:
    # Unstripped output: the first porcelain line starts with a status space.
    result = run(["git", "status", "--porcelain"], worktree)
    if result.returncode != 0:
        raise SystemExit(f"git status failed in {worktree}: {result.stderr.strip()}")
    return [line[3:] for line in result.stdout.splitlines() if line]


def branch_section(ctx: Context) -> Section:
    holder = next((t for t in ctx.trees if t.branch == ctx.branch), None)
    tip_text = git(ctx.root, "rev-parse", "--short=8", ctx.tip) if ctx.tip else "-"
    where = f"checked out in {holder.path}" if holder else "not checked out"
    lines = [f"branch: {ctx.branch} at {tip_text} ({ctx.tip_where}; {where})"]
    todos: list[str] = []
    stops = [f"the branch is the base ({ctx.base}); there is nothing to land"] if ctx.branch == ctx.base else []
    if holder:
        dirty = dirty_files(holder.path)
        operation = in_progress(holder.path)
        state = f"{len(dirty)} uncommitted: {short_list(dirty)}" if dirty else "clean"
        lines.append(f"tree: {state}" + (f"; {operation} in progress" if operation else ""))
        if operation:
            stops.append(f"a {operation} is in progress in {holder.path}")
        if dirty:
            todos.append(f"commit {len(dirty)} uncommitted files in {holder.path}")
    origin_branch = f"refs/remotes/origin/{ctx.branch}"
    has_origin = git_maybe(ctx.root, "rev-parse", "--verify", "--quiet", origin_branch) is not None
    if ctx.tip_where == "local" and has_origin:
        ahead, behind = ahead_behind(ctx.root, ctx.tip or "", origin_branch)
        lines.append(f"origin/{ctx.branch}: exists; branch ahead {ahead}, behind {behind}")
        if ahead:
            todos.append(f"push {ahead} commits to origin/{ctx.branch}")
        if behind:
            stops.append(f"the branch is {behind} behind origin/{ctx.branch}: pull --rebase and read what arrived")
    elif ctx.tip_where == "local":
        lines.append(f"origin/{ctx.branch}: none")
        todos.append(f"push the branch: git push -u origin {ctx.branch}")
    else:
        lines.append(f"origin/{ctx.branch}: {'exists' if has_origin else 'none'}; local branch: none")
    return Section(tuple(lines), tuple(todos), tuple(stops))


def base_section(ctx: Context) -> Section:
    origin_tip = git(ctx.root, "rev-parse", "--short=8", ctx.base_ref)
    local_base = f"refs/heads/{ctx.base}"
    if not git_maybe(ctx.root, "rev-parse", "--verify", "--quiet", local_base):
        return Section((f"base: {ctx.base}; origin/{ctx.base} at {origin_tip}; no local {ctx.base}",))
    holder = next((t for t in ctx.trees if t.branch == ctx.base), None)
    where = f"checked out in {holder.path}" if holder else "not checked out"
    ahead, behind = ahead_behind(ctx.root, local_base, ctx.base_ref)
    local = f"local {ctx.base} ahead {ahead}, behind {behind} ({where})"
    line = f"base: {ctx.base}; origin/{ctx.base} at {origin_tip}; {local}"
    stops = (f"local {ctx.base} has {ahead} commits not on origin/{ctx.base}; a push of {ctx.base} would carry them",)
    return Section((line,), stops=stops if ahead else ())


def landed_section(ctx: Context) -> Section:
    if ctx.tip is None:
        return Section(("landed: unknown; the branch is gone (pass --sha <old tip> for a content check)",))
    only_branch, only_base = ahead_behind(ctx.root, ctx.tip, ctx.base_ref)
    counts = f"vs origin/{ctx.base}: {only_branch} commits only on the branch, {only_base} only on {ctx.base}"
    if only_branch == 0:
        return Section((counts, f"landed: yes; the tip is in origin/{ctx.base}'s history"))
    outcome, conflicted = merge_result(ctx.root, ctx.base_ref, ctx.tip)
    if outcome == "no-op":
        return Section((counts, f"landed: yes; merging the branch into origin/{ctx.base} changes nothing"))
    landing = landing_commit(ctx.root, ctx.base_ref, ctx.tip)
    if landing:
        subject = git(ctx.root, "log", "-1", "--format=%h %s", landing)
        return Section((counts, f"landed: yes; in {subject}; {ctx.base} changed some of its files later"))
    if outcome == "conflict":
        files = f"{len(conflicted)} files: {short_list(list(conflicted))}"
        return Section(
            (counts, f"landed: no; a merge conflicts in {files}"),
            stops=(f"conflicts with origin/{ctx.base} in {files}",),
        )
    return Section((counts, "landed: no; a merge applies cleanly"))


def pr_section(ctx: Context, use_gh: bool) -> Section:
    styles = history_style(ctx.root, ctx.base_ref)
    history = (
        f"history of origin/{ctx.base} (last {sum(styles.values())} first-parent commits): "
        f"{styles['squash-pr']} squash PR, {styles['pr-merge']} PR merge commit, "
        f"{styles['local-merge']} local merge commit, {styles['direct']} direct or local squash"
    )
    slug = github_slug(git_maybe(ctx.root, "remote", "get-url", "origin") or "")
    if not (use_gh and slug and shutil.which("gh")):
        path, why = choose_path([], styles, on_github=False)
        lines = (history, "pr: not checked (--no-gh, origin is not GitHub, or gh is missing)", f"path: {path} ({why})")
        return Section(lines, stops=handover_stop(ctx, path))
    prs = gh_prs(ctx.root, slug, "--head", ctx.branch, "all")
    stacked = gh_prs(ctx.root, slug, "--base", ctx.branch, "open")
    lines = [history]
    lines += [pr_line(p) for p in prs] or ["pr: none for this branch"]
    path, why = choose_path([p for p in prs if p.state == "OPEN"], styles, on_github=True)
    lines.append(f"path: {path} ({why})")
    numbers = ", ".join(f"#{p.number}" for p in stacked)
    stops = (
        [f"{len(stacked)} open PRs use {ctx.branch} as their base ({numbers}); deleting the branch closes them"]
        if stacked
        else []
    )
    stops += [
        f"PR #{p.number} is a draft; gh pr merge refuses it until someone marks it ready"
        for p in prs
        if p.state == "OPEN" and p.draft
    ]
    return Section(tuple(lines), stops=tuple(stops) + handover_stop(ctx, path))


def pr_line(pr: PullRequest) -> str:
    state = f"{pr.state} draft" if pr.draft else pr.state
    return f"pr: #{pr.number} {state} {pr.head} -> {pr.base}, head {pr.head_sha}, by {pr.author}, {pr.url}"


def handover_stop(ctx: Context, path: str) -> tuple[str, ...]:
    """A local merge happens in the checkout that has the base checked out. When that is another
    checkout, another session owns it (firehose: only the session in ~/N2O/firehose merges)."""
    holder = next((t for t in ctx.trees if t.branch == ctx.base), None)
    if path != "local" or holder is None or holder.path == ctx.root:
        return ()
    return (f"{ctx.base} is checked out in {holder.path}; a local merge belongs to the session that works there",)


def worktree_section(ctx: Context) -> Section:
    schedule = scheduled_job_text()
    lines = ["worktrees:"]
    for t in ctx.trees:
        tags = [
            tag
            for tag, applies in (
                ("main checkout", t.path == ctx.trees[0].path),
                ("this checkout", t.path == ctx.root),
                ("holds this branch", t.branch == ctx.branch),
                ("KEEP: locked", t.locked),
                ("KEEP: named in a scheduled job", named_in_schedule(t.path, schedule)),
            )
            if applies
        ]
        label = f"[{t.branch}]" if t.branch else "(detached)"
        lines.append(f"  {t.path} {label} {t.head}" + (f" - {', '.join(tags)}" if tags else ""))
    return Section(tuple(lines))


def report(repo: Path, branch: str | None, base: str | None, sha: str | None, do_fetch: bool, use_gh: bool) -> str:
    root = repo_root(repo)
    trees = tuple(parse_worktrees(git(root, "worktree", "list", "--porcelain")))
    here = next(t for t in trees if t.path == root)
    branch = branch or here.branch
    if branch is None:
        raise SystemExit(f"{root} has a detached HEAD; pass --branch")
    fetch_state = fetch(root) if do_fetch else "skipped (--no-fetch); origin refs are as of the last fetch"
    base = base or default_base(root)
    base_ref = f"refs/remotes/origin/{base}"
    if not git_maybe(root, "rev-parse", "--verify", "--quiet", base_ref):
        raise SystemExit(f"origin has no branch {base!r} in {root}")
    tip, tip_where = resolve_tip(root, branch, sha)
    ctx = Context(root, trees, branch, base, base_ref, tip, tip_where)
    where = "" if root == trees[0].path else f" (worktree; main checkout {trees[0].path})"
    head = Section(
        (f"repo: {root}{where}", f"fetch: {fetch_state}"),
        stops=(f"fetch {fetch_state}",) if fetch_state.startswith("FAILED") else (),
    )
    sections = [
        head,
        branch_section(ctx),
        base_section(ctx),
        landed_section(ctx),
        pr_section(ctx, use_gh),
        worktree_section(ctx),
    ]
    lines = [line for s in sections for line in s.lines]
    lines += [f"todo: {item}" for s in sections for item in s.todos] or ["todo: none"]
    lines += [f"stop: {item}" for s in sections for item in s.stops] or ["stop: none"]
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="any folder in the repo (default: cwd)")
    parser.add_argument("--branch", help="branch to land (default: the current branch)")
    parser.add_argument("--base", help="target branch (default: origin's default branch)")
    parser.add_argument("--sha", help="old tip to check when the branch is already deleted")
    parser.add_argument("--no-fetch", action="store_true", help="do not fetch origin first")
    parser.add_argument("--no-gh", action="store_true", help="do not ask GitHub for PRs")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        raise SystemExit(f"--repo is not a folder: {args.repo}")
    print(report(args.repo.resolve(), args.branch, args.base, args.sha, not args.no_fetch, not args.no_gh))


if __name__ == "__main__":
    main(sys.argv[1:])
