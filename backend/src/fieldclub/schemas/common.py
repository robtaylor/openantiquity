"""Shapes shared across the API: pages, public users and GeoJSON."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Any, Literal
from urllib.parse import urlsplit

from geoalchemy2 import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from shapely.errors import ShapelyError
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from fieldclub.errors import InvalidBboxError, ValidationFailedError
from fieldclub.errors import InvalidCursorError as InvalidCursorError
from fieldclub.models.common import to_db_geometry as to_db_geometry
from fieldclub.schemas import text
from fieldclub.schemas.shapes import GEOMETRY_MAX_PARTS as GEOMETRY_MAX_PARTS
from fieldclub.schemas.shapes import GEOMETRY_MAX_POINTS as GEOMETRY_MAX_POINTS
from fieldclub.schemas.shapes import MALFORMED, check_shape
from fieldclub.schemas.shapes import GeometryTooComplexError as GeometryTooComplexError

if TYPE_CHECKING:
    from fieldclub.models import User

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_CURSOR_CHARS = 512
# The furthest any list paged by offset goes. Nobody reads 2,000 results, and
# an unbounded offset makes the database walk past every row before it.
MAX_OFFSET = 2000
# The largest id or offset a cursor may hold, and the largest id a path or body
# may name: PostgreSQL's BIGINT. Above it PostgreSQL raises rather than finds nothing.
MAX_ID = 2**63 - 1
# The longest web address kept anywhere.
WEB_URL_MAX = 2000


def web_url(value: str | None) -> str | None:
    """`value` if it is an absolute http or https address with a host, or None.

    For an address taken from somewhere other than a person's form, such as a
    publisher's record, which goes into a link someone may follow. Anything
    with another scheme (`javascript:`, `data:`), spaces or control
    characters, credentials or no host is dropped, as is one over `WEB_URL_MAX`.
    """
    if not value or len(value) > WEB_URL_MAX or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        return None
    return value


# A source's stored record count. A source that has never been ingested has none, which reads as 0.
RecordCount = Annotated[int, BeforeValidator(lambda value: value or 0)]


class ApiModel(BaseModel):
    """Base for response models. Reads straight from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class RequestModel(BaseModel):
    """Base for request bodies. An unknown field is an error, not something to ignore.

    Every string in the body, at any depth, is checked for characters the
    database can't store, and free-form JSON for runaway nesting. Either
    would otherwise surface as a 500. See `fieldclub.schemas.text`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _refuse_unstorable_text(cls, data: Any) -> Any:
        problem = text.find_problem(data)
        if problem is not None:
            raise ValueError(problem)
        return data


# --------------------------------------------------------------------------
# Paging
# --------------------------------------------------------------------------


class PageParams(BaseModel):
    """Query parameters every list takes. Use as `Annotated[PageParams, Query()]`.

    The cursor's length is checked by `decode_cursor`, so that a cursor that is
    wrong in any way, too long included, is the same 400 `invalid_cursor`.
    """

    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = None


class Page[T](BaseModel):
    """The envelope every list comes in.

    `next_cursor` is opaque. Send it back as `cursor` for the next page. It is
    null on the last page.
    """

    items: list[T]
    next_cursor: str | None = None


def encode_cursor(values: Sequence[Any]) -> str:
    """Pack the sort key of the last row into an opaque cursor."""
    raw = json.dumps(list(values), separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, length: int | None = None) -> list[Any]:
    """Unpack a cursor made by `encode_cursor`. Anything else raises `InvalidCursorError`."""
    if len(cursor) > MAX_CURSOR_CHARS:
        raise InvalidCursorError()
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise InvalidCursorError() from None
    if not isinstance(values, list) or (length is not None and len(values) != length):
        raise InvalidCursorError()
    # Cursor values go straight into queries, and the database refuses NUL.
    if text.find_problem(values) is not None:
        raise InvalidCursorError()
    return values


def cursor_int(value: Any) -> int:
    """A value from a cursor that must be a whole number a BIGINT column can hold, not negative."""
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_ID:
        raise InvalidCursorError()
    return value


def int_from_cursor(cursor: str) -> int:
    """The one non-negative whole number a cursor holds: a last id, or an offset."""
    (value,) = decode_cursor(cursor, 1)
    return cursor_int(value)


def offset_from_cursor(cursor: str | None) -> int:
    """The offset a cursor made by `offset_page` holds, 0 without one, and never past `MAX_OFFSET`."""
    if cursor is None:
        return 0
    offset = int_from_cursor(cursor)
    if offset > MAX_OFFSET:
        raise InvalidCursorError()
    return offset


def paginate[T](rows: Sequence[T], limit: int, key: Any) -> tuple[list[T], str | None]:
    """Turn `limit + 1` fetched rows into a page and the cursor for the next.

    Fetch one row more than the page size. If it arrives there is another
    page, and `key(last_row)` gives the values to resume from.
    """
    assert limit >= 1, "limit must be at least 1"
    assert len(rows) <= limit + 1, "fetch at most limit + 1 rows"
    items = list(rows[:limit])
    next_cursor = encode_cursor(key(items[-1])) if len(rows) > limit and items else None
    return items, next_cursor


def offset_page[T](
    rows: Sequence[T], offset: int, limit: int, *, max_offset: int | None = None
) -> tuple[list[T], str | None]:
    """Turn `limit + 1` rows fetched from `offset` into a page and the cursor for the next.

    For lists whose order changes as people use them, where a keyset cursor
    would skip rows. Read the offset back with `offset_from_cursor`. No next
    cursor is given past `max_offset`, and an offset past it is refused as
    `InvalidCursorError`. Every list shares `MAX_OFFSET` as its furthest
    offset, so None or a larger `max_offset` means `MAX_OFFSET`.
    """
    assert limit >= 1, "limit must be at least 1"
    assert len(rows) <= limit + 1, "fetch at most limit + 1 rows"
    max_offset = MAX_OFFSET if max_offset is None else min(max_offset, MAX_OFFSET)
    assert max_offset >= 0, "the furthest offset can't be negative"
    if not 0 <= offset <= max_offset:
        raise InvalidCursorError()
    following = offset + limit
    more = len(rows) > limit and following <= max_offset
    return list(rows[:limit]), encode_cursor([following]) if more else None


# --------------------------------------------------------------------------
# Boxes
# --------------------------------------------------------------------------

# West, south, east, north in degrees.
BBox = tuple[float, float, float, float]


def split_bbox(text: str) -> BBox:
    """`west,south,east,north` as four numbers. Raises `ValueError` when it isn't four numbers."""
    west, south, east, north = (float(part) for part in text.split(","))
    return west, south, east, north


def check_bbox(bbox: BBox) -> BBox:
    """The box as four floats, or `InvalidBboxError` when it isn't a box with an area (`is_bbox`).

    The one rule for a box, on every route and in every command that takes one.
    """
    assert len(bbox) == 4, "a bbox has four numbers: west, south, east, north"
    west, south, east, north = (float(value) for value in bbox)
    if not is_bbox((west, south, east, north)):
        raise InvalidBboxError()
    return west, south, east, north


def parse_bbox(text: str | None) -> BBox | None:
    """A `bbox` query parameter, `west,south,east,north`, checked by `check_bbox`. None when absent."""
    if text is None:
        return None
    try:
        bbox = split_bbox(text)
    except ValueError:
        raise InvalidBboxError() from None
    return check_bbox(bbox)


def is_bbox(bbox: BBox, *, allow_empty: bool = False) -> bool:
    """Whether a box lies in degrees and runs west to east and south to north.

    NaN and the infinities fail every comparison, so they are refused too.
    With `allow_empty`, a box may have no width or no height.
    """
    west, south, east, north = bbox
    if allow_empty:
        return -180 <= west <= east <= 180 and -90 <= south <= north <= 90
    return -180 <= west < east <= 180 and -90 <= south < north <= 90


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


class PublicUser(ApiModel):
    """What anyone may see of a user, wherever a person is credited.

    Built from a `User`, an account in the 16 to 17 band, or one that hasn't
    chosen a band yet, shows its handle as its name (Decision 0009).
    `User.shows_handle_only` decides. Nobody has a picture: a sign-in
    provider's would be fetched from the provider by every visitor's browser. The model refuses a dict, a row
    or any other input, because those carry no age band and the rule couldn't
    be applied.
    """

    handle: str
    display_name: str
    role: str

    @model_validator(mode="before")
    @classmethod
    def _handle_only_for_16_and_17(cls, data: Any) -> Any:
        from fieldclub.models import User

        if not isinstance(data, User):
            if not isinstance(data, cls):
                raise ValueError(f"{cls.__name__} is built from a User with {cls.__name__}.from_user")
            return data
        handle_only = data.shows_handle_only
        return {
            "handle": data.handle,
            "display_name": data.handle if handle_only else data.display_name,
            "role": data.role,
        }

    @classmethod
    def from_user(cls, user: User) -> PublicUser:
        return cls.model_validate(user)


# --------------------------------------------------------------------------
# GeoJSON
# --------------------------------------------------------------------------


class GeoJSONGeometry(BaseModel):
    """Any GeoJSON geometry in WGS84. Coordinates are longitude then latitude."""

    model_config = ConfigDict(extra="allow")

    type: Literal[
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    ]
    coordinates: list[Any] | None = None


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str | int | None = None
    geometry: GeoJSONGeometry | None
    properties: dict[str, Any] = Field(default_factory=dict)


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature] = Field(default_factory=list)


def to_geojson(
    geometry: WKBElement | WKTElement | BaseGeometry | None, *, decimals: int = 6
) -> dict[str, Any] | None:
    """A GeoJSON geometry dict from a database value or shapely geometry.

    Six decimal places of a degree is about 10 cm, which is plenty and keeps
    responses small.
    """
    if geometry is None:
        return None
    shapely_geometry = geometry if isinstance(geometry, BaseGeometry) else to_shape(geometry)
    return _round_coordinates(dict(mapping(shapely_geometry)), decimals)


def geojson_geometry(
    geometry: WKBElement | WKTElement | BaseGeometry | None, *, decimals: int = 6
) -> GeoJSONGeometry | None:
    """`to_geojson` as the response model."""
    data = to_geojson(geometry, decimals=decimals)
    return None if data is None else GeoJSONGeometry.model_validate(data)


def geojson_point(lon: float, lat: float) -> GeoJSONGeometry:
    """A GeoJSON point, rounded as `to_geojson` rounds."""
    return GeoJSONGeometry(type="Point", coordinates=[round(lon, 6), round(lat, 6)])


def _round_coordinates(value: Any, decimals: int) -> Any:
    if isinstance(value, float):
        return round(value, decimals)
    if isinstance(value, list | tuple):
        return [_round_coordinates(item, decimals) for item in value]
    if isinstance(value, dict):
        return {key: _round_coordinates(item, decimals) for key, item in value.items()}
    return value


def from_geojson(
    geometry: GeoJSONGeometry | dict[str, Any],
    *,
    allowed: Sequence[str] | None = None,
    max_points: int = GEOMETRY_MAX_POINTS,
) -> BaseGeometry:
    """A valid shapely geometry from GeoJSON sent by a client.

    Raises `ValidationFailedError` if it is malformed, empty, self-intersecting,
    outside the range of longitude and latitude, or not one of `allowed` types,
    and `GeometryTooComplexError` if it has more than `max_points` positions
    or `GEOMETRY_MAX_PARTS` parts.
    """
    data = geometry.model_dump() if isinstance(geometry, GeoJSONGeometry) else geometry
    if allowed is not None and data.get("type") not in allowed:
        raise ValidationFailedError(f"Expected a geometry of type {' or '.join(allowed)}.")
    assert max_points <= GEOMETRY_MAX_POINTS, "no shape from a client may be larger than the general limit"
    check_shape(data, max_points=max_points)
    try:
        geom = shape(data)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise ValidationFailedError(MALFORMED) from None
    if geom.is_empty:
        raise ValidationFailedError("The geometry is empty.")
    if not geom.is_valid:
        raise ValidationFailedError("The geometry crosses itself or is otherwise invalid.")
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise ValidationFailedError("Coordinates must be longitude then latitude, in degrees.")
    return geom
