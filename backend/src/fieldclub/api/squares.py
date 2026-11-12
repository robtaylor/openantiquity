"""Scan a square: the next square, your result for one, and the coverage layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import StringConstraints

from fieldclub.api.deps import Contributor, Db, OptionalUser, private, rate_limit
from fieldclub.errors import BadRequestError
from fieldclub.ratelimit import rate_limit_by_address
from fieldclub.schemas.common import parse_bbox
from fieldclub.schemas.squares import CoverageCollection, SquareOut, SurveyIn, SurveyOut, coverage_feature
from fieldclub.services import squares

router = APIRouter(prefix="/squares", tags=["squares"])

# Repeated parameters, `exclude=SU1069&exclude=SU1070`, as every list filter is.
ExcludeParam = Annotated[
    list[Annotated[str, StringConstraints(min_length=1, max_length=12)]] | None,
    Query(max_length=squares.MAX_EXCLUDE, description="Squares to leave out, such as `SU1069`"),
]


@router.get(
    "/next",
    response_model=SquareOut,
    dependencies=[Depends(rate_limit("squares_next", 600, per_seconds=3600))],
)
def next_square(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    exclude: ExcludeParam = None,
) -> SquareOut:
    """A 1 km square few people have scanned, near `lon` and `lat` when given.

    Never one you have already done. Signed out, pass the squares in your
    drafts as `exclude`. Only squares with 1 m elevation are offered.
    """
    if (lon is None) != (lat is None):
        raise BadRequestError("Give both lon and lat, or neither.", code="invalid_point")
    left_out = {squares.name(squares.parse_square(text)) for text in exclude or []}
    near = (lon, lat) if lon is not None and lat is not None else None
    chosen = squares.next_square(db, viewer, near=near, exclude=left_out)
    private(response)
    return SquareOut.build(chosen.ref, chosen.scans)


@router.put(
    "/{ref}",
    response_model=SurveyOut,
    responses={201: {"model": SurveyOut, "description": "Your first result for this square"}},
    dependencies=[Depends(rate_limit("squares_record", 300, per_seconds=3600))],
)
def record_survey(ref: str, body: SurveyIn, user: Contributor, db: Db, response: Response) -> SurveyOut:
    """Keep your result for a square. Sending another replaces it: there is one per person and square."""
    survey, created = squares.record_survey(
        db,
        user,
        squares.parse_square(ref),
        body.result,
        findings_count=body.findings_count,
        seconds=body.seconds,
    )
    db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    private(response)
    return SurveyOut.build(survey)


@router.get(
    "/coverage",
    response_model=CoverageCollection,
    # By address alone: the answer is public, so it must never carry a refreshed session cookie.
    dependencies=[Depends(rate_limit_by_address("squares_coverage", 1200, per_seconds=3600))],
)
def get_coverage(
    db: Db,
    response: Response,
    bbox: Annotated[str, Query(max_length=200, description="west,south,east,north in degrees")],
) -> CoverageCollection:
    """How many people have scanned each 1 km square in view, as polygons for the map.

    The box may span at most 2,500 square kilometres. The answer is the same
    for everyone.
    """
    box = parse_bbox(bbox)
    assert box is not None, "bbox is required"
    cells = squares.coverage(db, box)
    response.headers["Cache-Control"] = "public, max-age=300"
    return CoverageCollection(features=[coverage_feature(cell) for cell in cells])
