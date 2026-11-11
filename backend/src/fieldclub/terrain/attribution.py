"""The `sources` rows for the elevation the terrain layers show, so `/meta` attributes them like other data.

CLAUDE.md asks for a `sources` row, with licence and attribution, before any
of a dataset's data is stored or shown. The terrain service stores and shows
two of the work list's Defra LIDAR entries (`docs/sources/worklists/sources.json`):

- the 2022 composite DTM at 1 m, which fills the mirror and, through it, the
  national overview, from Defra's SFTP bulk supply;
- the survey index catalogue, whose flight dates give the coverage layer its
  capture years (`years.py`).

The work list's other two `defra-lidar-` entries, the post-2022 tiles and
the 10 m composite, have no row: nothing of theirs is stored or shown.

The attribution and licence URL are the work list's, word for word. Three
fields follow the project rather than the work list: the licence is spelt
"Open Government Licence v3.0", as in `layers.py` and the other connectors;
the category is `elevation`, because the work list's `lidar_index` is a
record category and nothing here is a record; and `access` is the
`SourceAccess` of Decision 0007, how Field Club holds the data, which is
`bulk` for both, although the survey index is read over WFS (the work list's
`access_method` is how it is fetched).

`register_sources` writes both rows and is idempotent. Every
`fieldclub-terrain` command that stores elevation calls it first, and
`fieldclub-terrain sources` runs it on its own, for a deployment.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.runner import upsert_source
from fieldclub.vocab import SourceAccess, SourceReuse

OGL_V3 = "Open Government Licence v3.0"
OGL_V3_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
EA_2022 = "© Environment Agency copyright and/or database right 2022. All rights reserved."
# Not a record category: elevation feeds the terrain layers, not the index.
ELEVATION = "elevation"

COMPOSITE_1M = SourceInfo(
    key="defra-lidar-composite-dtm-2022-1m",
    name="LIDAR Composite DTM 2022, 1 m",
    publisher="Environment Agency / Defra Data Services Platform",
    licence=OGL_V3,
    licence_url=OGL_V3_URL,
    attribution=EA_2022,
    category=ELEVATION,
    access=SourceAccess.BULK,
    reuse=SourceReuse.OPEN,
    homepage="https://environment.data.gov.uk/dataset/13787b9a-26a4-4775-8523-806d13af58fc",
    coverage="england",
)

SURVEY_INDEX = SourceInfo(
    key="defra-lidar-survey-index-catalogues",
    name="LIDAR survey index catalogues",
    publisher="Environment Agency",
    licence=OGL_V3,
    licence_url=OGL_V3_URL,
    attribution=EA_2022,
    category=ELEVATION,
    access=SourceAccess.BULK,
    reuse=SourceReuse.OPEN,
    homepage="https://environment.data.gov.uk/dataset/9f0fa3fc-a860-4729-adc9-47fe53f658d0",
    coverage="england",
)

TERRAIN_SOURCES = (COMPOSITE_1M, SURVEY_INDEX)


def register_sources(db: Session) -> list[str]:
    """Create or refresh the terrain's `sources` rows. Flushes, never commits. Returns their keys."""
    for info in TERRAIN_SOURCES:
        upsert_source(db, info)
    db.flush()
    return [info.key for info in TERRAIN_SOURCES]
