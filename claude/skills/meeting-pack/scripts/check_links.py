#!/usr/bin/env python3
"""Check a built meeting page before Leo shows it:
- every #anchor link has a target id on the page,
- every relative link points to a file that exists next to the page,
- every item (li, or table row with cells) in the quick-summary section carries a link,
  because each summary line must open its proof (Leo, 2026-11-19),
- the visible text holds no em dash (Leo's writing rule) and no markdown link that failed to
  render (a builder can leave "[text](url)" as plain text, for example around a code span),
- with --remote, every http(s) link answers below 400 (a GitHub Pages deploy lags the push).

Prints one line per problem with the bad value, then a count. Exit 1 on any problem.

Usage: check_links.py PAGE.html [--summary SECTION_ID] [--remote]
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})
SKIP_TEXT_TAGS = frozenset({"script", "style", "template"})
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")
EM_DASH = "\u2014"  # escaped so this file passes its own rule
RAW_MARKDOWN_LINK = re.compile(r"\]\((?:https?://|#|\.{0,2}/)[^)\s]*\)")
TEXT_CHARS = 60
REMOTE_TIMEOUT_S = 15
USER_AGENT = "meeting-pack-link-check"


@dataclass
class Item:
    tag: str
    text: list[str] = field(default_factory=list)
    linked: bool = False
    has_cells: bool = False


class PageParser(HTMLParser):
    def __init__(self, summary_id: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.summary_id = summary_id
        self.ids: set[str] = set()
        self.links: list[tuple[str, str]] = []  # (href, link text)
        self.items: list[Item] = []
        self.summary_found = False
        self.em_dash_text: list[str] = []
        self.raw_links: list[str] = []
        self._stack: list[str] = []
        self._summary_depth: int | None = None
        self._open_items: list[Item] = []
        self._open_link: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a" and values.get("name"):
            self.ids.add(values["name"])
        if tag in SKIP_TEXT_TAGS:
            self._skip_depth += 1
        in_summary = self._summary_depth is not None
        for item in self._open_items:
            item.text.append(" ")  # keeps cell and line text apart in the message
        if tag == "a" and "href" in values:
            self._open_link = [values["href"]]
            if in_summary:
                for item in self._open_items:
                    item.linked = True
        if in_summary and tag in ("li", "tr"):
            self._open_items.append(Item(tag=tag))
        if in_summary and tag == "td":
            for item in self._open_items:
                if item.tag == "tr":
                    item.has_cells = True
        if tag in VOID_TAGS:
            return
        self._stack.append(tag)
        if self.summary_id and values.get("id") == self.summary_id and self._summary_depth is None:
            self._summary_depth = len(self._stack)
            self.summary_found = True

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TEXT_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "a" and self._open_link is not None:
            href, *text = self._open_link
            self.links.append((href, " ".join("".join(text).split())))
            self._open_link = None
        if tag not in self._stack:
            return
        while self._stack:
            popped = self._stack.pop()
            if popped in ("li", "tr") and self._open_items and self._open_items[-1].tag == popped:
                self.items.append(self._open_items.pop())
            if popped == tag:
                break
        if self._summary_depth is not None and len(self._stack) < self._summary_depth:
            self._summary_depth = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if EM_DASH in data:
            self.em_dash_text.append(" ".join(data.split())[:TEXT_CHARS])
        self.raw_links += RAW_MARKDOWN_LINK.findall(data)
        if self._open_link is not None:
            self._open_link.append(data)
        for item in self._open_items:
            item.text.append(data)


def summary_problems(parser: PageParser) -> list[str]:
    if not parser.summary_id:
        return []
    if not parser.summary_found:
        return [f"summary section not found: no element with id={parser.summary_id!r}"]
    problems = []
    for item in parser.items:
        if item.tag == "tr" and not item.has_cells:
            continue  # a header row
        if not item.linked:
            text = " ".join("".join(item.text).split())[:TEXT_CHARS]
            problems.append(f"summary item without a link: {text!r}")
    return problems


def local_problems(parser: PageParser, page: Path) -> list[str]:
    problems = []
    for href, text in parser.links:
        if not href or href.startswith(SKIP_SCHEMES) or urlsplit(href).scheme in ("http", "https"):
            continue
        if href.startswith("#"):
            target = unquote(href[1:])
            if target and target not in parser.ids:
                problems.append(f"missing anchor target: {href} (link text {text!r})")
            continue
        path = unquote(urlsplit(href).path)
        if href.startswith("//") or not path:
            continue
        target = (page.parent / path).resolve()
        if path.endswith("/"):
            target = target / "index.html"
        if not target.exists():
            problems.append(f"missing file: {href} (resolved to {target})")
    return problems


def remote_status(url: str) -> int | str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REMOTE_TIMEOUT_S) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return f"no answer ({exc})"


def remote_problems(parser: PageParser) -> list[str]:
    urls = sorted({href.split("#")[0] for href, _ in parser.links if urlsplit(href).scheme in ("http", "https")})
    problems = []
    for url in urls:
        status = remote_status(url)
        if not isinstance(status, int) or status >= 400:
            problems.append(f"dead link: {url} ({status})")
    return problems


def check(page: Path, summary_id: str | None, remote: bool) -> tuple[list[str], PageParser]:
    if not page.is_file():
        raise FileNotFoundError(f"page not found: {page}")
    parser = PageParser(summary_id)
    parser.feed(page.read_text(errors="replace"))
    parser.close()
    problems = local_problems(parser, page) + summary_problems(parser)
    problems += [f"em dash in page text: {text!r}" for text in parser.em_dash_text]
    problems += [f"markdown link shown as text: {raw!r}" for raw in parser.raw_links]
    if remote:
        problems += remote_problems(parser)
    return problems, parser


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("page", help="the built HTML page")
    parser.add_argument("--summary", help="id of the quick-summary section; every item in it must link")
    parser.add_argument("--remote", action="store_true", help="also fetch every http(s) link")
    args = parser.parse_args(argv)
    try:
        problems, page = check(Path(args.page).resolve(), args.summary, args.remote)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for problem in problems:
        print(problem)
    summary_items = len([i for i in page.items if i.tag == "li" or i.has_cells])
    print(f"{len(problems)} problem(s); {len(page.links)} links, {summary_items} summary items checked")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
