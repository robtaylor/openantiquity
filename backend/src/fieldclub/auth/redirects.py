"""Where to send someone after sign-in: a relative path on this site, and nothing else.

`next` arrives from the browser, so it is attacker-controlled. A value that
a browser could read as another host (`//evil.example`, `/\\evil.example`,
`/%5Cevil.example`, a tab or newline that browsers strip) or as a scheme
(`javascript:`) would turn the sign-in flow into an open redirect. Rather than
try to list every trick, a path is accepted only when it is printable ASCII
starting with exactly one slash, and still starts that way, with no backslash
and no control or invisible character, however many times it is
percent-decoded. Anything else becomes `/`.

The redirect itself is always built as `public_url + path`, so even a path
that slipped through would stay on this site's host.
"""

from __future__ import annotations

import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from fieldclub.config import Settings

DEFAULT_NEXT = "/"
MAX_NEXT_LENGTH = 2000
# Percent-decoding is repeated this many times when checking, which is more
# layers than any browser or proxy applies.
_DECODE_ROUNDS = 3
# Controls (tab, newline, NUL), format characters (bidirectional overrides,
# zero-width), and line and paragraph separators.
_FORBIDDEN_DECODED = frozenset({"Cc", "Cf", "Zl", "Zp"})


def _looks_local(path: str, *, raw: bool) -> bool:
    """One form of a path is a plain absolute path on this host.

    The path as sent must be printable ASCII with no spaces. Decoded forms may
    hold spaces and other text, but never a control or invisible formatting
    character, which browsers strip or render in ways that change the path.
    """
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return False
    if raw:
        if not all(0x21 <= ord(char) <= 0x7E for char in path):
            return False
    elif any(unicodedata.category(char) in _FORBIDDEN_DECODED for char in path):
        return False
    parts = urlsplit(path)
    return not parts.scheme and not parts.netloc


def safe_next(raw: str | None) -> str:
    """`raw` if it is a relative path on this site, otherwise `/`."""
    if not raw or len(raw) > MAX_NEXT_LENGTH or not _looks_local(raw, raw=True):
        return DEFAULT_NEXT
    value = raw
    for _ in range(_DECODE_ROUNDS):
        decoded = unquote(value)
        if decoded == value:
            return raw
        if not _looks_local(decoded, raw=False):
            return DEFAULT_NEXT
        value = decoded
    # Still changing after every round: encoded more deeply than anything legitimate.
    return DEFAULT_NEXT


def app_url(settings: Settings, path: str, **query: str) -> str:
    """An absolute address on the app for a path `safe_next` accepted, with query values added."""
    assert safe_next(path) == path, f"{path!r} is not a safe local path"
    base = settings.public_url.rstrip("/")
    parts = urlsplit(path)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    pairs = [(key, value) for key, value in pairs if key not in query] + sorted(query.items())
    return base + urlunsplit(("", "", parts.path, urlencode(pairs), parts.fragment))
