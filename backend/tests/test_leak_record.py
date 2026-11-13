"""What `tests.leak_record` counts as a leak test reading a line through a route.

`tests/test_routes.py` relies on it to prove that every route's leak test
read a line as someone who sees only its square. These tests drive the
record by hand, as `tests/conftest.py` and `tests.findings.test_leaks.check`
would, and check that the weaker readings it once accepted no longer count.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests import leak_record

ROUTE = ("GET", "/api/v1/findings")
OPEN, PROTECTED = "OPENLN", "PROTLN"


class Response:
    """Stands in for a response: the record keeps only its identity."""


@pytest.fixture
def record() -> Iterator[None]:
    leak_record.start()
    leak_record.built(OPEN)
    leak_record.built(PROTECTED)
    yield
    leak_record.start()


def proved() -> set[tuple[str, str]]:
    key = "tests.test_leak_record:scratch"
    leak_record.RESULTS.pop(key, None)
    leak_record.finish(key)
    return leak_record.RESULTS.pop(key)


@pytest.mark.usefixtures("record")
def test_a_response_checked_against_a_line_the_reader_sees_only_as_its_square_proves_its_route() -> None:
    text = f'{{"items": ["{OPEN}", "{PROTECTED}"]}}'
    leak_record.requested(Response(), ROUTE, text, text, {PROTECTED: "protected"})
    leak_record.checked(text, {"protected"})
    assert proved() == {ROUTE}


@pytest.mark.usefixtures("record")
def test_naming_only_the_open_line_proves_nothing() -> None:
    text = f'{{"items": ["{OPEN}"]}}'
    leak_record.requested(Response(), ROUTE, text, text, {PROTECTED: "protected"})
    leak_record.checked(text, {"protected"})
    assert proved() == set()


@pytest.mark.usefixtures("record")
def test_a_reader_who_sees_the_line_exactly_proves_nothing() -> None:
    text = f'{{"items": ["{OPEN}", "{PROTECTED}"]}}'
    leak_record.requested(Response(), ROUTE, text, text, {})
    leak_record.checked(text, set())
    assert proved() == set()


@pytest.mark.usefixtures("record")
def test_a_check_that_allows_the_line_s_level_proves_nothing() -> None:
    text = f'{{"items": ["{PROTECTED}"]}}'
    leak_record.requested(Response(), ROUTE, text, text, {PROTECTED: "protected"})
    leak_record.checked(text, set())
    assert proved() == set()


@pytest.mark.usefixtures("record")
def test_a_response_that_was_never_checked_proves_nothing() -> None:
    text = f'{{"items": ["{PROTECTED}"]}}'
    leak_record.requested(Response(), ROUTE, text, text, {PROTECTED: "protected"})
    leak_record.checked('{"items": []}', {"protected"})
    assert proved() == set()


@pytest.mark.usefixtures("record")
def test_a_response_that_names_no_line_is_proved_only_for_a_line_the_reader_does_not_see() -> None:
    photo = ("GET", "/api/v1/media/{media_id}")
    seen, unseen = Response(), Response()
    leak_record.requested(seen, photo, None, "/api/v1/media/1", {})
    leak_record.checked_response(seen, PROTECTED)
    assert proved() == set()
    leak_record.requested(unseen, photo, None, "/api/v1/media/1", {PROTECTED: "protected"})
    leak_record.checked_response(unseen, OPEN)
    assert proved() == set()
    leak_record.checked_response(unseen, PROTECTED)
    assert proved() == {photo}
