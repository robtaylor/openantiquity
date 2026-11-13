"""What each leak test proved of the leak world's lines, so `tests/test_routes.py` can check that
every route's leak test read a line through that route as someone who sees only its square.

`tests.findings.test_leaks.draw_line` names each line it builds (`built`).
While a test runs, `tests/conftest.py` notes every request a test client
sends (`requested`): the route it went to, which built lines the reader
didn't see exactly when it was sent, and which of those its address, body
or response names. The reader is found from the session cookie the request
carries, as the app finds it, and each line is judged by
`sensitivity.sees_exact`.

`tests.findings.test_leaks.check` notes each text it checks and the levels
it checks are absent (`checked`). A response proves its route when the
checked text is the response's text or holds it, and it names a line the
reader didn't see exactly whose level is one of those. A route that serves
something of a line without naming it, such as a photo's bytes or a list
that leaves the line out, is proved by `checked_response`, which the test
calls once it has checked that response against the line.

The routes each test proved, across its parameters, are kept by test
function in `RESULTS` once the test passes. `COLLECTED` holds every test
function pytest is to run in this session.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

# A route as `tests/test_routes.py` names it: method and path.
Route = tuple[str, str]


@dataclass
class _Response:
    route: Route
    text: str | None
    # Each built line the reader saw only as its square when the request was sent, by public id,
    # with its level then.
    unseen: dict[str, str]
    # Those of them the request's address or body, or its response, names.
    named: set[str]


@dataclass
class _Current:
    lines: set[str] = field(default_factory=set)
    responses: list[_Response] = field(default_factory=list)
    # By id of the response object, for `checked_response`.
    by_object: dict[int, _Response] = field(default_factory=dict)
    proved: set[Route] = field(default_factory=set)


_current = _Current()
# By test function, as "module:name": the routes it proved, once it passed.
RESULTS: dict[str, set[Route]] = {}
# Every test function this session runs, as "module:name".
COLLECTED: set[str] = set()


def start() -> None:
    """Forget what the last test built and read. Called before each test is set up."""
    global _current
    _current = _Current()


def built(public_id: str) -> None:
    _current.lines.add(public_id)


def lines() -> set[str]:
    """The lines built by the test that is running."""
    return set(_current.lines)


def requested(
    response: object, route: Route | None, text: str | None, words: str, unseen: dict[str, str]
) -> None:
    """Note a request the test made and its response.

    `words` is the request's address and body, and the response's text when
    it was read. `unseen` holds each built line the reader didn't see
    exactly, with its level.
    """
    if route is None or not unseen:
        return
    named = {public_id for public_id in unseen if public_id in words}
    noted = _Response(route, text, unseen, named)
    _current.responses.append(noted)
    _current.by_object[id(response)] = noted


def checked(text: str, absent: Iterable[str]) -> None:
    """The test checked that `text` holds no exact position of a line at any of the levels `absent`."""
    levels = set(absent)
    for noted in _current.responses:
        if not noted.text or noted.text not in text:
            continue
        if any(noted.unseen[public_id] in levels for public_id in noted.named):
            _current.proved.add(noted.route)


def checked_response(response: object, public_id: str) -> None:
    """The test checked `response` against the line `public_id`, which the response needn't name.

    For a route that serves something of a line without naming it, such as
    a photo's bytes. It counts when the reader saw that line only as its square.
    """
    noted = _current.by_object.get(id(response))
    if noted is not None and public_id in noted.unseen:
        _current.proved.add(noted.route)


def finish(key: str) -> None:
    """Add the routes the test that just passed proved to its function's record."""
    RESULTS.setdefault(key, set()).update(_current.proved)
