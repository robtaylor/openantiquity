"""Records as Mapbox vector tiles, built in PostGIS with ST_AsMVT.

Below `FEATURES_FROM_ZOOM` a tile holds counts: the tile is cut into a
`GRID` by `GRID` grid, and each cell with records gets one point per
category in layer `record_counts`, with `category`, `count` and `sources`
(the source keys counted, comma-separated). A record is counted where its
centroid falls, so it is counted once however many tiles its outline
touches. From `FEATURES_FROM_ZOOM` up, layer `records` holds the records
themselves, clipped to the tile, with `id`, `name`, `category`, `type`,
`source` and `reuse`. A source's licence and attribution come from
`GET /api/v1/sources` by the `source` key.

A tile at a feature zoom with more than `MAX_TILE_FEATURES` records gets
counts instead, so a tile in the middle of a town never runs to a megabyte.
The frontend draws whichever of the two layers a tile has.

Both queries filter on an indexed column first: `centroid` for counts and
`geom` for features, against the tile's envelope in EPSG:4326. A Web
Mercator tile is a longitude and latitude rectangle, so that test is exact.
A tile with nothing in it is an empty byte string, which is a valid tile
with no layers.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from fieldclub.errors import BadRequestError, NotFoundError
from fieldclub.vocab import RecordCategory

MAX_ZOOM = 22
FEATURES_FROM_ZOOM = 12
# 500,000 synthetic records put 15,358 in the densest zoom-12 tile, which came
# to 942 KB. 5,000 keeps a tile to about 300 KB.
MAX_TILE_FEATURES = 5000
GRID = 32
EXTENT = 4096
# How far features reach past the tile edge, in tile units, so lines and
# outlines join up across tiles.
BUFFER = 64
MEDIA_TYPE = "application/vnd.mapbox-vector-tile"


class TileOutOfRangeError(NotFoundError):
    code = "tile_out_of_range"
    message = "There is no tile with that address."


class InvalidTileFilterError(BadRequestError):
    code = "invalid_tile_filter"


_FILTER = """
    WHERE s.enabled
      AND r.geom && bounds.area
      AND (CAST(:categories AS text[]) IS NULL OR r.category = ANY (CAST(:categories AS text[])))
"""

_BUSY = text(
    f"""
    WITH bounds AS (
        SELECT ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => :margin), 4326) AS area
    )
    SELECT count(*) FROM (
        SELECT 1 FROM records r JOIN sources s ON s.key = r.source_key CROSS JOIN bounds
        {_FILTER}
        LIMIT :cap + 1
    ) AS busy
    """
)

_FEATURES = text(
    f"""
    WITH bounds AS (
        SELECT ST_TileEnvelope(:z, :x, :y) AS tile,
               ST_Transform(ST_TileEnvelope(:z, :x, :y, margin => :margin), 4326) AS area
    )
    SELECT ST_AsMVT(features, 'records', :extent, 'geom', 'id')
    FROM (
        SELECT r.id, r.name, r.category, r.record_type AS type, r.source_key AS source, s.reuse,
               ST_AsMVTGeom(ST_Transform(r.geom, 3857), bounds.tile, :extent, :buffer, true) AS geom
        FROM records r
        JOIN sources s ON s.key = r.source_key
        CROSS JOIN bounds
        {_FILTER}
    ) AS features
    WHERE features.geom IS NOT NULL
    """
)

_COUNTS = text(
    """
    WITH bounds AS (
        SELECT ST_TileEnvelope(:z, :x, :y) AS tile,
               ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326) AS area
    ),
    grid AS (
        SELECT tile, area, ST_XMin(tile) AS x0, ST_YMin(tile) AS y0,
               (ST_XMax(tile) - ST_XMin(tile)) / :grid AS cell
        FROM bounds
    ),
    placed AS (
        SELECT r.category, r.source_key, ST_Transform(r.centroid, 3857) AS point
        FROM records r
        JOIN sources s ON s.key = r.source_key
        CROSS JOIN grid
        WHERE s.enabled
          AND r.centroid && grid.area
          AND (CAST(:categories AS text[]) IS NULL OR r.category = ANY (CAST(:categories AS text[])))
    ),
    cells AS (
        SELECT p.category,
               floor((ST_X(p.point) - grid.x0) / grid.cell) AS gx,
               floor((ST_Y(p.point) - grid.y0) / grid.cell) AS gy,
               count(*) AS count,
               string_agg(DISTINCT p.source_key, ',' ORDER BY p.source_key) AS sources
        FROM placed p CROSS JOIN grid
        GROUP BY 1, 2, 3
    )
    SELECT ST_AsMVT(counted, 'record_counts', :extent, 'geom')
    FROM (
        SELECT cells.category, cells.count, cells.sources,
               ST_AsMVTGeom(
                   ST_SetSRID(
                       ST_MakePoint(
                           grid.x0 + (cells.gx + 0.5) * grid.cell,
                           grid.y0 + (cells.gy + 0.5) * grid.cell
                       ),
                       3857
                   ),
                   grid.tile, :extent, 0, true
               ) AS geom
        FROM cells CROSS JOIN grid
    ) AS counted
    WHERE counted.geom IS NOT NULL
    """
)


def check_tile(z: int, x: int, y: int) -> None:
    if not 0 <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise TileOutOfRangeError(f"{z}/{x}/{y} is not a tile. Zoom runs from 0 to {MAX_ZOOM}.")


def check_categories(categories: list[str] | None) -> list[str] | None:
    if not categories:
        return None
    unknown = [value for value in categories if value not in RecordCategory]
    if unknown:
        raise InvalidTileFilterError(f"Unknown record categories: {', '.join(unknown)}.")
    return sorted(set(categories))


def record_tile(db: Session, z: int, x: int, y: int, categories: list[str] | None = None) -> bytes:
    """The tile at `z/x/y`: counts below `FEATURES_FROM_ZOOM`, records from it up."""
    check_tile(z, x, y)
    params = {"z": z, "x": x, "y": y, "extent": EXTENT, "categories": check_categories(categories)}
    if z >= FEATURES_FROM_ZOOM and not is_busy(db, params):
        statement, params = _FEATURES, params | {"buffer": BUFFER, "margin": BUFFER / EXTENT}
    else:
        statement, params = _COUNTS, params | {"grid": GRID}
    tile = db.execute(statement, params).scalar()
    return bytes(tile) if tile is not None else b""


def is_busy(db: Session, params: dict[str, object]) -> bool:
    """Whether a tile has more records than one tile should carry one by one."""
    found = db.execute(_BUSY, params | {"margin": BUFFER / EXTENT, "cap": MAX_TILE_FEATURES}).scalar()
    assert found is not None, "count(*) always returns a row"
    return found > MAX_TILE_FEATURES
