"""Tests for audit.py. Run: python3 -m pytest ~/dotfiles/claude/skills/coverage-audit/scripts -q"""

import json
import subprocess
from pathlib import Path

import pytest

import audit

SESSION_ID = "cafe1234-0000-0000-0000-000000000000"
IMAGE_B64 = "aW1hZ2UgYnl0ZXM="  # b"image bytes"
TRANSCRIPT = (
    "Me: We want to get all of the relevant articles. And like, if I only tracked 20% of the sources, "
    "which 20 would be the best, for example? Any trending GitHub repositories, things that researchers "
    "are talking about. And then pulling every Dwarkesh podcast."
)
GOOD_AUDIT = """No. 4 asks: 1 covered, 1 partial, 1 missing, 1 n/a.
Source: call 2026-11-20. Checked against: `pipeline/` at `{sha}`.

| # | Ask (source words) | Status | Evidence |
|---|---|---|---|
| 1 | "get all of the relevant articles" | covered | Daily run collects every source: `pipeline/collect.py`, commit `{sha}` |
| 3 | "if I only tracked 20% of the sources, which 20 would be the best" | missing | Searched `research/` for "backtest": no ranking. |
| 5d | "Any trending GitHub repositories" | partial | `crawl4ai.github.trending.repositories` exists in treg, no adapter |
| 6a | "pulling every Dwarkesh ... podcast" | n/a | Permission only. |

## What fills the gaps
| # | What fills it | Waits on | Size |
|---|---|---|---|
| 3 | Backtest script over the traces. | me | 1 agent |
| 5 | GitHub trending adapter. | you: pick languages | 1 agent |
"""


def user(stamp: str, text: str | list[dict], **flags: object) -> dict:
    return {"type": "user", "timestamp": f"2026-11-22T{stamp}:00Z", "message": {"content": text}, **flags}


def paste(pid: str, body: str) -> str:
    return f'<pasted_content id="{pid}">\n{body}\n</pasted_content id="{pid}">'


SESSION_ENTRIES = [
    user("06:56", paste("f9ab", TRANSCRIPT) + "\n\ndoes he mention any other accounts"),
    {"type": "queue-operation", "timestamp": "2026-11-22T06:56:00Z", "content": paste("f9ab", TRANSCRIPT)},
    user("06:57", "skill body " + paste("meta", "not a paste Leo typed"), isMeta=True),
    user("06:58", "the rubric: " + paste("r1", "Rubric row 1. Hook & MVP Validation")),
    user("06:59", "so can we make sure all of our bases are covered"),
    user("07:00", [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": IMAGE_B64}},
                   {"type": "text", "text": "[Image #1] this was the red team report"}]),
    user("07:01", [{"type": "tool_result", "tool_use_id": "t1",
                    "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "c2hvdA=="}}]}]),
]


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    (root / "pipeline").mkdir(parents=True)
    (root / "research").mkdir()
    (root / "pipeline" / "collect.py").write_text("print('collect')\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "feat: collect"],
        check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return root, sha


def run_check(audit_text: str, repo: tuple[Path, str]) -> tuple[list[str], list[str]]:
    root, sha = repo
    return audit.check_audit(audit_text.replace("{sha}", sha), [TRANSCRIPT], [root])


@pytest.fixture
def saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    transcript = tmp_path / "projects" / "-Users-leo-firehose" / f"{SESSION_ID}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join(json.dumps(e) for e in SESSION_ENTRIES) + "\n{broken line\n")
    monkeypatch.setattr(audit, "PROJECTS_DIR", tmp_path / "projects")
    out_dir = tmp_path / "out"
    lines = audit.save_pastes(audit.session_pastes(audit.find_transcript("cafe12")), out_dir)
    return lines, out_dir


def test_source_saves_each_distinct_paste_in_time_order(saved: tuple[list[str], Path]) -> None:
    lines, out_dir = saved
    assert len(lines) == 2
    assert (out_dir / "paste-1.txt").read_text() == TRANSCRIPT + "\n"
    assert (out_dir / "paste-2.txt").read_text() == "Rubric row 1. Hook & MVP Validation\n"


def test_source_index_shows_time_size_and_preview(saved: tuple[list[str], Path]) -> None:
    lines, out_dir = saved
    assert lines[0] == f"{out_dir / 'paste-1.txt'}  2026-11-22T06:56  {len(TRANSCRIPT)} chars  {TRANSCRIPT[:80]}"


def test_source_skips_meta_entries(saved: tuple[list[str], Path]) -> None:
    _, out_dir = saved
    assert "not a paste Leo typed" not in "\n".join(p.read_text() for p in out_dir.iterdir())


def test_source_saves_pasted_images_but_not_tool_screenshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transcript = tmp_path / "projects" / "-Users-leo-firehose" / f"{SESSION_ID}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join(json.dumps(e) for e in SESSION_ENTRIES) + "\n")
    monkeypatch.setattr(audit, "PROJECTS_DIR", tmp_path / "projects")

    lines = audit.save_images(audit.session_images(audit.find_transcript("cafe12")), tmp_path / "out")

    assert len(lines) == 1
    assert (tmp_path / "out" / "image-1.png").read_bytes() == b"image bytes"


def test_check_accepts_a_finding_number_as_evidence_for_a_covered_row(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace(
        "Daily run collects every source: `pipeline/collect.py`, commit `{sha}`", "Response PDF, finding 7: fixed."
    )
    problems, _ = run_check(text, repo)
    assert problems == []


def test_source_fails_loudly_on_an_unknown_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "PROJECTS_DIR", tmp_path)
    with pytest.raises(SystemExit, match="no transcript for session 'nope'"):
        audit.find_transcript("nope")


def test_check_passes_a_good_audit_and_counts_statuses(repo: tuple[Path, str]) -> None:
    problems, summary = run_check(GOOD_AUDIT, repo)
    assert problems == []
    assert summary[0] == "asks: 4; Status: 1 covered, 1 partial, 1 missing, 0 unverified, 1 n/a"


def test_check_reports_names_and_domains_as_not_checkable(repo: tuple[Path, str]) -> None:
    _, summary = run_check(GOOD_AUDIT, repo)
    assert summary[1] == "evidence: 3 paths and commits exist; 1 not checkable (crawl4ai.github.trending.repositories)"


def test_check_accepts_a_slide_number_as_evidence_for_a_covered_row(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace(
        "Daily run collects every source: `pipeline/collect.py`, commit `{sha}`", "Slide 7: 41 of 56 closed."
    )
    problems, _ = run_check(text, repo)
    assert problems == []


def test_check_flags_an_audit_with_no_target_line(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace(" Checked against: `pipeline/` at `{sha}`.", "")
    problems, _ = run_check(text, repo)
    assert problems == ["no target: add a 'Checked against: <file, repo or commit in backticks>' line"]


def test_check_flags_a_target_that_does_not_exist(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("Checked against: `pipeline/` at `{sha}`", "Checked against: `deck.pdf`")
    problems, _ = run_check(text, repo)
    assert problems == [f"target: path `deck.pdf` does not exist under {repo[0]}"]


def test_check_does_not_fail_on_handles_domains_and_commands(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace(
        "no adapter", "no adapter; `r/ClaudeAI`, `github.com/trending`, `typesafe.ai`, `npm run check`"
    )
    problems, summary = run_check(text, repo)
    assert problems == []
    assert summary[1].startswith("evidence: 3 paths and commits exist; 5 not checkable")


def test_check_flags_a_paraphrase_shown_as_a_quote(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace('"get all of the relevant articles"', '"collect every relevant article"')
    problems, _ = run_check(text, repo)
    assert problems == ["row 1: quote 'collect every relevant article' is not word for word in the source"]


def test_check_flags_an_ask_with_no_source_words(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace('"get all of the relevant articles"', "Collect all articles")
    problems, _ = run_check(text, repo)
    assert problems == ["row 1: the ask quotes no source words"]


def test_check_flags_a_path_that_does_not_exist(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("`pipeline/collect.py`", "`pipeline/collector.py`")
    problems, _ = run_check(text, repo)
    assert problems == [f"row 1: path `pipeline/collector.py` does not exist under {repo[0]}"]


def test_check_accepts_a_path_with_a_line_or_test_suffix(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("`pipeline/collect.py`", "`pipeline/collect.py:1` and `pipeline/collect.py::test_run`")
    problems, _ = run_check(text, repo)
    assert problems == []


def test_check_flags_a_line_past_the_end_of_the_file(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("`pipeline/collect.py`", "`pipeline/collect.py:12`")
    problems, _ = run_check(text, repo)
    assert problems == [f"row 1: `pipeline/collect.py:12` points past the end of {repo[0] / 'pipeline' / 'collect.py'}"]


def test_check_flags_a_commit_that_does_not_exist(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("commit `{sha}`", "commit `0badc0de`")
    problems, _ = run_check(text, repo)
    assert problems == [f"row 1: commit `0badc0de` is not in {repo[0]}"]


def test_check_flags_a_covered_row_with_no_evidence(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace(
        "Daily run collects every source: `pipeline/collect.py`, commit `{sha}`", "The agent said so."
    )
    problems, _ = run_check(text, repo)
    assert problems == [
        "row 1: covered, but the evidence names no file, commit, command, link or place (slide, page, section)"
    ]


def test_check_flags_a_status_outside_the_five(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("| covered |", "| done |")
    problems, _ = run_check(text, repo)
    assert problems[0] == "row 1: status 'done' is not one of covered, partial, missing, unverified, n/a"


def test_check_flags_a_headline_that_does_not_match_the_table(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("No. 4 asks: 1 covered, 1 partial", "No. 5 asks: 1 covered, 2 partial")
    problems, _ = run_check(text, repo)
    assert problems == ["headline says 5 asks, the table has 4", "headline says 2 partial, the table has 1"]


def test_check_flags_an_audit_with_no_headline(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("No. 4 asks: 1 covered, 1 partial, 1 missing, 1 n/a.", "Here is the table.")
    problems, _ = run_check(text, repo)
    assert problems == ["no headline: start with '<Yes | No | Mostly>. <N> asks: <a> covered, ...'"]


def test_check_flags_an_open_row_with_no_gap_row(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("| 3 | Backtest script over the traces. | me | 1 agent |\n", "")
    problems, _ = run_check(text, repo)
    assert problems == ["row 3: open, but no row in the gaps table says what fills it"]


def test_check_lets_a_parent_gap_row_cover_its_lettered_parts(repo: tuple[Path, str]) -> None:
    problems, _ = run_check(GOOD_AUDIT, repo)
    assert not any("row 5d" in problem for problem in problems)


def test_check_flags_a_gap_that_waits_on_an_unknown_owner(repo: tuple[Path, str]) -> None:
    text = GOOD_AUDIT.replace("| me | 1 agent |", "| Roy | 1 agent |")
    problems, _ = run_check(text, repo)
    assert problems == ["gap 3: 'Waits on' must start with me, you or external, not 'roy'"]


def test_check_counts_each_target_column_on_its_own(repo: tuple[Path, str]) -> None:
    text = (
        "Checked against: `pipeline/`.\n\n"
        "| # | Ask | Status (system) | Status (page) | Evidence |\n|---|---|---|---|---|\n"
        '| 1 | "get all of the relevant articles" | covered | n/a | `pipeline/collect.py` |\n'
    )
    _, summary = run_check(text, repo)
    assert summary[0] == (
        "asks: 1; Status (system): 1 covered, 0 partial, 0 missing, 0 unverified, 0 n/a"
        "; Status (page): 0 covered, 0 partial, 0 missing, 0 unverified, 1 n/a"
    )


def test_check_fails_loudly_without_an_asks_table(repo: tuple[Path, str]) -> None:
    with pytest.raises(SystemExit, match="no asks table"):
        run_check("No table here.", repo)


def test_split_cells_keeps_pipes_inside_backticks() -> None:
    assert audit.split_cells("| 1 | `a | b` | x \\| y |") == ("1", "`a | b`", "x | y")


def test_main_exits_nonzero_when_the_check_finds_problems(repo: tuple[Path, str], tmp_path: Path) -> None:
    audit_file, source_file = tmp_path / "audit.md", tmp_path / "source.txt"
    audit_file.write_text(GOOD_AUDIT.replace("| covered |", "| done |"))
    source_file.write_text(TRANSCRIPT)
    assert audit.main(["check", str(audit_file), "--source", str(source_file), "--root", str(repo[0])]) == 1
