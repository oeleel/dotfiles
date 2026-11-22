"""Tests for land_state.py. Run: python3 -m pytest ~/dotfiles/claude/skills/land-branch/scripts -q"""

import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

import land_state

PORCELAIN = (
    "worktree /repo\nHEAD 1111111111\nbranch refs/heads/main\n\n"
    "worktree /repo-judge\nHEAD 2222222222\ndetached\n\n"
    "worktree /repo/.claude/worktrees/agent-a1\nHEAD 3333333333\nbranch refs/heads/feature/x\nlocked\n"
)
GH_JSON = json.dumps(
    [
        {
            "number": 121,
            "state": "MERGED",
            "isDraft": False,
            "headRefName": "feature/e2e",
            "baseRefName": "main",
            "headRefOid": "eed6cd4aaaaaaaa",
            "author": {"login": "oeleel"},
            "url": "https://github.com/o/r/pull/121",
        }
    ]
)
OPEN_PR = land_state.PullRequest(5, "OPEN", False, "feature/x", "main", "abcd1234", "oeleel", "https://x/5")
SCHEDULE = (
    "<string>/Users/leo/N2O/firehose-judge</string>\n<string>/Users/leo/N2O/firehose-judge/scripts/run.sh</string>"
)


def sh(cwd: Path, *args: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    sh(repo, "git", "add", name)
    sh(repo, "git", "commit", "-q", "-m", message)


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A bare origin and a clone with main pushed and feature/x pushed, one commit ahead."""
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr(land_state, "scheduled_job_text", lambda: "")
    sh(tmp_path, "git", "init", "-q", "--bare", "origin.git")
    sh(tmp_path, "git", "clone", "-q", str(tmp_path / "origin.git"), "work")
    work = tmp_path / "work"
    commit(work, "app.txt", "one\n", "feat: start")
    sh(work, "git", "push", "-q", "-u", "origin", "main")
    sh(work, "git", "remote", "set-head", "origin", "main")
    sh(work, "git", "switch", "-q", "-c", "feature/x")
    commit(work, "app.txt", "one\ntwo\n", "feat: add two")
    sh(work, "git", "push", "-q", "-u", "origin", "feature/x")
    return work


@pytest.fixture
def squashed(sandbox: Path) -> Path:
    sh(sandbox, "git", "switch", "-q", "main")
    sh(sandbox, "git", "merge", "-q", "--squash", "feature/x")
    sh(sandbox, "git", "commit", "-q", "-m", "feat: land feature/x")
    sh(sandbox, "git", "push", "-q", "origin", "main")
    return sandbox


@pytest.fixture
def changed_after_landing(squashed: Path) -> Path:
    commit(squashed, "app.txt", "one\nTWO, later\n", "fix: reword two")
    sh(squashed, "git", "push", "-q", "origin", "main")
    return squashed


@pytest.fixture
def conflicting(sandbox: Path) -> Path:
    sh(sandbox, "git", "switch", "-q", "main")
    commit(sandbox, "app.txt", "one\nTWO\n", "fix: other two")
    sh(sandbox, "git", "push", "-q", "origin", "main")
    return sandbox


@pytest.fixture
def deleted(squashed: Path) -> tuple[Path, str]:
    tip = sh(squashed, "git", "rev-parse", "feature/x")
    sh(squashed, "git", "branch", "-q", "-D", "feature/x")
    sh(squashed, "git", "push", "-q", "origin", "--delete", "feature/x")
    return squashed, tip


@pytest.fixture
def in_worktree(sandbox: Path) -> Path:
    """feature/x moves to its own worktree; main is checked out in the main clone."""
    sh(sandbox, "git", "switch", "-q", "main")
    sh(sandbox, "git", "worktree", "add", "-q", str(sandbox.parent / "work-x"), "feature/x")
    return sandbox.parent / "work-x"


def state(repo: Path, **options: str) -> str:
    return land_state.report(repo, options.get("branch"), None, options.get("sha"), do_fetch=True, use_gh=False)


def test_parse_worktrees_reads_branch_detached_and_locked() -> None:
    assert land_state.parse_worktrees(PORCELAIN) == [
        land_state.Worktree(Path("/repo").resolve(), "11111111", "main", False),
        land_state.Worktree(Path("/repo-judge").resolve(), "22222222", None, False),
        land_state.Worktree(Path("/repo/.claude/worktrees/agent-a1").resolve(), "33333333", "feature/x", True),
    ]


@pytest.mark.parametrize(
    ("subject", "parents", "style"),
    [
        ("fix(tooling): e2e ignores DEMO_SHELL (#121)", 1, "squash-pr"),
        ("Merge pull request #22 from N2O-com/john/hub", 2, "pr-merge"),
        ("Merge branch 'feature/mvp-ui' (fb96cbb8)", 2, "local-merge"),
        ("feat: weekly hindcast", 1, "direct"),
    ],
)
def test_classify_subject_names_the_landing_style(subject: str, parents: int, style: str) -> None:
    assert land_state.classify_subject(subject, parents) == style


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://github.com/N2O-com/firehose.git", "N2O-com/firehose"),
        ("git@github.com:oeleel/dotfiles.git", "oeleel/dotfiles"),
        ("https://github.com/oeleel/epiForecasting", "oeleel/epiForecasting"),
        ("/tmp/origin.git", None),
    ],
)
def test_github_slug_reads_owner_and_repo(url: str, slug: str | None) -> None:
    assert land_state.github_slug(url) == slug


def test_parse_prs_keeps_state_head_and_author() -> None:
    assert land_state.parse_prs(GH_JSON) == [
        land_state.PullRequest(
            121, "MERGED", False, "feature/e2e", "main", "eed6cd4a", "oeleel", "https://github.com/o/r/pull/121"
        )
    ]


def test_choose_path_follows_an_open_pr() -> None:
    assert land_state.choose_path([OPEN_PR], Counter(direct=30), on_github=True)[0] == "pr"


def test_choose_path_is_local_off_github() -> None:
    assert land_state.choose_path([], Counter({"squash-pr": 30}), on_github=False)[0] == "local"


def test_choose_path_follows_a_pr_majority_in_history() -> None:
    assert land_state.choose_path([], Counter({"squash-pr": 18, "direct": 12}), on_github=True) == (
        "pr",
        "18 of the last 30 landings on the base went through PRs",
    )


def test_choose_path_is_local_when_history_has_few_prs() -> None:
    assert land_state.choose_path([], Counter({"local-merge": 6, "direct": 24}), on_github=True)[0] == "local"


def test_named_in_schedule_matches_the_folder_and_files_in_it() -> None:
    assert land_state.named_in_schedule(Path("/Users/leo/N2O/firehose-judge"), SCHEDULE)


def test_named_in_schedule_ignores_a_sibling_with_a_shared_prefix() -> None:
    assert not land_state.named_in_schedule(Path("/Users/leo/N2O/firehose"), SCHEDULE)


def test_land_state_reports_an_unlanded_branch(sandbox: Path) -> None:
    out = state(sandbox)

    assert "branch: feature/x at " in out
    assert "landed: no; a merge applies cleanly" in out
    assert "vs origin/main: 1 commits only on the branch, 0 only on main" in out
    assert "path: local (origin is not GitHub or gh is unavailable)" in out
    assert out.endswith("todo: none\nstop: none")


def test_land_state_counts_a_root_commit_as_direct(sandbox: Path) -> None:
    out = state(sandbox)

    assert "(last 1 first-parent commits): 0 squash PR, 0 PR merge commit, 0 local merge commit, 1 direct" in out


def test_land_state_sees_a_squash_merge_as_landed(squashed: Path) -> None:
    out = state(squashed, branch="feature/x")

    assert "landed: yes; merging the branch into origin/main changes nothing" in out
    assert "vs origin/main: 1 commits only on the branch, 1 only on main" in out


def test_land_state_finds_the_landing_when_main_changed_the_files_later(changed_after_landing: Path) -> None:
    out = state(changed_after_landing, branch="feature/x")

    assert "feat: land feature/x; main changed some of its files later" in out
    assert out.endswith("stop: none")


def test_land_state_sees_a_fast_forward_as_landed(sandbox: Path) -> None:
    sh(sandbox, "git", "push", "-q", "origin", "feature/x:main")

    out = state(sandbox)

    assert "landed: yes; the tip is in origin/main's history" in out


def test_land_state_stops_on_conflicts(conflicting: Path) -> None:
    out = state(conflicting, branch="feature/x")

    assert "landed: no; a merge conflicts in 1 files: app.txt" in out
    assert "stop: conflicts with origin/main in 1 files: app.txt" in out


def test_land_state_stops_when_local_base_has_unpushed_commits(sandbox: Path) -> None:
    sh(sandbox, "git", "switch", "-q", "main")
    commit(sandbox, "other.txt", "x\n", "chore: other work")

    out = state(sandbox, branch="feature/x")

    assert "stop: local main has 1 commits not on origin/main; a push of main would carry them" in out


def test_land_state_lists_uncommitted_and_unpushed_work_as_todo(sandbox: Path) -> None:
    commit(sandbox, "new.txt", "n\n", "feat: unpushed")
    (sandbox / "app.txt").write_text("edited\n")

    out = state(sandbox)

    assert "tree: 1 uncommitted: app.txt" in out
    assert "todo: commit 1 uncommitted files in " in out
    assert "todo: push 1 commits to origin/feature/x" in out


def test_land_state_reports_a_deleted_branch_as_gone(deleted: tuple[Path, str]) -> None:
    out = state(deleted[0], branch="feature/x")

    assert "branch: feature/x at - (gone locally and on origin; not checked out)" in out
    assert "landed: unknown; the branch is gone" in out


def test_land_state_checks_content_of_a_deleted_branch_by_sha(deleted: tuple[Path, str]) -> None:
    out = state(deleted[0], branch="feature/x", sha=deleted[1])

    assert "landed: yes; merging the branch into origin/main changes nothing" in out


def test_land_state_stops_a_local_merge_from_a_worktree_when_base_lives_elsewhere(in_worktree: Path) -> None:
    out = state(in_worktree)

    assert "(worktree; main checkout " in out
    assert "stop: main is checked out in " in out
    assert "a local merge belongs to the session that works there" in out


def test_land_state_allows_a_local_merge_from_the_checkout_that_holds_base(in_worktree: Path) -> None:
    out = state(in_worktree.parent / "work", branch="feature/x")

    assert "holds this branch" in out
    assert out.endswith("stop: none")


def test_land_state_marks_a_scheduled_worktree_keep(in_worktree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(land_state, "scheduled_job_text", lambda: f"<string>{in_worktree.resolve()}/run.sh</string>")

    out = state(in_worktree)

    assert "[feature/x]" in out
    assert "KEEP: named in a scheduled job" in out


def test_land_state_stops_when_the_branch_is_the_base(sandbox: Path) -> None:
    out = state(sandbox, branch="main")

    assert "stop: the branch is the base (main); there is nothing to land" in out


def test_land_state_fails_loudly_outside_a_repo(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not a git repository: "):
        land_state.report(tmp_path, None, None, None, do_fetch=False, use_gh=False)
