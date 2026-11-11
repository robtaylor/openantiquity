"""`services.notes_markdown`: the notebook's small part of Markdown, as HTML for the printable report.

The cases follow `frontend/src/features/investigations/notesSyntax.test.ts`,
so the report reads a note as the notebook does. Most of the file is hostile
text: HTML, scripts in addresses, images, and notes of the longest length
made of markers that never close, which must render in well under a second.
"""

from __future__ import annotations

import time
from html.parser import HTMLParser

import pytest

from fieldclub.services.notes_markdown import MAX_DEPTH, render, render_inline, safe_href, shown_text
from fieldclub.services.text_positions import PLACEHOLDER, holds_position, redact

NOTES_MAX = 50_000
REL = 'rel="noopener noreferrer external nofollow"'


def a(href: str, words: str) -> str:
    return f'<a href="{href}" {REL}>{words}</a>'


# --------------------------------------------------------------------------
# The subset
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("A bank and a ditch", "A bank and a ditch"),
        (
            "a **big** bank, *faint* and _low_",
            "a <strong>big</strong> bank, <em>faint</em> and <em>low</em>",
        ),
        ("**very *faint***", "<strong>very <em>faint</em></strong>"),
        ("2 * 3 and ** and **", "2 * 3 and ** and **"),
        ("snake_case_name", "snake_case_name"),
        (
            "see [the HER](https://example.org/her?id=1) entry",
            f"see {a('https://example.org/her?id=1', 'the HER')} entry",
        ),
        ("[a **bold** link](http://example.org/)", a("http://example.org/", "a <strong>bold</strong> link")),
        ("\\*not emphasis\\*", "*not emphasis*"),
        ("an [open bracket and no link", "an [open bracket and no link"),
        ("[a](https://example.org/(b)c)", a("https://example.org/(b)c", "a")),
    ],
)
def test_inline(source: str, expected: str) -> None:
    assert render_inline(source) == expected


def test_headings_paragraphs_and_both_kinds_of_list() -> None:
    source = "\n".join(
        [
            "# The parish",
            "",
            "Two lines of one",
            "paragraph.",
            "",
            "- first",
            "* second",
            "",
            "1. one",
            "2. two",
        ]
    )
    assert render(source, 3) == (
        "<h3>The parish</h3><p>Two lines of one paragraph.</p>"
        "<ul><li>first</li><li>second</li></ul><ol><li>one</li><li>two</li></ol>"
    )


def test_heading_levels_start_where_the_caller_says_and_use_three() -> None:
    source = "# One\n## Two\n### Three\n###### Six ##"
    assert render(source, 4) == "<h4>One</h4><h5>Two</h5><h6>Three</h6><h6>Six</h6>"
    assert render(source, 3) == "<h3>One</h3><h4>Two</h4><h5>Three</h5><h5>Six</h5>"


def test_a_list_ends_where_a_paragraph_starts_and_an_indented_line_folds_into_its_item() -> None:
    assert render("- a bank\n  that runs north\nAfter the list", 3) == (
        "<ul><li>a bank that runs north</li></ul><p>After the list</p>"
    )


def test_headings_need_a_space_and_stop_at_six() -> None:
    assert render("####### seven\n#tag", 3) == "<p>####### seven #tag</p>"


def test_empty_text_and_windows_line_ends() -> None:
    assert render("", 3) == ""
    assert render("\n \n", 3) == ""
    assert render("## A\r\n\r\nB", 3) == "<h4>A</h4><p>B</p>"


# --------------------------------------------------------------------------
# Hostile text
# --------------------------------------------------------------------------

ALLOWED = {"p", "h3", "h4", "h5", "h6", "ul", "ol", "li", "strong", "em", "a"}


class Parsed(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.extend(attrs)


def parsed(source: str) -> Parsed:
    page = Parsed()
    page.feed(render(source, 3))
    page.close()
    return page


HOSTILE_HTML = [
    '<script>alert("x")</script>',
    '<img src=x onerror="alert(1)">',
    "</p><iframe src=//evil.example></iframe>",
    '<a href="javascript:alert(2)">click</a>',
    "<svg onload=alert(3)>",
    "<style>body{display:none}</style>",
    "\\<script>alert(4)\\</script>",
    "# <b onclick=alert(5)>heading</b>",
    "- <i>item</i>\n1. <u>item</u>",
    "**<script>**",
    "&lt;script&gt; and &amp; and &#x3C;",
]


@pytest.mark.parametrize("source", HOSTILE_HTML)
def test_html_in_a_note_stays_the_characters_it_is(source: str) -> None:
    page = parsed(source)
    assert set(page.tags) <= ALLOWED, set(page.tags) - ALLOWED
    assert page.attributes == []
    # What a reader sees is the text as typed, markers aside.
    assert "<" not in source or "<" in shown_text(render(source, 3))
    assert "&lt;script&gt;" in shown_text(render("&lt;script&gt;", 3))


HOSTILE_ADDRESSES = [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)",
    "java\tscript:alert(1)",
    "java%0Ascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "mailto:someone@example.org",
    "ftp://example.org/file",
    "//evil.example/path",
    "/relative/path",
    "relative",
    "https:evil.example",
    "https:///nohost",
    "http://",
    "\\\\evil.example\\share",
    "https://exa\u0000mple.org",
    "https://example.org/\u202e",
]


@pytest.mark.parametrize("address", HOSTILE_ADDRESSES)
def test_only_a_whole_http_or_https_address_becomes_a_link(address: str) -> None:
    assert safe_href(address.strip()) is None
    page = parsed(f"[words]({address})")
    assert "a" not in page.tags, address
    assert "words" in shown_text(render(f"[words]({address})", 3))


def test_an_address_cannot_break_out_of_its_attribute() -> None:
    source = '[x](https://example.org/"onmouseover="alert(1)) and [y](https://example.org/\'><script>)'
    page = parsed(source)
    assert [name for name, _ in page.attributes] == ["href", "rel", "href", "rel"]
    hrefs = [value for name, value in page.attributes if name == "href"]
    assert hrefs == ['https://example.org/"onmouseover="alert(1)', "https://example.org/'><script>"]
    assert "script" not in page.tags


def test_there_are_no_images() -> None:
    page = parsed("![a photo](https://example.org/photo.jpg)")
    assert "img" not in page.tags
    assert page.tags == ["p", "a"]


def test_markup_cannot_put_together_a_position_the_text_does_not_hold() -> None:
    """`SU 123**456**` reads as `SU 123456` once the stars go, which redaction never saw."""
    for source in (
        "At SU 123**456**.",
        "At SU 12*3456*.",
        "At [SU 123](https://example.org/)456.",
        "At SU 123\\.456.",
    ):
        assert not holds_position(source), source
        assert redact(source) == source
        html = render(source, 3)
        assert not holds_position(shown_text(html)), source
        assert html == f'<p class="text">{source.replace("<", "&lt;")}</p>', source
    # Text that holds a position already is the reader's to see, and is rendered as usual.
    assert render("At **SU 123 456**.", 3) == "<p>At <strong>SU 123 456</strong>.</p>"
    hidden = redact("At SU 123 456, *faint*.")
    assert PLACEHOLDER in hidden
    assert render(hidden, 3) == f"<p>At {PLACEHOLDER}, <em>faint</em>.</p>"


def test_emphasis_nests_no_deeper_than_it_allows() -> None:
    html = render_inline(f"{'**' * 20}x{'**' * 20}")
    assert html.count("<strong>") == MAX_DEPTH
    assert "**" in html


def test_a_long_ordinary_note_still_reads_its_emphasis_and_links() -> None:
    paragraph = "A bank, *faint*, beside a **ditch**; see [the HER](https://example.org/her). " * 600
    assert len(paragraph) <= NOTES_MAX
    html = render(paragraph, 3)
    assert html.count("<a ") == 600
    assert html.count("<em>") == 600
    assert html.count("<strong>") == 600


def _timed(source: str) -> float:
    """The best of three, so a busy machine doesn't decide it."""
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        render(source, 3)
        best = min(best, time.perf_counter() - start)
    return best


SLOW_CASES = {
    "unclosed underscores": "_a " * 17000,
    "unclosed stars": "*a " * 17000,
    "unclosed doubles": "**a " * 13000,
    "openers before a closer that ends mid-word": "_x " * 17000 + "a_b",
    "unfinished links": "[a](" * 12500,
    "brackets": "[" * 50000 + "](https://example.org)",
    "deep nesting": "**" * 12500 + "x" + "**" * 12500,
    "a long line of spaces": " " * 50000 + "x",
    "only stars": "*" * 50000,
    "only underscores": "_" * 50000,
    "only backslashes and stars": "\\*" * 25000,
    "stars after words": "a*" * 25000,
    "doubles after words": "a**" * 16666,
    "unbalanced brackets in an address": "[a](" + "(" * 49990,
    "label ends without addresses": "[a](b c" * 7200,
    "lists of openers": "- *a\n" * 10000,
    "headings of openers": "# **a\n" * 8400,
    "hashes and spaces": "# " + " #" * 25000,
}


@pytest.mark.parametrize("name", list(SLOW_CASES))
def test_a_hostile_note_of_the_longest_length_renders_quickly(name: str) -> None:
    source = SLOW_CASES[name]
    assert len(source) >= NOTES_MAX - 10, name
    assert _timed(source[:NOTES_MAX]) < 0.25, name
