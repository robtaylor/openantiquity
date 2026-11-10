"""Context for the map: live sources the browser queries itself, and links to external viewers.

See Decision 0007. The server stores nothing from either.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query, Response

from fieldclub.api.deps import Db
from fieldclub.schemas.records import ContextLink, ContextLinks, LiveSourceOut, LiveSources
from fieldclub.services import context

router = APIRouter(prefix="/context", tags=["context"])

# The catalogue changes only with a deploy.
CATALOGUE_CACHE = "public, max-age=86400"
# The links for a point also depend on which nation it is in, from
# `admin_areas`, so a change there must reach browsers within the hour.
LINKS_CACHE = "public, max-age=3600"


@router.get("/live-sources", response_model=LiveSources)
def live_sources(response: Response) -> LiveSources:
    """The sources the browser queries for an area, with how to ask and how to credit each."""
    response.headers["Cache-Control"] = CATALOGUE_CACHE
    return LiveSources(items=[LiveSourceOut.model_validate(item) for item in context.live_sources()])


@router.get("/links", response_model=ContextLinks)
def links(
    db: Db,
    response: Response,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    zoom: Annotated[int, Query(ge=1, le=20)] = context.DEFAULT_ZOOM,
) -> ContextLinks:
    """Links that open external viewers at this point, for the ones that cover it."""
    found = context.links_for(db, lon, lat, zoom)
    response.headers["Cache-Control"] = LINKS_CACHE
    return ContextLinks(grid_ref=found.grid_ref, items=[ContextLink(**asdict(link)) for link in found.links])
