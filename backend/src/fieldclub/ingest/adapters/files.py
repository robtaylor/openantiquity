"""Readers for files on disk: anything OGR reads, CSV and newline-delimited JSON.

    for feature in read_vector(path):                     # GeoPackage, shapefile, GeoJSON...
    for feature in read_vector("monuments.zip", layer="Mon_point"):   # a zipped shapefile
    for feature in read_csv(path, x="Easting", y="Northing", crs="EPSG:27700", encoding="cp1252"):
    for feature in read_csv("names.zip", member="Data/SU16.csv", fieldnames=HEADINGS):
    for feature in read_ndjson(path):

`read_vector` goes through pyogrio and reads in chunks of feature ids, so a
file of half a million polygons never sits in memory at once. Geometry comes
back in WGS84 whatever the file's own CRS. CSV values stay as text, because
guessing types is how leading zeros in identifiers get lost.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import warnings
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

import shapely
from shapely.errors import ShapelyError
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters import ogr
from fieldclub.ingest.adapters.common import (
    Feature,
    UpstreamFormatError,
    bbox_from_wgs84,
    plain,
    plain_tree,
    to_wgs84,
)
from fieldclub.ingest.adapters.ogr import DataSourceError
from fieldclub.ingest.base import BBox

logger = logging.getLogger(__name__)

DEFAULT_CHUNK = 5000


def _vsi(path: Path | str) -> str:
    """The path as GDAL wants it. A `.zip` is opened through `/vsizip/`."""
    text = str(path)
    return f"/vsizip/{text}" if text.lower().endswith(".zip") and not text.startswith("/vsi") else text


def vector_info(path: Path | str, layer: str | int | None = None) -> dict[str, Any]:
    """The layer's CRS, fields, geometry type and feature count, as pyogrio reports them."""
    try:
        with quiet_ogr():
            return dict(ogr.read_info(_vsi(path), layer=layer))
    except DataSourceError as exc:
        raise UpstreamFormatError(f"{Path(path).name} could not be opened: {exc}") from None


def _bbox_in(crs: str | None, bbox: BBox) -> tuple[float, float, float, float]:
    """A WGS84 box as a box in `crs`, for pyogrio's prefilter."""
    if crs is None:
        return bbox
    return bbox_from_wgs84(bbox, crs)


def read_vector(
    path: Path | str,
    *,
    layer: str | int | None = None,
    columns: Sequence[str] | None = None,
    where: str | None = None,
    bbox: BBox | None = None,
    crs: str | None = None,
    chunk: int = DEFAULT_CHUNK,
    info: dict[str, Any] | None = None,
) -> Iterator[Feature]:
    """Every feature of one layer, in WGS84.

    `crs` overrides the file's own, for a file that doesn't state one. `bbox`
    (WGS84) is a prefilter by envelope. The runner does the exact test.
    `info` is what `vector_info` gave for this layer, for a caller that has
    already read it.
    """
    assert chunk >= 1, "chunk must be at least 1"
    source = _vsi(path)
    if info is None:
        info = vector_info(path, layer)
    crs = crs or info.get("crs")
    if crs is None:
        raise UpstreamFormatError(f"{Path(path).name} states no CRS. Pass crs= to say what it is.")
    with quiet_ogr():
        _, fids, _, _ = ogr.read(
            source,
            layer=layer,
            read_geometry=False,
            columns=[],
            where=where,
            bbox=_bbox_in(crs, bbox) if bbox is not None else None,
            return_fids=True,
        )
    assert fids is not None, "return_fids=True always returns fids"
    logger.info("%s: %d features", Path(path).name, len(fids))
    for start in range(0, len(fids), chunk):
        with quiet_ogr():
            meta, chunk_fids, geometries, fields = ogr.read(
                source, layer=layer, columns=columns, fids=fids[start : start + chunk], return_fids=True
            )
        yield from ogr_features(meta, chunk_fids, geometries, fields, crs)


def ogr_features(
    meta: dict[str, Any], fids: Any, geometries: Any, fields: Sequence[Any], crs: str
) -> Iterator[Feature]:
    """Features from what `pyogrio.raw.read(..., return_fids=True)` returns, reprojected from `crs`."""
    assert fids is not None, "read with return_fids=True"
    names = [str(name) for name in meta["fields"]]
    for index, fid in enumerate(fids):
        properties = {name: plain(values[index]) for name, values in zip(names, fields, strict=True)}
        geometry = None
        if geometries is not None and geometries[index] is not None:
            geometry = shapely.from_wkb(geometries[index])
            geometry = None if geometry.is_empty else to_wgs84(geometry, crs)
        yield Feature(properties, geometry, plain(fid))


@contextmanager
def quiet_ogr() -> Iterator[None]:
    """Silence three warnings from reading OGR data that say nothing is wrong.

    Historic England's GeoPackages write some dates as `1925-03-10T00:00:00.0Z`.
    GDAL reads them correctly and says so with a RuntimeWarning. pyogrio 0.13
    converts date fields with a numpy idiom that numpy 2.5 deprecates. Either
    would fail the tests, where a warning is an error.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Non-conformant content", category=RuntimeWarning)
        warnings.filterwarnings(
            "ignore", message="The 'generic' unit for NumPy timedelta", category=DeprecationWarning
        )
        # Historic England's AIM export has measured (M) polygons, which pyogrio reads as plain ones.
        warnings.filterwarnings("ignore", message="Measured \\(M\\) geometry types", category=UserWarning)
        yield


def _number(text: str | None) -> float | None:
    if text is None or not text.strip():
        return None
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def read_csv(
    path: Path | str,
    *,
    x: str | None = None,
    y: str | None = None,
    crs: str = "EPSG:4326",
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    member: str | None = None,
    fieldnames: Sequence[str] | None = None,
) -> Iterator[Feature]:
    """Rows of a CSV file as features. `x` and `y` name the coordinate columns, if it has any.

    A row with blank or unreadable coordinates gets no geometry. Values stay
    as text, with empty cells as None. The default encoding drops a UTF-8
    byte-order mark. Lincolnshire's export, for one, is `cp1252`, and the
    GB1900 gazetteer is `utf-16`.

    `member` reads one file inside the zip at `path` without unpacking it.
    `fieldnames` gives the headings of a file that has none, such as each
    tile of OS Open Names, whose headings are in a file of their own.
    """
    assert (x is None) == (y is None), "give both x and y, or neither"
    name = member or Path(path).name
    with _open_text(path, member, encoding) as handle:
        reader = csv.DictReader(handle, fieldnames=fieldnames, delimiter=delimiter)
        try:
            yield from _csv_rows(name, reader, x, y, crs)
        except UnicodeDecodeError as exc:
            raise _not_encoded(name, encoding, exc) from None


@contextmanager
def _open_text(path: Path | str, member: str | None, encoding: str) -> Iterator[TextIO]:
    """A text handle on `path`, or on `member` inside the zip at `path`."""
    if member is None:
        with Path(path).open(encoding=encoding, newline="") as handle:
            yield handle
        return
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise UpstreamFormatError(f"{Path(path).name} is not a zip file.") from None
    with archive:
        try:
            raw = archive.open(member)
        except KeyError:
            raise UpstreamFormatError(f"{Path(path).name} has no {member}.") from None
        with io.TextIOWrapper(raw, encoding=encoding, newline="") as handle:
            yield handle


def _not_encoded(path: Path | str, encoding: str, exc: UnicodeDecodeError) -> UpstreamFormatError:
    # Text is decoded a block at a time, so there is no line number worth giving.
    return UpstreamFormatError(
        f"{Path(path).name} isn't {encoding}: {exc.reason}. Pass encoding= to say what it is."
    )


def _csv_rows(
    name: str, reader: csv.DictReader[str], x: str | None, y: str | None, crs: str
) -> Iterator[Feature]:
    if reader.fieldnames is None:
        return
    missing = [column for column in (x, y) if column is not None and column not in reader.fieldnames]
    if missing:
        raise UpstreamFormatError(f"{name} has no column {missing[0]!r}: {reader.fieldnames}")
    for number, row in enumerate(reader, start=2):
        if None in row:
            raise UpstreamFormatError(f"{name} line {number} has more cells than headings.")
        properties = {key: (value if value != "" else None) for key, value in row.items()}
        geometry: BaseGeometry | None = None
        if x is not None and y is not None:
            east, north = _number(row[x]), _number(row[y])
            if east is not None and north is not None:
                geometry = to_wgs84(Point(east, north), crs)
        yield Feature(properties, geometry)


def read_ndjson(
    path: Path | str,
    *,
    crs: str = "EPSG:4326",
    encoding: str = "utf-8",
) -> Iterator[Feature]:
    """Lines of newline-delimited JSON. A GeoJSON Feature gives its properties and geometry.

    Any other object is taken whole as properties, with no geometry. Blank
    lines are skipped. A line that isn't JSON stops the read with its number.
    """
    with Path(path).open(encoding=encoding) as handle:
        try:
            yield from _ndjson_lines(Path(path).name, handle, crs)
        except UnicodeDecodeError as exc:
            raise _not_encoded(path, encoding, exc) from None


def _ndjson_lines(name: str, handle: Iterable[str], crs: str) -> Iterator[Feature]:
    for number, line in enumerate(handle, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise UpstreamFormatError(f"{name} line {number} is not JSON: {exc}") from None
        if not isinstance(item, dict):
            raise UpstreamFormatError(f"{name} line {number} is not a JSON object.")
        if item.get("type") != "Feature":
            yield Feature(plain_tree(item), None)
            continue
        properties = item.get("properties") or {}
        if not isinstance(properties, dict):
            raise UpstreamFormatError(f"{name} line {number} has properties that aren't an object.")
        geometry = geojson_geometry(item.get("geometry"), crs, where=f"line {number}")
        yield Feature(plain_tree(properties), geometry, item.get("id"))


def geojson_geometry(value: Any, crs: str = "EPSG:4326", *, where: str = "a feature") -> BaseGeometry | None:
    """A GeoJSON geometry object as shapely in WGS84, or None when it is null or empty."""
    if value is None:
        return None
    try:
        geometry = shape(value)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, ShapelyError):
        raise UpstreamFormatError(f"The geometry of {where} isn't valid GeoJSON.") from None
    return None if geometry.is_empty else to_wgs84(geometry, crs)
