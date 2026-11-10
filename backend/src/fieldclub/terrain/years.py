"""The years each 5 km tile's elevation was flown, from Defra's survey index (Decision 0006, point 7).

The 2022 composite is stitched from surveys flown between 2000 and 2022.
Defra's index of the surveys behind it (`LIDAR_Composite_1m_DTM_2022_extents`,
21,380 polygons) gives each one's flight dates. `data/england-dtm-2022-years.tsv`
lists, for every tile the polygons reach, the years from the first flight date
to the last of each survey that covers part of it. It is a packaged file,
like the tile catalogue, so the coverage layer reads it without a network
call. `fieldclub-terrain years build` writes it again.

A build asks the index's WFS twice over:

1. the dates and bounding box of every polygon, without geometry, in one
   request of about 5.5 MB;
2. the outline, in British National Grid metres, of only the polygons whose
   box spans more than one tile (about 4,500), in batches of `BATCH`, which
   keeps each address under the 8 KB the server takes.

A polygon whose box lies inside one tile counts for that tile. One that spans
several counts for each tile it overlaps by more than `MIN_OVERLAP_M2`, so a
survey that only touches a tile's edge doesn't add its year there.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from fieldclub.ingest.adapters.common import Polite
from fieldclub.terrain.catalogue import TILE_METRES, Catalogue, tile_name_at

logger = logging.getLogger(__name__)

WFS_URL = "https://environment.data.gov.uk/spatialdata/survey-index-files/wfs"
LAYER = "dataset-9f0fa3fc-a860-4729-adc9-47fe53f658d0:LIDAR_Composite_1m_DTM_2022_extents"
EXPECTED_POLYGONS = 21_380
BATCH = 100
MIN_OVERLAP_M2 = 1_000.0
YEARS_FILE = "data/england-dtm-2022-years.tsv"


@dataclass(frozen=True)
class Survey:
    """One polygon of the index: where a survey's data sits in the composite, and when it was flown."""

    id: str
    bbox: tuple[float, float, float, float]
    years: tuple[int, ...]

    @property
    def tiles(self) -> list[tuple[int, int]]:
        """The 5 km cells (column, row) its bounding box overlaps by more than an edge."""
        west, south, east, north = self.bbox
        cols = range(math.floor(west / TILE_METRES), math.ceil(east / TILE_METRES))
        rows = range(math.floor(south / TILE_METRES), math.ceil(north / TILE_METRES))
        return [(col, row) for col in cols for row in rows]


def flown_years(properties: dict[str, Any]) -> tuple[int, ...]:
    """Every year from the first flight date to the last, or the survey's `year` without dates."""
    start, end = properties.get("sd_flown"), properties.get("ed_flown")
    if start and end:
        first, last = date.fromisoformat(start[:10]).year, date.fromisoformat(end[:10]).year
        assert first <= last, f"flown from {start} to {end}"
        assert last - first < 5, f"a survey flown from {start} to {end} is longer than any seen"
        return tuple(range(first, last + 1))
    year = properties.get("year")
    assert year, f"a survey with no dates and no year: {properties}"
    assert str(year).isdigit(), f"a survey's year is {year!r}"
    return (int(year),)


def parse_surveys(body: dict[str, Any]) -> list[Survey]:
    assert body.get("type") == "FeatureCollection", "the index answered something other than GeoJSON"
    features = body["features"]
    assert body.get("numberMatched") == len(features), (
        f"the index matched {body.get('numberMatched')} polygons and returned {len(features)}"
    )
    surveys = []
    for feature in features:
        bbox = feature.get("bbox")
        assert bbox, f"{feature.get('id')} has no bounding box"
        assert len(bbox) == 4, f"{feature.get('id')} has the box {bbox}"
        west, south, east, north = (float(value) for value in bbox)
        # British National Grid metres, which is what the index stores.
        assert 0 <= west <= east <= 700_000, f"{feature['id']} box {bbox} isn't in grid metres"
        assert 0 <= south <= north <= 1_300_000, f"{feature['id']} box {bbox} isn't in grid metres"
        surveys.append(
            Survey(str(feature["id"]), (west, south, east, north), flown_years(feature["properties"]))
        )
    return surveys


class IndexClient:
    """The index's WFS, asked politely: a second between requests, retries with back-off."""

    def __init__(
        self, client: httpx.Client, polite: Polite | None = None, *, expected: int = EXPECTED_POLYGONS
    ) -> None:
        self.client = client
        self.polite = polite or Polite()
        # Fewer than 90% of this many polygons means the answer was cut short.
        self.expected = expected
        self.requests = 0
        self.bytes = 0

    def _get(self, params: dict[str, str]) -> dict[str, Any]:
        base = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": LAYER,
            "outputFormat": "application/json",
        }
        response = self.polite.request(self.client, "GET", WFS_URL, params={**base, **params})
        self.requests += 1
        self.bytes += len(response.content)
        return response.json()

    def surveys(self) -> list[Survey]:
        body = self._get({"count": "30000", "propertyName": "year,sd_flown,ed_flown"})
        surveys = parse_surveys(body)
        assert len(surveys) >= self.expected * 0.9, f"the index listed only {len(surveys)} polygons"
        return surveys

    def outlines(self, ids: Sequence[str]) -> Iterator[tuple[str, BaseGeometry]]:
        for start in range(0, len(ids), BATCH):
            batch = ids[start : start + BATCH]
            body = self._get(
                {"resourceId": ",".join(batch), "srsName": "EPSG:27700", "propertyName": "shape"}
            )
            found = {str(feature["id"]): feature["geometry"] for feature in body["features"]}
            missing = set(batch) - set(found)
            assert not missing, f"the index didn't return {sorted(missing)[:5]}"
            for feature_id in batch:
                yield feature_id, shape(found[feature_id])


def years_by_tile(
    catalogue: Catalogue,
    surveys: Iterable[Survey],
    outlines: Callable[[Sequence[str]], Iterable[tuple[str, BaseGeometry]]],
) -> dict[str, tuple[int, ...]]:
    """The years flown over each catalogue tile that any survey covers."""
    found: dict[str, set[int]] = defaultdict(set)

    def add(cell: tuple[int, int], years: tuple[int, ...]) -> None:
        name = tile_name_at(cell[0] * TILE_METRES, cell[1] * TILE_METRES)
        if name in catalogue:
            found[name].update(years)

    spanning: dict[str, Survey] = {}
    for survey in surveys:
        cells = survey.tiles
        if len(cells) == 1:
            add(cells[0], survey.years)
        elif cells:
            spanning[survey.id] = survey
    for survey_id, outline in outlines(sorted(spanning)):
        survey = spanning[survey_id]
        for col, row in survey.tiles:
            cell = box(col * TILE_METRES, row * TILE_METRES, (col + 1) * TILE_METRES, (row + 1) * TILE_METRES)
            if outline.intersection(cell).area > MIN_OVERLAP_M2:
                add((col, row), survey.years)
    return {name: tuple(sorted(years)) for name, years in sorted(found.items())}


def format_years(years: dict[str, tuple[int, ...]], *, fetched: date, polygons: int) -> str:
    lines = [
        "# The years each 5 km tile of the 2022 composite DTM was flown, from the Environment Agency's",
        "# LIDAR_Composite_1m_DTM_2022_extents survey index. Written by `fieldclub-terrain years build`.",
        f"# Fetched {fetched.isoformat()} from {polygons} polygons. tile<TAB>years, comma-separated.",
    ]
    lines += [f"{name}\t{','.join(str(year) for year in found)}" for name, found in years.items()]
    return "\n".join(lines) + "\n"


def parse_years(text: str) -> dict[str, tuple[int, ...]]:
    years: dict[str, tuple[int, ...]] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.startswith("#"):
            continue
        name, _, listed = raw.partition("\t")
        values = tuple(int(year) for year in listed.split(","))
        assert values == tuple(sorted(set(values))), f"line {number}: years must be sorted and distinct"
        assert all(1995 <= year <= 2030 for year in values), f"line {number}: {values} out of range"
        assert name not in years, f"line {number}: {name} is listed twice"
        years[name] = values
    return years


def build(catalogue: Catalogue, index: IndexClient, dest: Path) -> dict[str, tuple[int, ...]]:
    """Fetch the index, work out each tile's years and write them to `dest`."""
    surveys = index.surveys()
    years = years_by_tile(catalogue, surveys, index.outlines)
    dest.write_text(
        format_years(years, fetched=datetime.now(UTC).date(), polygons=len(surveys)), encoding="utf-8"
    )
    return years


def packaged_path() -> Path:
    """Where the packaged years file lives in a source checkout, for `years build` to write."""
    return Path(str(resources.files("fieldclub.terrain").joinpath(YEARS_FILE)))


@lru_cache(maxsize=1)
def england_years() -> dict[str, tuple[int, ...]]:
    """The packaged years, by tile name."""
    return parse_years(resources.files("fieldclub.terrain").joinpath(YEARS_FILE).read_text("utf-8"))


@lru_cache(maxsize=1)
def years_edition() -> str:
    """Changes whenever the packaged file does, for the coverage layer's ETag."""
    data = resources.files("fieldclub.terrain").joinpath(YEARS_FILE).read_bytes()
    return hashlib.sha256(data).hexdigest()[:12]
