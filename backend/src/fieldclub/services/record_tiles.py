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

Counting a low-zoom tile from `records` meant transforming every centroid in
it, over a second a tile at a million records. So the counts below
`FEATURES_FROM_ZOOM` come from `record_cell_counts`, which holds each cell
of every level a count tile uses, per source and category.
`refresh_counts` rebuilds one source's cells, and the ingest runner calls it
after every run. A busy tile at a feature zoom covers a small area, so it is
still counted from `records`.

The live queries filter on an indexed column first: `centroid` for counts
and `geom` for features, against the tile's envelope in EPSG:4326. A Web
Mercator tile is a longitude and latitude rectangle, so that test is exact.
A tile with nothing in it is an empty byte string, which is a valid tile
with no layers.

Tiles change only when an ingest run completes or a source is switched on or
off. `tile_token` is a token of both, and `/meta` gives the tile address with
it as `?v=`, so a tile asked for with the current token can be cached as
immutable and an ingest reaches every browser at once.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import TextClause, func, select, text
from sqlalchemy.orm import Session

from fieldclub.errors import BadRequestError, TileNotFoundError
from fieldclub.models import IngestRun, Source
from fieldclub.terrain.grid import HALF_WORLD
from fieldclub.vocab import IngestStatus, RecordCategory

MAX_ZOOM = 22
FEATURES_FROM_ZOOM = 12
# 500,000 synthetic records put 15,358 in the densest zoom-12 tile, which came
# to 942 KB. 5,000 keeps a tile to about 300 KB.
MAX_TILE_FEATURES = 5000
GRID = 32
# A count tile at zoom z is a GRID by GRID block of the cells at level z + CELL_LEVELS.
CELL_LEVELS = 5
assert 2**CELL_LEVELS == GRID, "a count cell must be a tile some zooms further in"
EXTENT = 4096
# How far features reach past the tile edge, in tile units, so lines and
# outlines join up across tiles.
BUFFER = 64
MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
# The address `/meta` gives, with `?v=` and the current `tile_token` after it.
TILE_TEMPLATE = "/tiles/records/{z}/{x}/{y}.mvt"
# Asked for with the current token, a tile can't change: the next ingest changes the token.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
# Without it, or with an old one, an hour fresh and a day stale, so an ingest shows the same day.
UNVERSIONED_CACHE = "public, max-age=3600, stale-while-revalidate=86400"


class InvalidTileFilterError(BadRequestError):
    code = "invalid_tile_filter"


# Every record, or only those of the categories asked for. Format with the table alias.
_CATEGORY = "(CAST(:categories AS text[]) IS NULL OR {alias}.category = ANY (CAST(:categories AS text[])))"

_FILTER = f"""
    WHERE s.enabled
      AND r.geom && bounds.area
      AND {_CATEGORY.format(alias="r")}
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
    f"""
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
          AND {_CATEGORY.format(alias="r")}
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


_STORED_COUNTS = text(
    f"""
    WITH cells AS (
        SELECT c.cx, c.cy, c.category, sum(c.count) AS count,
               string_agg(DISTINCT c.source_key, ',' ORDER BY c.source_key) AS sources
        FROM record_cell_counts c
        JOIN sources s ON s.key = c.source_key
        WHERE s.enabled
          AND c.level = :level
          AND c.cx BETWEEN :cx0 AND :cx0 + :grid - 1
          AND c.cy BETWEEN :cy0 AND :cy0 + :grid - 1
          AND {_CATEGORY.format(alias="c")}
        GROUP BY c.cx, c.cy, c.category
    )
    SELECT ST_AsMVT(counted, 'record_counts', :extent, 'geom')
    FROM (
        SELECT cells.category, cells.count, cells.sources,
               ST_AsMVTGeom(
                   ST_SetSRID(
                       ST_MakePoint(
                           -:half + (cells.cx + 0.5) * :cell,
                           :half - (cells.cy + 0.5) * :cell
                       ),
                       3857
                   ),
                   ST_TileEnvelope(:z, :x, :y), :extent, 0, true
               ) AS geom
        FROM cells
    ) AS counted
    WHERE counted.geom IS NOT NULL
    """
)

_CLEAR_COUNTS = text(
    "DELETE FROM record_cell_counts WHERE CAST(:source AS text) IS NULL OR source_key = :source"
)

# Each record's centroid in Web Mercator once, then its cell at every level.
_FILL_COUNTS = text(
    """
    INSERT INTO record_cell_counts (source_key, level, cx, cy, category, count)
    SELECT placed.source_key, levels.level,
           LEAST(GREATEST(
               CAST(floor((ST_X(placed.point) + :half) / (2 * :half) * power(2, levels.level)) AS integer), 0
           ), CAST(power(2, levels.level) AS integer) - 1),
           LEAST(GREATEST(
               CAST(floor((:half - ST_Y(placed.point)) / (2 * :half) * power(2, levels.level)) AS integer), 0
           ), CAST(power(2, levels.level) AS integer) - 1),
           placed.category, count(*)
    FROM (
        SELECT source_key, category, ST_Transform(centroid, 3857) AS point
        FROM records
        WHERE CAST(:source AS text) IS NULL OR source_key = :source
    ) AS placed
    CROSS JOIN generate_series(CAST(:first_level AS integer), CAST(:last_level AS integer)) AS levels (level)
    GROUP BY 1, 2, 3, 4, 5
    """
)


def refresh_counts(db: Session, source_key: str | None = None) -> None:
    """Rebuild the stored cell counts of one source, or of every source. Flushes, never commits."""
    params = {
        "source": source_key,
        "half": HALF_WORLD,
        "first_level": CELL_LEVELS,
        "last_level": FEATURES_FROM_ZOOM - 1 + CELL_LEVELS,
    }
    db.execute(_CLEAR_COUNTS, params)
    db.execute(_FILL_COUNTS, params)


def check_tile(z: int, x: int, y: int) -> None:
    if not 0 <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise TileNotFoundError(f"{z}/{x}/{y} is not a tile. Zoom runs from 0 to {MAX_ZOOM}.")


def tile_token(db: Session) -> str:
    """A token of what the tiles are drawn from: the last completed ingest run and the enabled sources."""
    finished = db.scalar(
        select(func.max(IngestRun.finished_at)).where(IngestRun.status == IngestStatus.COMPLETED.value)
    )
    enabled = db.scalars(select(Source.key).where(Source.enabled).order_by(Source.key)).all()
    stamp = finished.isoformat() if finished is not None else "never"
    return hashlib.sha256("\n".join([stamp, *enabled]).encode()).hexdigest()[:12]


def tile_url(token: str) -> str:
    return f"{TILE_TEMPLATE}?v={token}"


def check_categories(
    categories: list[str] | None, error: type[BadRequestError] = InvalidTileFilterError
) -> list[str] | None:
    """The categories asked for, sorted and without repeats, or None for all.

    An unknown category raises `error`, so each caller keeps its own error code.
    """
    if not categories:
        return None
    unknown = [value for value in categories if value not in RecordCategory]
    if unknown:
        raise error(f"Unknown record categories: {', '.join(unknown)}.")
    return sorted(set(categories))


def record_tile(db: Session, z: int, x: int, y: int, categories: list[str] | None = None) -> bytes:
    """The tile at `z/x/y`: stored counts below `FEATURES_FROM_ZOOM`, records from it up."""
    statement, params = tile_query(db, z, x, y, categories)
    tile = db.execute(statement, params).scalar()
    return bytes(tile) if tile is not None else b""


def tile_query(
    db: Session, z: int, x: int, y: int, categories: list[str] | None = None
) -> tuple[TextClause, dict[str, object]]:
    """The statement that builds the tile at `z/x/y`, and its parameters."""
    check_tile(z, x, y)
    params: dict[str, object] = {"z": z, "x": x, "y": y, "extent": EXTENT}
    params["categories"] = check_categories(categories)
    if z < FEATURES_FROM_ZOOM:
        level = z + CELL_LEVELS
        cells = {"level": level, "cx0": x * GRID, "cy0": y * GRID, "grid": GRID, "half": HALF_WORLD}
        return _STORED_COUNTS, params | cells | {"cell": 2 * HALF_WORLD / 2**level}
    if not is_busy(db, params):
        return _FEATURES, params | {"buffer": BUFFER, "margin": BUFFER / EXTENT}
    return _COUNTS, params | {"grid": GRID}


def is_busy(db: Session, params: dict[str, object]) -> bool:
    """Whether a tile has more records than one tile should carry one by one."""
    found = db.execute(_BUSY, params | {"margin": BUFFER / EXTENT, "cap": MAX_TILE_FEATURES}).scalar()
    assert found is not None, "count(*) always returns a row"
    return found > MAX_TILE_FEATURES
