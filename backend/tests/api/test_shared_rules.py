"""Rules every list and every box follows, whichever track built the route.

- A `bbox` is four finite numbers with west < east and south < north, and a
  bad one is 400 `invalid_bbox` (`schemas.common.parse_bbox`).
- A cursor that is wrong in any way is 400 `invalid_cursor`, and no offset
  held in one goes past `schemas.common.MAX_OFFSET`.
- A limit above a list's maximum is 422 `validation_error`.
- A filter with several values is a repeated parameter with typed values.
"""

from __future__ import annotations

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.schemas.common import MAX_OFFSET, encode_cursor
from tests.findings.support import create
from tests.helpers import ClientAs, MakeUser, add_record, add_source, error_code

API = "/api/v1"


def with_params(path: str, **params: object) -> str:
    """`path` with `params` added to any query it already has. A list value is a repeated parameter."""
    pairs = [
        (name, value)
        for name, values in params.items()
        for value in (values if isinstance(values, list) else [values])
    ]
    return f"{path}{'&' if '?' in path else '?'}{urlencode(pairs)}"


BOX_ROUTES = [
    f"{API}/findings",
    f"{API}/findings/export",
    f"{API}/records/search",
    f"{API}/terrain/coverage",
]
BAD_BOXES = [
    "1,2,3",
    "1,2,3,4,5",
    "a,b,c,d",
    "nan,51,0,52",
    "-1,51,inf,52",
    "0,51,0,52",  # no width
    "-1,51,0,51",  # no height
    "0,51,-1,52",  # west of west
    "-200,51,0,52",
    "",
]


@pytest.mark.parametrize("path", BOX_ROUTES)
@pytest.mark.parametrize("bbox", BAD_BOXES)
def test_a_bad_box_is_invalid_bbox_everywhere(client: TestClient, path: str, bbox: str) -> None:
    response = client.get(path, params={"bbox": bbox})
    assert response.status_code == 400, response.text
    assert error_code(response) == "invalid_bbox"


@pytest.mark.parametrize("path", BOX_ROUTES)
def test_a_good_box_is_taken_everywhere(client: TestClient, path: str) -> None:
    assert client.get(path, params={"bbox": "-1.9,51.4,-1.8,51.45"}).status_code == 200


def test_the_ingest_command_takes_the_same_boxes() -> None:
    import argparse

    from fieldclub.ingest.cli import parse_bbox

    assert parse_bbox("-1.9,51.4,-1.8,51.45") == (-1.9, 51.4, -1.8, 51.45)
    for bad in BAD_BOXES:
        with pytest.raises(argparse.ArgumentTypeError):
            parse_bbox(bad)


@pytest.fixture
def lists(db: Session, make_user: MakeUser, client_as: ClientAs) -> tuple[TestClient, list[str]]:
    """A finder's client, and every list that pages by cursor, with a finding to list under."""
    finder = make_user()
    finding = create(db, finder)
    add_record(db, add_source(db), "Bowl barrow", -1.85, 51.43)
    db.commit()
    paths = [
        f"{API}/findings",
        f"{API}/findings?format=geojson",
        f"{API}/findings/export",
        f"{API}/findings/{finding.public_id}/observations",
        f"{API}/findings/{finding.public_id}/comments",
        f"{API}/review/next",
        f"{API}/review/tasks?code=need_observers",
        f"{API}/records/search?q=barrow",
        f"{API}/records/search",
    ]
    return client_as(finder), paths


BAD_CURSORS = [
    "!!!",
    "x" * 600,
    encode_cursor([]),
    encode_cursor(["a"]),
    encode_cursor([True]),
    encode_cursor([-1]),
    encode_cursor([2**70]),
    encode_cursor([1.5]),
    encode_cursor([None, None]),
    encode_cursor([True, True]),
    encode_cursor(["2026-11-10T00:00:00+00:00", 2**70]),
    encode_cursor([{"a": 1}, 1]),
]


@pytest.mark.parametrize("cursor", BAD_CURSORS)
def test_a_bad_cursor_is_invalid_cursor_on_every_list(
    lists: tuple[TestClient, list[str]], cursor: str
) -> None:
    client, paths = lists
    for path in paths:
        response = client.get(with_params(path, cursor=cursor))
        assert response.status_code == 400, f"{path}: {response.text}"
        assert error_code(response) == "invalid_cursor", path


@pytest.mark.parametrize(
    "path", [f"{API}/review/next", f"{API}/review/tasks?code=need_observers", f"{API}/records/search"]
)
def test_no_offset_goes_past_the_shared_limit(lists: tuple[TestClient, list[str]], path: str) -> None:
    client, _ = lists
    assert client.get(with_params(path, cursor=encode_cursor([MAX_OFFSET]))).status_code == 200
    beyond = client.get(with_params(path, cursor=encode_cursor([MAX_OFFSET + 1])))
    assert beyond.status_code == 400
    assert error_code(beyond) == "invalid_cursor"


@pytest.mark.parametrize(
    ("path", "limit"),
    [
        (f"{API}/findings", 201),
        (f"{API}/findings?format=geojson", 1001),
        (f"{API}/findings/export", 5001),
        (f"{API}/records/search", 201),
        (f"{API}/records/nearby?lon=-1.85&lat=51.43", 201),
        (f"{API}/review/next", 51),
        (f"{API}/review/tasks", 201),
        (f"{API}/geo/search?q=avebury", 21),
    ],
)
def test_a_limit_above_the_maximum_is_a_validation_error(client: TestClient, path: str, limit: int) -> None:
    response = client.get(with_params(path, limit=limit))
    assert response.status_code == 422, response.text
    assert error_code(response) == "validation_error"
    assert client.get(with_params(path, limit=limit - 1)).status_code == 200


@pytest.mark.parametrize("path", [f"{API}/records/search", f"{API}/records/nearby?lon=-1.85&lat=51.43"])
def test_filters_with_several_values_are_repeated_parameters(
    db: Session, client: TestClient, path: str
) -> None:
    designations = add_source(db)
    finds = add_source(db, "test-finds", name="Test finds", category="find")
    add_record(db, designations, "Bowl barrow", -1.85, 51.43)
    add_record(db, finds, "Roman coin", -1.8501, 51.4301)
    db.commit()

    def keys(**params: object) -> set[str]:
        response = client.get(with_params(path, **params))
        assert response.status_code == 200, response.text
        return {item["source_key"] for item in response.json()["items"]}

    assert keys(category=["designation", "find"]) == {"test-designations", "test-finds"}
    assert keys(category="find") == {"test-finds"}
    assert keys(source=["test-designations"]) == {"test-designations"}
    assert keys(source=["test-designations", "test-finds"]) == {"test-designations", "test-finds"}
    for refused in ({"category": "treasure"}, {"category": "designation,find"}):
        response = client.get(with_params(path, **refused))
        assert response.status_code == 422
        assert error_code(response) == "validation_error"
