"""Tests for meeting.py.

Run: python3 -m pytest ~/dotfiles/claude/skills/meeting-to-actions/scripts -q
"""

import json
import subprocess
from pathlib import Path

import pytest

import meeting

SESSION_ID = "abc12345-0000-0000-0000-000000000000"
TRANSCRIPT = (
    "Speaker 1: Hi, Leo.\n"
    "leo lee (You):  Hi.\n"
    "Speaker 1:  So what was the experiment? Run it  on more states.\n"
    "leo lee (You):  Okay, I will run it on Rivanna.\n"
    "Speaker 1:  Perfect. See you Monday, bye.\n"
)
GRANOLA = (
    "Date: Nov 20\nMeeting participants: Wiley Simonds\n\nTranscript:\n"
    "Me: Get all of it.\nThem: Yes.\nMe: Fast.\nThem: Sure.\n"
)
LOOM = (
    "0:01 Alright, this is part two.\n0:11 I am interested in the cost.\n4:53 Some narrative map.\n"
)
LATE_TAIL = "Them: See you then, bye.\n" + "You: unrelated talk after the call.\n" * 12
TODO = (
    "# Todo - week of 2026-11-23\n\n"
    "## 1. Runs\n\n"
    "- [x] Run the tests (566 pass)\n"
    "- [ ] Collect AutoARIMA from job 23164608\n"
    "- [ ] **Leo:** confirm the Monday meeting\n\n"
    "## 2. Waiting on others\n\n"
    "- [ ] Advisor: Bayesian layer document\n"
)
NOTE = 'Wiley asked: "if I only tracked 20% of the sources, which 20 would be the best"\n'
NOTE_CHANGED = 'Wiley asked: "if I only tracked 20% of the sources, which 20 would be best"\n'
NOTE_CUT = 'Wiley asked: "if I only tracked 20% ... which 20 would be the best"\n'
NOTE_SHORT_QUOTES = '"Me" in the transcript is Wiley; "Them" is Leo.\n'
NOTE_PAGE_QUOTE = 'The page says Firehose is "partly: not in NOS yet" today.\n'
SOURCE = (
    "Me: And like, if I only tracked 20% of the sources, which 20 would be the best, for example?\n"
)
PAGE = "<td><b>partly:</b> not in NOS yet</td>"


def user(stamp: str, text: str, **flags: object) -> dict:
    return {
        "type": "user",
        "timestamp": f"2026-11-19T{stamp}:00Z",
        "message": {"content": text},
        **flags,
    }


def queued(stamp: str, text: str) -> dict:
    attachment = {"type": "queued_command", "prompt": text}
    return {"type": "attachment", "timestamp": f"2026-11-19T{stamp}:00Z", "attachment": attachment}


def pasted(paste_id: str, body: str) -> str:
    return f'<pasted_content id="{paste_id}">\n{body}\n</pasted_content id="{paste_id}">'


SESSION_ENTRIES = [
    user(
        "15:00",
        pasted("a1", "old notes")
        + " sept 9 "
        + pasted("a2", "Speaker 1: an older, longer call.")
        + " aug 27",
    ),
    user("15:05", pasted("s1", "agent text"), isSidechain=True),
    user("15:06", pasted("m1", "skill body"), isMeta=True),
    queued(
        "15:10",
        pasted("b1", "teams message")
        + pasted("b2", TRANSCRIPT)
        + " using transcript, create a todo",
    ),
    user(
        "15:11",
        pasted("b1", "teams message")
        + pasted("b2", TRANSCRIPT)
        + " using transcript, create a todo",
    ),
]


REPEATED_QUEUE_ENTRIES = [
    queued("16:00", pasted("c1", "first paste") + " notes"),
    user("16:01", pasted("c1", "first paste") + " notes"),
    user("16:30", pasted("c2", "second paste") + " transcript"),
]


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "projects" / "-Users-leolee-repo"
    project.mkdir(parents=True)
    path = project / f"{SESSION_ID}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in SESSION_ENTRIES) + "\nnot json\n")
    monkeypatch.setattr(meeting, "PROJECTS_DIR", tmp_path / "projects")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "lab"
    (root / "documentation" / "meeting-notes").mkdir(parents=True)
    (root / "context" / "meetings").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text(
        "# private meeting notes stay local\ndocumentation/meeting-notes/\n"
    )
    (root / "CLAUDE.md").write_text(
        "# Rules\n- One meeting = one file in context/meetings/.\n- Run the tests.\n"
    )
    (root / "documentation" / "meeting-notes" / "todo-week-2026-11-16.md").write_text(TODO)
    (root / "context" / "meetings" / "2026-11-20-wiley-call.md").write_text("# Call\n")
    private = tmp_path / "lab-private" / "meetings"
    private.mkdir(parents=True)
    (tmp_path / "lab-private" / "README.md").write_text(
        "- `meetings/` - meeting notes; this folder is the record.\n"
    )
    return root


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_paste_list_shows_label_after_each_paste(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["paste", "--list", "--session", "abc123"])
    out = capsys.readouterr().out
    assert "after:  sept 9" in out
    assert "after:  aug 27" in out


def test_paste_list_skips_sidechain_meta_and_queued_repeat(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["paste", "--list", "--session", "abc123"])
    out = capsys.readouterr().out
    assert "agent text" not in out
    assert "skill body" not in out
    assert out.count("teams message") == 1


def test_paste_list_numbers_prompts_without_gaps(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session.write_text("\n".join(json.dumps(e) for e in REPEATED_QUEUE_ENTRIES))
    meeting.main(["paste", "--list", "--session", "abc123"])
    assert "[1] prompt 2," in capsys.readouterr().out


def test_paste_default_saves_longest_paste_of_latest_prompt_verbatim(
    session: Path, tmp_path: Path
) -> None:
    out = tmp_path / "notes" / "2026-11-19-transcript.txt"
    meeting.main(["paste", "--session", "abc123", "--out", str(out)])
    assert out.read_text() == TRANSCRIPT


def test_paste_index_selects_an_older_paste(session: Path, tmp_path: Path) -> None:
    out = tmp_path / "older.txt"
    meeting.main(["paste", "--session", "abc123", "--index", "1", "--out", str(out)])
    assert out.read_text() == "Speaker 1: an older, longer call."


def test_paste_rejects_out_of_range_index(session: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="out of range: the session has pastes 0 to 3"):
        meeting.main(
            ["paste", "--session", "abc123", "--index", "9", "--out", str(tmp_path / "x.txt")]
        )


def test_paste_refuses_tracked_path_inside_repo(session: Path, repo: Path) -> None:
    with pytest.raises(SystemExit, match="not ignored, so a commit could publish"):
        meeting.main(
            ["paste", "--session", "abc123", "--out", str(repo / "docs" / "transcript.txt")]
        )


def test_paste_writes_ignored_path_inside_repo(session: Path, repo: Path) -> None:
    out = repo / "documentation" / "meeting-notes" / "2026-11-19-transcript.txt"
    meeting.main(["paste", "--session", "abc123", "--out", str(out)])
    assert out.read_text() == TRANSCRIPT


def test_paste_refuses_to_overwrite_other_content(session: Path, tmp_path: Path) -> None:
    out = write(tmp_path, "taken.txt", "another meeting")
    with pytest.raises(SystemExit, match="exists with different content"):
        meeting.main(["paste", "--session", "abc123", "--out", str(out)])


def test_paste_fails_without_session(session: Path) -> None:
    with pytest.raises(SystemExit, match="no session id"):
        meeting.main(["paste", "--list", "--session", ""])


def test_profile_counts_speakers_and_flags_generic_labels(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["profile", str(write(tmp_path, "t.txt", TRANSCRIPT))])
    out = capsys.readouterr().out
    assert "Speaker 1: 3 turns" in out
    assert "generic labels: Speaker 1, leo lee (You)" in out
    assert "end: last goodbye at line 5 of 5" in out


def test_profile_reads_granola_header(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    meeting.main(["profile", str(write(tmp_path, "g.txt", GRANOLA))])
    out = capsys.readouterr().out
    assert "header: Date: Nov 20 | Meeting participants: Wiley Simonds | Transcript:" in out
    assert "Me: 2 turns" in out


def test_profile_reports_timestamps_without_speakers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["profile", str(write(tmp_path, "loom.txt", LOOM))])
    out = capsys.readouterr().out
    assert "speakers: no labels found" in out
    assert "timestamps: 3 lines, 0:01 to 4:53" in out


def test_profile_warns_when_lines_follow_last_goodbye(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["profile", str(write(tmp_path, "late.txt", LATE_TAIL))])
    assert "last goodbye at line 1, 12 lines follow it" in capsys.readouterr().out


def test_records_reports_rules_ignores_and_folders(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["records", str(repo)])
    out = capsys.readouterr().out
    assert "CLAUDE.md:2: - One meeting = one file in context/meetings/." in out
    assert (
        ".gitignore:2: documentation/meeting-notes/   (# private meeting notes stay local)" in out
    )
    assert "documentation/meeting-notes/ - 1 files, ignored, local only" in out
    assert "context/meetings/ - 1 files, tracked by git, pushed with the repo" in out
    assert "todo-week-2026-11-16.md  1/4 done" in out


def test_records_reads_private_sibling_readme(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["records", str(repo)])
    out = capsys.readouterr().out
    assert "(not a git repo)" in out
    assert "README.md:1: - `meetings/` - meeting notes; this folder is the record." in out
    assert "meetings/ - 0 files, outside git, local only" in out


def test_todo_counts_sections_and_owners(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(["todo", str(write(tmp_path, "todo.md", TODO))])
    out = capsys.readouterr().out
    assert "1. Runs: 1/3 done" in out
    assert "total: 1/4 done; open: 1 agent, 1 Leo, 1 others" in out
    assert "L6 [agent] Collect AutoARIMA from job 23164608" in out
    assert "L7 [Leo] **Leo:** confirm the Monday meeting" in out


def test_todo_fails_without_checkboxes(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="has no checkbox items"):
        meeting.main(["todo", str(write(tmp_path, "plain.md", "# Notes\n- a bullet\n"))])


def test_quotes_pass_when_every_word_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(
        ["quotes", str(write(tmp_path, "n.md", NOTE)), str(write(tmp_path, "t.txt", SOURCE))]
    )
    assert "1/1 quotes found word for word" in capsys.readouterr().out


def test_quotes_fail_on_a_dropped_word(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        meeting.main(
            [
                "quotes",
                str(write(tmp_path, "n.md", NOTE_CHANGED)),
                str(write(tmp_path, "t.txt", SOURCE)),
            ]
        )
    assert exit_info.value.code == 1
    assert (
        'L1: "if I only tracked 20% of the sources, which 20 would be best"'
        in capsys.readouterr().out
    )


def test_quotes_accept_a_cut_marked_with_ellipsis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(
        ["quotes", str(write(tmp_path, "n.md", NOTE_CUT)), str(write(tmp_path, "t.txt", SOURCE))]
    )
    assert "1/1 quotes found word for word" in capsys.readouterr().out


def test_quotes_skip_the_gap_between_two_short_quotes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meeting.main(
        [
            "quotes",
            str(write(tmp_path, "n.md", NOTE_SHORT_QUOTES)),
            str(write(tmp_path, "t.txt", SOURCE)),
        ]
    )
    assert "0/0 quotes found word for word" in capsys.readouterr().out


def test_quotes_read_an_html_source_without_tags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    note = write(tmp_path, "n.md", NOTE_PAGE_QUOTE)
    meeting.main(
        [
            "quotes",
            str(note),
            str(write(tmp_path, "t.txt", SOURCE)),
            str(write(tmp_path, "page.html", PAGE)),
        ]
    )
    assert "1/1 quotes found word for word in t.txt, page.html" in capsys.readouterr().out
