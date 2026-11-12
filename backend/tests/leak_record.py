"""What each test built and read of the leak world's lines, so `tests/test_routes.py` can prove
that every route's leak test includes a line finding.

`tests.findings.test_leaks.draw_line` names each line it builds (`built`). While a
test runs, `tests/conftest.py` records every request a test client sends, its
address and body, and every response body it reads, and
`tests.findings.test_leaks.check` records every text it checks (`read`). A
test read a line when one of those texts names a line built for it. A route
that serves something of a line without naming it, such as a photo's bytes,
is read by passing the line's public id to `read` beside the request. The
results are kept by test function, across its parameters, in `RESULTS`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Proof:
    built: bool = False
    read: bool = False


@dataclass
class _Current:
    lines: set[str] = field(default_factory=set)
    read: bool = False


_current = _Current()
# By test function, as "module:name".
RESULTS: dict[str, Proof] = {}


def start() -> None:
    """Forget what the last test built and read. Called before each test is set up."""
    global _current
    _current = _Current()


def built(public_id: str) -> None:
    _current.lines.add(public_id)


def read(text: str) -> None:
    if not _current.read and any(public_id in text for public_id in _current.lines):
        _current.read = True


def finish(key: str) -> None:
    """Add what the test that just passed built and read to its function's proof."""
    proof = RESULTS.setdefault(key, Proof())
    proof.built |= bool(_current.lines)
    proof.read |= _current.read
