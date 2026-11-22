"""Tests for record.py. Run: python3 -m pytest ~/dotfiles/claude/skills/meeting-pack/scripts -q"""

import os
import subprocess
from datetime import date
from pathlib import Path

import pytest

import record

TODAY = date(2026, 11, 19)
GITHUB = "https://github.com/oeleel/epiForecasting"
TODO_NOTES = "# Todo\n## 1. Rivanna\n- [x] Log in to Rivanna\n- [X] Run the tests as a job\n- [ ] Serve the larger Qwen model\n"
REPORT_YAML = "title: x\nsections:\n  - id: quick\n    heading: Quick summary\n  - id: next\n    heading: Next steps\n"


def git(repo: Path, *args: str, day: str = "2026-11-10") -> None:
    stamp = f"{day}T12:00:00"
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def commit(repo: Path, path: str, subject: str, day: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(subject)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", subject, day=day)


def make_repo(tmp_path: Path) -> Path:
    """A repo with an old report, gitignored notes, a pushed commit, an autosave and an unpushed commit."""
    repo = tmp_path / "proj"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    git(repo, "remote", "add", "origin", "git@github.com:oeleel/epiForecasting.git")
    (repo / ".gitignore").write_text("documentation/meeting-notes/\n")
    (repo / ".nojekyll").write_text("")
    commit(repo, "documentation/reports/2026-11-05/report.yaml", REPORT_YAML, "2026-11-05")
    commit(repo, "documentation/experiments/tsci/summary.md", "feat(comparison): score both frameworks", "2026-11-12")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    commit(repo, "scripts/slurm/llm.sbatch", "checkpoint: WIP autosave (1 file(s))", "2026-11-13")
    commit(repo, "scripts/slurm/cpu.sbatch", "ops(rivanna): sbatch templates", "2026-11-14")
    notes = repo / "documentation" / "meeting-notes"
    notes.mkdir(parents=True)
    (notes / "todo-week-2026-11-16.md").write_text(TODO_NOTES)
    return repo


def bare_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "bare"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    commit(repo, "README.md", "chore: start", "2026-11-18")
    return repo


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:oeleel/epiForecasting.git",
        "https://github.com/oeleel/epiForecasting.git",
        "https://github.com/oeleel/epiForecasting",
        "ssh://git@github.com/oeleel/epiForecasting.git\n",
    ],
)
def test_github_base_parses_ssh_and_https_remotes(remote: str) -> None:
    assert record.github_base(remote) == GITHUB


def test_github_base_rejects_other_hosts() -> None:
    assert record.github_base("https://gitlab.com/oeleel/epiForecasting.git") is None


def test_pages_base_needs_nojekyll(tmp_path: Path) -> None:
    assert record.pages_base(GITHUB, tmp_path) is None


def test_pages_base_lowercases_the_owner(tmp_path: Path) -> None:
    (tmp_path / ".nojekyll").write_text("")

    assert record.pages_base("https://github.com/OeLeel/epiForecasting", tmp_path) == "https://oeleel.github.io/epiForecasting/"


def test_checkbox_summary_counts_done_and_lists_open() -> None:
    assert record.checkbox_summary(TODO_NOTES) == (2, ["Serve the larger Qwen model"])


def test_checkbox_sections_tallies_each_heading() -> None:
    text = "## 1. Rivanna\n- [x] Log in\n- [ ] Serve the model\n## Notes\nplain text\n### 2. TSci\n- [x] Run it\n"

    assert record.checkbox_sections(text) == [("1. Rivanna", 1, 2), ("2. TSci", 1, 1)]


def test_numbered_asks_reads_items_under_an_asked_heading() -> None:
    text = "## Asked (not yet accepted)\n1. **MVP by Monday**\n2. Speed\n## Open\n1. Did the demo happen\n"

    assert record.numbered_asks(text) == ["**MVP by Monday**", "Speed"]


def test_commit_types_counts_by_prefix_most_common_first() -> None:
    commits = [record.Commit("a", "d", s, True) for s in ("map: auto x", "feat(web): y", "map: auto z", "odd subject")]

    assert record.commit_types(commits) == {"map": 2, "feat": 1, "(other)": 1}


def test_render_lists_only_deliverable_commits_when_the_window_is_flooded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record, "MAX_COMMITS", 1)
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "too many to list" in out
    assert "ops(rivanna)" not in out.split("by type:")[1].split("## Files")[0].split("too many")[1]


def test_report_sections_reads_section_ids() -> None:
    assert record.report_sections(REPORT_YAML) == ["quick", "next"]


def test_date_in_name_ignores_impossible_dates() -> None:
    assert record.date_in_name("notes-2026-13-45.md") is None


def test_window_start_prefers_since() -> None:
    window = record.window_start(date(2026, 11, 1), [Path("2026-11-05")], TODAY, ("a" * 40, date(2026, 11, 6)))

    assert (window.start, window.base, window.log_range()) == (date(2026, 11, 1), None, ["--since=2026-11-01 00:00:00", "HEAD"])


def test_window_start_opens_after_the_previous_report_commit() -> None:
    window = record.window_start(None, [Path("2026-11-05")], TODAY, ("a" * 40, date(2026, 11, 6)))

    assert (window.start, window.log_range()) == (date(2026, 11, 6), ["a" * 40 + "..HEAD"])


def test_window_start_falls_back_to_the_report_date() -> None:
    window = record.window_start(None, [Path("2026-11-05")], TODAY, None)

    assert (window.start, window.basis) == (date(2026, 11, 5), "previous report 2026-11-05, by date")


def test_window_start_defaults_to_a_week() -> None:
    window = record.window_start(None, [], TODAY, None)

    assert (window.start, window.basis) == (date(2026, 11, 12), "default 7 days, no earlier report")


def test_find_reports_skips_today_and_undated(tmp_path: Path) -> None:
    for name in ("2026-11-05", "2026-11-19", "_template"):
        (tmp_path / "documentation" / "reports" / name).mkdir(parents=True)

    found = record.find_reports(tmp_path, TODAY)

    assert [p.name for p in found] == ["2026-11-05"]


def test_split_paths_lists_result_folders_and_counts_the_rest() -> None:
    paths = ["documentation/experiments/a.md", "scripts/slurm/a.sbatch", "scripts/slurm/b.sbatch", "README.md"]

    results, counts = record.split_paths(paths)

    assert (results, counts) == (["documentation/experiments/a.md"], {"scripts/slurm": 2, "(root)": 1})


def test_render_marks_unpushed_commits(tmp_path: Path) -> None:
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "ops(rivanna): sbatch templates https://github.com/oeleel/epiForecasting/commit/" in out
    assert "(not pushed: the link 404s until it is)" in out.split("ops(rivanna)")[1].splitlines()[0]


def test_render_hides_autosave_commits(tmp_path: Path) -> None:
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "Commits on HEAD in the window: 2 (+1 autosaves not listed)" in out
    assert "WIP autosave" not in out


def test_render_lists_gitignored_notes_as_local_only(tmp_path: Path) -> None:
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "documentation/meeting-notes/todo-week-2026-11-16.md (2026-11-16, local only): 2 done, 1 open" in out
    assert "    open: Serve the larger Qwen model" in out
    assert "    2/3 done: 1. Rivanna" in out


def test_render_leaves_the_previous_report_commit_out(tmp_path: Path) -> None:
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "window: since 2026-11-05 (after " in out
    assert "title: x" not in out.split("## Commits")[1]


def test_render_links_previous_report_on_pages(tmp_path: Path) -> None:
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "page: https://oeleel.github.io/epiForecasting/documentation/reports/2026-11-05/" in out


def test_render_lists_result_files_from_the_window(tmp_path: Path) -> None:
    out = record.render(make_repo(tmp_path), None, TODAY)

    assert "- documentation/experiments/tsci/summary.md" in out


def test_render_names_gaps_when_the_record_is_thin(tmp_path: Path) -> None:
    out = record.render(bare_repo(tmp_path), None, TODAY)

    assert "- no meeting notes in documentation/meeting-notes" in out
    assert "- no test command found: the page cannot cite a test count" in out


def test_main_fails_loudly_on_a_bad_date(capsys: pytest.CaptureFixture[str]) -> None:
    code = record.main(["--since", "2026-11-31"])

    assert (code, capsys.readouterr().err) == (1, "error: not a YYYY-MM-DD date: '2026-11-31'\n")


def test_main_fails_loudly_outside_a_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = record.main(["--repo", str(tmp_path)])

    assert code == 1
    assert f"failed in {tmp_path}" in capsys.readouterr().err
