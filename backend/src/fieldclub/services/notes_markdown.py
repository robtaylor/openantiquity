"""An investigation's notes as HTML, read with the same small part of Markdown the notebook uses.

Headings, paragraphs, bulleted and numbered lists, strong, emphasis and links,
as `frontend/src/features/investigations/notesSyntax.ts` reads them, and
nothing else. Every piece of text is escaped, so HTML in a note stays the
characters it is. A link becomes one only for an `http` or `https` address
with a host (`safe_href`), and is otherwise shown as its words. There are no
images: `![words](address)` is an exclamation mark and a link.

Markup must not put together a position that the text as typed doesn't
hold. `SU 123**456**` reads as `SU 123456` once the stars are gone, and
`services.text_positions` wouldn't have hidden it in the text as typed. So
when the rendered words hold a position and the text doesn't, the note is
shown as written instead, as plain escaped text.

Notes come from other people and can be 50,000 characters long, so the work
is bounded whatever is in them. Looking ahead for a closing marker or the end
of a link is the only costly part. Each run of text remembers its last search
for each marker, every look ahead draws on one budget proportional to the
note's length, and each place a search stops to look costs a fixed share of
it. Once the budget is spent, what is left is shown as written. Emphasis
nests at most `MAX_DEPTH` deep, and an address is at most `MAX_ADDRESS` long.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fieldclub.services.text_positions import holds_position

MAX_DEPTH = 8
MAX_ADDRESS = 2048
BUDGET_PER_CHAR = 40
# What one stop of a search costs, in characters, on top of the characters it passes over.
STOP_COST = 20

_ESCAPABLE = frozenset("\\*_[]()#-+.")
_SPECIAL = re.compile(r"[\\*_\[]")
_BACKSLASH = re.compile(r"\\")
_PAREN_STOP = re.compile(r"[()\n ]")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s{0,3}\d{1,9}[.)]\s+(.*)$")
_LINES = re.compile(r"\r\n?|\n")
_LINK_REL = "noopener noreferrer external nofollow"
# The tags `render` writes. A block's end reads as a line break, any other tag as nothing.
_BLOCK_END = re.compile(r"</(?:p|h[1-6]|li|ul|ol)>")
_TAG = re.compile(r"<[^>]*>")


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _is_word(char: str) -> bool:
    """JavaScript's `\\w`: an ASCII letter, digit or underscore."""
    return char.isascii() and (char.isalnum() or char == "_")


def safe_href(value: str) -> str | None:
    """The address, when it is a whole `http` or `https` address with a host. Otherwise None."""
    if not value or len(value) > MAX_ADDRESS:
        return None
    # Spaces, control and format characters (a right-to-left override among them), and backslashes,
    # which browsers read as slashes.
    if any(char.isspace() or char == "\\" or unicodedata.category(char).startswith("C") for char in value):
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None
    return value


@dataclass
class _Budget:
    left: int


@dataclass
class _Run:
    """The searches made in one run of text, which nested runs don't share."""

    budget: _Budget
    # The last search for each closing marker: where it started and what it found.
    closers: dict[str, tuple[int, int]] = field(default_factory=dict)
    # The same for the `](` that ends a link's words.
    label_end: tuple[int, int] | None = None

    def spend(self, characters: int) -> bool:
        """Charge a stop of a search that passed over `characters`. False once the budget is spent."""
        self.budget.left -= characters + STOP_COST
        return self.budget.left >= 0


def _escaped(source: str, at: int, start: int) -> bool:
    """Whether the character at `at` follows an odd run of backslashes that begins at or after `start`."""
    back = at
    while back > start and source[back - 1] == "\\":
        back -= 1
    return (at - back) % 2 == 1


def _closing(source: str, marker: str, start: int, run: _Run) -> int:
    """Where a `**`, `*` or `_` that closes emphasis opened before `start` is, or -1."""
    # The first closer after an earlier start is also the first after any later start before it.
    last = run.closers.get(marker)
    if last is not None and start > last[0] and (last[1] < 0 or start < last[1]):
        return last[1]
    char, at, found = marker[0], start, -1
    while True:
        index = source.find(char, at)
        if not run.spend((index if index >= 0 else len(source)) - at):
            return -1
        if index < 0:
            break
        at = index + 1
        if _escaped(source, index, start):
            continue
        if len(marker) == 2:
            if not source.startswith(marker, index):
                continue
            # In a run of three, as in `***`, the double marker is the last two: the first closes inside.
            if source.startswith("*", index + 2):
                continue
        elif source.startswith(marker, index + 1) and not source.startswith(marker, index + 2):
            # Half of a double marker belongs to that, unless it closes at the end of the double.
            at = index + 2
            continue
        if index == start or source[index - 1].isspace():
            continue
        found = index
        break
    run.closers[marker] = (start, found)
    return found


def _closing_paren(source: str, start: int, run: _Run) -> int:
    """Where the `)` that closes an address starting at `start` is, allowing balanced brackets, or -1."""
    depth, at = 0, start
    end = min(len(source), start + MAX_ADDRESS)
    while True:
        stop = _PAREN_STOP.search(source, at, end)
        if not run.spend((stop.start() if stop else end) - at):
            return -1
        if stop is None:
            return -1
        char, at = stop.group(), stop.end()
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return stop.start()
            depth -= 1
        else:
            return -1


def _label_end(source: str, start: int, run: _Run) -> int:
    """The `](` at or after `start`, or -1, remembering the search as `_closing` does."""
    last = run.label_end
    if last is not None and start > last[0] and (last[1] < 0 or start <= last[1]):
        return last[1]
    found = source.find("](", start)
    run.spend((len(source) if found < 0 else found) - start)
    run.label_end = (start, found)
    return found


def _link(source: str, start: int, run: _Run) -> tuple[str, str, int] | None:
    """`[words](address)` starting at `start`: the words, the address and where it ends, or None."""
    if run.budget.left < 0:
        return None
    label_end = _label_end(source, start + 1, run)
    if label_end < 0:
        return None
    # Words with a `[` of their own aren't a link's.
    bracket = source.find("[", start + 1, label_end)
    if bracket >= 0:
        return None
    href_end = _closing_paren(source, label_end + 2, run)
    if href_end < 0:
        return None
    return source[start + 1 : label_end], source[label_end + 2 : href_end], href_end + 1


def _inline(source: str, budget: _Budget, depth: int) -> str:
    run = _Run(budget)
    # Deeper than this, markers are shown as written.
    nests = depth < MAX_DEPTH
    special = _SPECIAL if nests else _BACKSLASH
    out: list[str] = []
    at, size = 0, len(source)
    while at < size:
        found = special.search(source, at)
        if found is None:
            out.append(_e(source[at:]))
            break
        if found.start() > at:
            out.append(_e(source[at : found.start()]))
        at = found.start()
        char = source[at]
        if char == "\\":
            following = source[at + 1 : at + 2]
            if following and following in _ESCAPABLE:
                out.append(_e(following))
                at += 2
            else:
                out.append(_e(char))
                at += 1
            continue
        if char in "*_":
            double = char == "*" and source.startswith("**", at)
            marker = "**" if double else char
            start = at + len(marker)
            opens_word = start < size and not source[start].isspace()
            # `_` inside a word, as in snake_case, is a letter, not emphasis.
            mid_word = char == "_" and at > 0 and _is_word(source[at - 1])
            end = _closing(source, marker, start, run) if opens_word and not mid_word else -1
            closes_word = end >= 0 and not (char == "_" and end + 1 < size and _is_word(source[end + 1]))
            if end > start and closes_word:
                tag = "strong" if double else "em"
                out.append(f"<{tag}>{_inline(source[start:end], budget, depth + 1)}</{tag}>")
                at = end + len(marker)
            else:
                out.append(marker)
                at = start
            continue
        link = _link(source, at, run)
        if link is None:
            out.append("[")
            at += 1
            continue
        words, address, at = link
        inner = _inline(words, budget, depth + 1)
        href = safe_href(address.strip())
        out.append(f'<a href="{_e(href)}" rel="{_LINK_REL}">{inner}</a>' if href is not None else inner)
    return "".join(out)


def render_inline(source: str) -> str:
    """One line's, or one paragraph's, emphasis and links, as escaped HTML."""
    return _inline(source, _Budget(BUDGET_PER_CHAR * len(source) + 1000), 0)


def _heading_text(text: str) -> str:
    """A heading's words without the closing hashes Markdown allows, as in `## Notes ##`."""
    return text.rstrip().rstrip("#").rstrip()


def shown_text(rendered: str) -> str:
    """The words a reader sees in HTML `render` wrote, with a line break after each block."""
    return html.unescape(_TAG.sub("", _BLOCK_END.sub("\n", rendered)))


def render(source: str, top_level: int) -> str:
    """A note as escaped HTML. Its first-level headings become `<h{top_level}>`.

    A note's second-level headings take the level below, and every deeper one
    the level below that, as the notebook shows them. A note whose markup
    would put together a position the text doesn't hold is shown as written.
    """
    rendered = _render(source, top_level)
    if holds_position(shown_text(rendered)) and not holds_position(source):
        return f'<p class="text">{_e(source)}</p>'
    return rendered


def _render(source: str, top_level: int) -> str:
    assert 1 <= top_level <= 4, "a note's three heading levels must fit in h1 to h6"
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    ordered: bool | None = None

    def flush() -> None:
        nonlocal ordered
        if paragraph:
            blocks.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()
        if ordered is not None:
            tag = "ol" if ordered else "ul"
            listed = "".join(f"<li>{render_inline(item)}</li>" for item in items)
            blocks.append(f"<{tag}>{listed}</{tag}>")
            items.clear()
            ordered = None

    for raw in _LINES.split(source):
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        heading = _HEADING.match(line)
        if heading is not None and not paragraph:
            flush()
            level = top_level + min(len(heading.group(1)), 3) - 1
            blocks.append(f"<h{level}>{render_inline(_heading_text(heading.group(2)))}</h{level}>")
            continue
        bullet = _BULLET.match(line)
        numbered = None if bullet is not None else _NUMBERED.match(line)
        item = bullet or numbered
        if item is not None:
            is_ordered = numbered is not None
            if paragraph or (ordered is not None and ordered is not is_ordered):
                flush()
            ordered = is_ordered
            items.append(item.group(1).strip())
            continue
        if ordered is not None and raw[:1].isspace():
            items[-1] = f"{items[-1]} {line.strip()}"
            continue
        if ordered is not None:
            flush()
        paragraph.append(line.strip())
    flush()
    return "".join(blocks)
