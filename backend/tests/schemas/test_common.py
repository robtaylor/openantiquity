"""Paging, the public user shape and the GeoJSON helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from geoalchemy2 import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from pydantic import ValidationError
from shapely.geometry import LineString, Point, Polygon, box
from sqlalchemy.orm import Session

from fieldclub.errors import ValidationFailedError
from fieldclub.models import Finding, User
from fieldclub.schemas.common import (
    DEFAULT_LIMIT,
    MAX_CURSOR_CHARS,
    MAX_LIMIT,
    MAX_OFFSET,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONGeometry,
    InvalidCursorError,
    Page,
    PageParams,
    PublicUser,
    RequestModel,
    decode_cursor,
    encode_cursor,
    from_geojson,
    offset_page,
    paginate,
    to_db_geometry,
    to_geojson,
)

# --------------------------------------------------------------------------
# Paging
# --------------------------------------------------------------------------


def test_page_envelope() -> None:
    page = Page[int](items=[1, 2, 3], next_cursor="abc")
    assert page.model_dump() == {"items": [1, 2, 3], "next_cursor": "abc"}
    assert Page[int](items=[]).model_dump() == {"items": [], "next_cursor": None}
    schema = Page[PublicUser].model_json_schema()
    assert set(schema["properties"]) == {"items", "next_cursor"}
    with pytest.raises(ValidationError):
        Page[int](items=["not a number"])  # pyright: ignore[reportArgumentType]


def test_page_params_defaults_and_limits() -> None:
    assert PageParams().model_dump() == {"limit": DEFAULT_LIMIT, "cursor": None}
    assert PageParams(limit=MAX_LIMIT).limit == MAX_LIMIT
    for limit in (0, -1, MAX_LIMIT + 1):
        with pytest.raises(ValidationError):
            PageParams(limit=limit)
    # A long cursor is refused where every other bad cursor is, with the same code.
    with pytest.raises(InvalidCursorError):
        decode_cursor("x" * 600)


def test_a_well_formed_cursor_that_is_too_long_is_refused_before_it_is_decoded() -> None:
    """The length check is all that bounds a cursor, now that the query parameters have no maximum."""
    longest = encode_cursor(["a" * 300])
    assert len(longest) <= MAX_CURSOR_CHARS
    assert decode_cursor(longest) == ["a" * 300]
    too_long = encode_cursor(["a" * 400])
    assert len(too_long) > MAX_CURSOR_CHARS
    with pytest.raises(InvalidCursorError):
        decode_cursor(too_long)


def test_offset_pages_never_go_past_the_shared_limit_whatever_a_caller_asks() -> None:
    """Callers older than `MAX_OFFSET` may pass None or a larger `max_offset`: both mean the shared limit."""
    rows = list(range(11))
    for max_offset in (None, MAX_OFFSET, MAX_OFFSET * 10):
        page, cursor = offset_page(rows, 0, 10, max_offset=max_offset)
        assert (page, cursor) == (rows[:10], encode_cursor([10]))
        assert offset_page(rows, MAX_OFFSET - 10, 10, max_offset=max_offset)[1] == encode_cursor([MAX_OFFSET])
        assert offset_page(rows, MAX_OFFSET, 10, max_offset=max_offset)[1] is None
        with pytest.raises(InvalidCursorError):
            offset_page(rows, MAX_OFFSET + 1, 10, max_offset=max_offset)
    # A smaller limit of a list's own still holds.
    assert offset_page(rows, 0, 10, max_offset=5)[1] is None


def test_cursor_round_trip() -> None:
    when = datetime(2026, 11, 10, 12, 30, tzinfo=UTC)
    cursor = encode_cursor([when.isoformat(), 42])
    assert cursor.isascii()
    assert "=" not in cursor
    assert decode_cursor(cursor) == [when.isoformat(), 42]
    assert decode_cursor(cursor, length=2) == [when.isoformat(), 42]
    assert decode_cursor(encode_cursor([when])) == [str(when)]
    for values in ([], [1], [1.5, "a", None, True], ["ünïcode"]):
        assert decode_cursor(encode_cursor(values)) == values


@pytest.mark.parametrize("cursor", ["", "!!!", "not base64 at all", "bm90IGpzb24", "eyJhIjoxfQ", "/w"])
def test_bad_cursors_are_a_400(cursor: str) -> None:
    with pytest.raises(InvalidCursorError) as caught:
        decode_cursor(cursor, length=2)
    assert caught.value.status_code == 400
    assert caught.value.code == "invalid_cursor"


def test_cursor_of_the_wrong_length_is_refused() -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(encode_cursor([1, 2, 3]), length=2)


@pytest.mark.parametrize("values", [["nul\x00byte", 1], [["nested", "bell\x07"]], ["\ud800"]])
def test_a_cursor_cannot_smuggle_text_the_database_refuses(values: list) -> None:
    # Cursor values go into queries as they are, and NUL there is a database error.
    with pytest.raises(InvalidCursorError):
        decode_cursor(encode_cursor(values))


def test_paginate() -> None:
    rows = list(range(1, 12))
    items, cursor = paginate(rows[:6], 5, key=lambda row: [row])
    assert items == [1, 2, 3, 4, 5]
    assert cursor is not None
    assert decode_cursor(cursor) == [5]

    items, cursor = paginate(rows[5:10], 5, key=lambda row: [row])
    assert (items, cursor) == ([6, 7, 8, 9, 10], None)
    assert paginate([], 5, key=lambda row: [row]) == ([], None)
    with pytest.raises(AssertionError):
        paginate(rows, 5, key=lambda row: [row])


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


def test_public_user_shows_only_public_fields(make_user: Callable[..., User]) -> None:
    user = make_user("trusted", handle="QuietBarrow42", email="private@example.org", bio="Hello")
    public = PublicUser.model_validate(user)
    assert public.model_dump() == {
        "handle": "QuietBarrow42",
        "display_name": "QuietBarrow42",
        "role": "trusted",
    }
    # Nobody has a picture: a provider's would be fetched from the provider by every visitor.
    pictured = make_user(avatar_url="https://example.org/a.png")
    assert "avatar_url" not in PublicUser.model_validate(pictured).model_dump()
    assert "is_guest" not in PublicUser.model_fields


@pytest.mark.parametrize("band", ["16_17", None])
def test_a_16_or_17_year_old_is_shown_by_handle_only(
    make_user: Callable[..., User], band: str | None
) -> None:
    # Decision 0009. An account that hasn't chosen a band yet is treated the
    # same way until it says it is 18 or over.
    user = make_user(
        handle="YoungDigger",
        display_name="Alex Provider",
        avatar_url="https://provider.example/alex.png",
        age_band=band,
    )
    expected = {"handle": "YoungDigger", "display_name": "YoungDigger", "role": "member"}
    assert PublicUser.model_validate(user).model_dump() == expected
    assert PublicUser.from_user(user).model_dump() == expected
    assert user.shows_handle_only is True


def test_public_user_refuses_input_that_is_not_a_user(make_user: Callable[..., User]) -> None:
    # A dict carries no age band, so the handle-only rule couldn't be applied.
    raw = {
        "handle": "YoungDigger",
        "display_name": "Alex Provider",
        "role": "member",
    }
    with pytest.raises(ValidationError, match=r"PublicUser\.from_user"):
        PublicUser.model_validate(raw)
    # A model already built from a User passes through again, as when a response is validated.
    built = PublicUser.from_user(
        make_user(handle="YoungDigger", display_name="Alex Provider", age_band="16_17")
    )
    assert PublicUser.model_validate(built).display_name == "YoungDigger"


def test_an_adult_is_shown_with_their_name_and_no_picture(make_user: Callable[..., User]) -> None:
    user = make_user(
        handle="RidgewayRob", display_name="Rob", avatar_url="https://example.org/rob.png", age_band="18_plus"
    )
    assert PublicUser.from_user(user).model_dump() == {
        "handle": "RidgewayRob",
        "display_name": "Rob",
        "role": "member",
    }
    assert user.shows_handle_only is False


def test_request_models_refuse_unknown_fields_and_trim_strings() -> None:
    class Body(RequestModel):
        name: str

    assert Body(name="  Avebury  ").name == "Avebury"
    with pytest.raises(ValidationError):
        Body(name="x", surprise=1)  # pyright: ignore[reportCallIssue]


def test_request_models_refuse_text_the_database_cannot_store() -> None:
    class Inner(RequestModel):
        note: str

    class Body(RequestModel):
        name: str
        data: dict | None = None
        inner: Inner | None = None
        tags: list[str] | None = None

    fine = Body(name="Two\nlines", data={"a": ["b", {"c": "d\te"}]}, inner=Inner(note="ok"), tags=["x"])
    assert fine.name == "Two\nlines"
    for body in (
        {"name": "nul\x00byte"},
        {"name": "ok", "data": {"deep": [{"er": "bell\x07"}]}},
        {"name": "ok", "data": {"nul\x00key": 1}},
        {"name": "ok", "inner": {"note": "escape\x1b"}},
        {"name": "ok", "tags": ["fine", "\ud800"]},
    ):
        with pytest.raises(ValidationError, match="control character"):
            Body.model_validate(body)


def test_request_models_refuse_runaway_nesting() -> None:
    class Body(RequestModel):
        data: dict

    value: dict = {"leaf": 1}
    for _ in range(300):
        value = {"a": value}
    with pytest.raises(ValidationError, match="nested more than"):
        Body.model_validate({"data": value})


# --------------------------------------------------------------------------
# GeoJSON
# --------------------------------------------------------------------------


def test_to_geojson_from_shapely_and_database_values(
    db: Session, make_finding: Callable[..., Finding]
) -> None:
    assert to_geojson(None) is None
    assert to_geojson(Point(-1.85421234567, 51.42861234567)) == {
        "type": "Point",
        "coordinates": [-1.854212, 51.428612],
    }
    assert to_geojson(WKTElement("POINT(-1.5 51.5)", srid=4326)) == {
        "type": "Point",
        "coordinates": [-1.5, 51.5],
    }

    finding = make_finding(lon=-1.8542, lat=51.4286, outline=to_db_geometry(box(-1.86, 51.42, -1.85, 51.43)))
    db.expire_all()
    assert isinstance(finding.location, WKBElement)
    assert to_geojson(finding.location) == {"type": "Point", "coordinates": [-1.8542, 51.4286]}
    outline = to_geojson(finding.outline)
    assert outline is not None
    assert outline["type"] == "Polygon"
    assert len(outline["coordinates"][0]) == 5
    assert outline["coordinates"][0][0] == outline["coordinates"][0][-1]


def test_to_geojson_precision_can_be_chosen() -> None:
    assert to_geojson(Point(-1.85421234567, 51.42861234567), decimals=3) == {
        "type": "Point",
        "coordinates": [-1.854, 51.429],
    }


def test_from_geojson_accepts_valid_geometry() -> None:
    point = from_geojson({"type": "Point", "coordinates": [-1.8542, 51.4286]})
    assert point.equals(Point(-1.8542, 51.4286))
    line = from_geojson(GeoJSONGeometry(type="LineString", coordinates=[[-1.86, 51.42], [-1.85, 51.43]]))
    assert line.equals(LineString([(-1.86, 51.42), (-1.85, 51.43)]))
    square = {
        "type": "Polygon",
        "coordinates": [[[-1.86, 51.42], [-1.85, 51.42], [-1.85, 51.43], [-1.86, 51.42]]],
    }
    assert isinstance(from_geojson(square, allowed=["Polygon", "MultiPolygon"]), Polygon)


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"type": "Point"}, "valid GeoJSON"),
        ({"type": "Point", "coordinates": "here"}, "valid GeoJSON"),
        ({"type": "Point", "coordinates": []}, "empty"),
        ({"type": "Blob", "coordinates": [1, 2]}, "valid GeoJSON"),
        ({"coordinates": [1, 2]}, "valid GeoJSON"),
        ({"type": "Point", "coordinates": [51.4286, -181.0]}, "longitude then latitude"),
        ({"type": "Point", "coordinates": [-1.85, 95.0]}, "longitude then latitude"),
        ({"type": "Point", "coordinates": [410250, 169960]}, "longitude then latitude"),
        (
            {
                "type": "Polygon",
                "coordinates": [
                    [[-1.86, 51.42], [-1.85, 51.43], [-1.85, 51.42], [-1.86, 51.43], [-1.86, 51.42]]
                ],
            },
            "crosses itself",
        ),
        (
            {"type": "LineString", "coordinates": [[-1.86, 51.42], [-1.85, 51.43]]},
            "Expected a geometry of type Point",
        ),
    ],
)
def test_from_geojson_refuses_bad_geometry(geometry: dict, message: str) -> None:
    allowed = ["Point"] if "Expected" in message else None
    with pytest.raises(ValidationFailedError, match=message) as caught:
        from_geojson(geometry, allowed=allowed)
    assert caught.value.status_code == 422


_RING = [[-1.8, 51.45], [-1.799, 51.45], [-1.799, 51.451], [-1.8, 51.45]]


@pytest.mark.parametrize(
    "geometry",
    [
        # A polygon with an empty hole made GEOS crash the whole process in `contains`.
        {"type": "Polygon", "coordinates": [_RING, []]},
        {"type": "Polygon", "coordinates": [[]]},
        {"type": "Polygon", "coordinates": []},
        {"type": "MultiPolygon", "coordinates": [[_RING], []]},
        {"type": "MultiPolygon", "coordinates": [[_RING, []]]},
        {"type": "MultiPolygon", "coordinates": []},
        # Rings need four positions and must close; lines need two.
        {"type": "Polygon", "coordinates": [_RING[:3]]},
        {"type": "Polygon", "coordinates": [[*_RING[:3], [-1.8, 51.4505]]]},
        {"type": "LineString", "coordinates": [[-1.8, 51.45]]},
        {"type": "LineString", "coordinates": []},
        {"type": "MultiLineString", "coordinates": [[[-1.8, 51.45], [-1.79, 51.45]], []]},
        {"type": "MultiPoint", "coordinates": [[-1.8, 51.45], []]},
        # Positions are two or three finite numbers.
        {"type": "Point", "coordinates": [-1.8]},
        {"type": "Point", "coordinates": [-1.8, 51.45, 0, 0]},
        {"type": "Point", "coordinates": [-1.8, float("nan")]},
        {"type": "Point", "coordinates": [True, 51.45]},
        {"type": "LineString", "coordinates": [[-1.8, 51.45], [[-1.79, 51.45]]]},
        # A ring whose ends aren't positions at all.
        {"type": "Polygon", "coordinates": [[1, 2, 3, 1]]},
        {"type": "Polygon", "coordinates": [[None, [-1.799, 51.45], [-1.799, 51.451], None]]},
        {"type": "MultiPolygon", "coordinates": [[["ab", [-1.799, 51.45], [-1.799, 51.451], "ab"]]]},
        # A whole number too large to be a coordinate, which Python can't turn into a float.
        {"type": "Point", "coordinates": [10**400, 51.45]},
        {"type": "LineString", "coordinates": [[-1.8, 51.45], [-1.79, -(10**400)]]},
        # A collection of nothing, or holding a broken member or another collection.
        {"type": "GeometryCollection", "geometries": []},
        {"type": "GeometryCollection", "geometries": [{"type": "Polygon", "coordinates": [_RING, []]}]},
        {"type": "GeometryCollection", "geometries": [{"type": "GeometryCollection", "geometries": []}]},
        # A member whose type isn't a word at all.
        {"type": "GeometryCollection", "geometries": [{"type": ["Point"], "coordinates": [-1.8, 51.45]}]},
        {"type": "GeometryCollection", "geometries": [{"type": {}, "coordinates": [-1.8, 51.45]}]},
    ],
)
def test_from_geojson_refuses_shapes_with_empty_or_short_parts(geometry: dict) -> None:
    """Such a shape reaches GEOS, which can crash the API process on it: refuse it first."""
    with pytest.raises(ValidationFailedError) as caught:
        from_geojson(geometry)
    assert caught.value.status_code == 422
    assert caught.value.code == "validation_error"


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Polygon", "coordinates": [_RING]},
        {"type": "Polygon", "coordinates": [[[x, y, 120.5] for x, y in _RING]]},
        {"type": "MultiPolygon", "coordinates": [[_RING]]},
        {"type": "LineString", "coordinates": [[-1.8, 51.45], [-1.79, 51.45]]},
        {"type": "MultiPoint", "coordinates": [[-1.8, 51.45]]},
        {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [-1.8, 51.45]}]},
    ],
)
def test_every_shape_from_geojson_can_be_tested_against_the_british_isles(geometry: dict) -> None:
    from fieldclub.services.geo import check_in_british_isles

    check_in_british_isles(from_geojson(geometry))


def test_to_db_geometry_carries_the_srid() -> None:
    element = to_db_geometry(Point(-1.8542, 51.4286))
    assert isinstance(element, WKBElement)
    assert element.srid == 4326
    assert to_shape(element).equals(Point(-1.8542, 51.4286))


def test_feature_collection_models_validate_as_geojson() -> None:
    marked = GeoJSONFeature(
        id="7K3QXM",
        geometry=GeoJSONGeometry.model_validate(to_geojson(Point(-1.8542, 51.4286))),
        properties={"tier": "seen"},
    )
    bare = GeoJSONFeature(geometry=None, properties={"obscured": True})
    assert marked.model_dump(exclude_none=True) == {
        "type": "Feature",
        "id": "7K3QXM",
        "geometry": {"type": "Point", "coordinates": [-1.8542, 51.4286]},
        "properties": {"tier": "seen"},
    }
    collection = GeoJSONFeatureCollection(features=[marked, bare])
    parsed = GeoJSONFeatureCollection.model_validate(collection.model_dump())
    assert [item.id for item in parsed.features] == ["7K3QXM", None]
    assert GeoJSONFeatureCollection().model_dump() == {"type": "FeatureCollection", "features": []}


def test_geojson_geometry_model_rejects_unknown_types() -> None:
    with pytest.raises(ValidationError):
        GeoJSONGeometry(type="Circle", coordinates=[0, 0])  # pyright: ignore[reportArgumentType]
