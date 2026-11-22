"""Tests for check_links.py. Run: python3 -m pytest ~/dotfiles/claude/skills/meeting-pack/scripts -q"""

from pathlib import Path

import pytest

import check_links

LINKED_SUMMARY = """<html><body>
<section id="quick"><ul>
  <li><b>Rivanna works.</b> <a href="#rivanna">Details</a></li>
  <li>Tuning window: ours -12.6% <a href="#panel-tuning">Tables</a></li>
</ul></section>
<section id="rivanna"><h2>Rivanna</h2></section>
<div id="panel-tuning"></div>
</body></html>"""

UNLINKED_ITEM = """<section id="quick"><ul>
  <li>Rivanna works. <a href="#rivanna">Details</a></li>
  <li>Diagnosis is the result that holds.</li>
</ul></section><section id="rivanna"></section>"""

GLANCE_TABLE = """<section id="glance"><table>
  <thead><tr><th>Topic</th><th>Result</th></tr></thead>
  <tbody>
    <tr><td><a href="#asked">Asks</a></td><td>done</td></tr>
    <tr><td>Held-out split</td><td>done</td></tr>
  </tbody></table></section><section id="asked"></section>"""

UNCLOSED_ITEMS = """<section id="quick"><ul>
  <li>First result <a href="#a">proof</a>
  </ul><p>After the list <a href="#a">x</a></p>
</section><div id="a"></div>"""

BROKEN_LINKS = """<a href="#nowhere">jump</a>
<a href="data/sweep.json">data</a>
<a href="../2026-11-05/">last week</a>
<a href="mailto:x@example.com">mail</a>
<a href="https://example.com/x">site</a>"""

EM_DASH_PAGE = "<p>Result \u2014 better</p><script>const s = '\u2014';</script>"


def write_page(tmp_path: Path, html: str, name: str = "index.html") -> Path:
    page = tmp_path / "2026-11-19" / name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(html)
    return page


def test_check_passes_a_fully_linked_summary(tmp_path: Path) -> None:
    problems, _ = check_links.check(write_page(tmp_path, LINKED_SUMMARY), "quick", remote=False)

    assert problems == []


def test_check_flags_a_summary_item_without_a_link(tmp_path: Path) -> None:
    problems, _ = check_links.check(write_page(tmp_path, UNLINKED_ITEM), "quick", remote=False)

    assert problems == ["summary item without a link: 'Diagnosis is the result that holds.'"]


def test_check_skips_table_header_rows_in_the_summary(tmp_path: Path) -> None:
    problems, _ = check_links.check(write_page(tmp_path, GLANCE_TABLE), "glance", remote=False)

    assert problems == ["summary item without a link: 'Held-out split done'"]


def test_check_ends_the_summary_at_its_closing_tag(tmp_path: Path) -> None:
    problems, parser = check_links.check(write_page(tmp_path, UNCLOSED_ITEMS), "quick", remote=False)

    assert (problems, len(parser.items)) == ([], 1)


def test_check_flags_a_missing_summary_section(tmp_path: Path) -> None:
    problems, _ = check_links.check(write_page(tmp_path, LINKED_SUMMARY), "glance", remote=False)

    assert problems == ["summary section not found: no element with id='glance'"]


def test_check_flags_missing_anchors_and_files(tmp_path: Path) -> None:
    page = write_page(tmp_path, BROKEN_LINKS)

    problems, _ = check_links.check(page, None, remote=False)

    assert problems == [
        "missing anchor target: #nowhere (link text 'jump')",
        f"missing file: data/sweep.json (resolved to {page.parent.resolve() / 'data' / 'sweep.json'})",
        f"missing file: ../2026-11-05/ (resolved to {tmp_path.resolve() / '2026-11-05' / 'index.html'})",
    ]


def test_check_accepts_a_relative_folder_with_an_index(tmp_path: Path) -> None:
    write_page(tmp_path, "<p>old</p>").rename(tmp_path / "2026-11-19" / "keep.html")
    (tmp_path / "2026-11-05").mkdir()
    (tmp_path / "2026-11-05" / "index.html").write_text("<p>last week</p>")

    problems, _ = check_links.check(write_page(tmp_path, '<a href="../2026-11-05/">last week</a>'), None, remote=False)

    assert problems == []


def test_check_flags_em_dashes_in_visible_text_only(tmp_path: Path) -> None:
    problems, _ = check_links.check(write_page(tmp_path, EM_DASH_PAGE), None, remote=False)

    assert problems == ["em dash in page text: 'Result \u2014 better'"]


def test_check_flags_a_markdown_link_left_as_text(tmp_path: Path) -> None:
    page = write_page(tmp_path, "<td>[<code>scripts/slurm/</code>](https://github.com/o/r/tree/abc/scripts/slurm)</td>")

    problems, _ = check_links.check(page, None, remote=False)

    assert problems == ["markdown link shown as text: '](https://github.com/o/r/tree/abc/scripts/slurm)'"]


def test_check_reports_dead_remote_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_links, "remote_status", lambda url: 404)

    problems, _ = check_links.check(write_page(tmp_path, BROKEN_LINKS), None, remote=True)

    assert problems[-1] == "dead link: https://example.com/x (404)"


def test_main_fails_loudly_on_a_missing_page(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = check_links.main([str(tmp_path / "none.html")])

    assert (code, capsys.readouterr().err) == (1, f"error: page not found: {tmp_path.resolve() / 'none.html'}\n")
