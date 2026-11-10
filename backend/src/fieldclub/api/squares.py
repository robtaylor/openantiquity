"""Scan a square: the next square, your result for one, and the coverage layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from fieldclub.api.deps import Contributor, Db, OptionalUser, private, rate_limit, split_list
from fieldclub.errors import BadRequestError
from fieldclub.schemas.common import is_bbox, split_bbox
from fieldclub.schemas.squares import CoverageCollection, SquareOut, SurveyIn, SurveyOut, coverage_feature
from fieldclub.services import squares

router = APIRouter(prefix="/squares", tags=["squares"])


class InvalidBboxError(BadRequestError):
    code = "invalid_bbox"
    message = "bbox must be west,south,east,north in degrees, running west to east and south to north."


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
    exclude: Annotated[
        str | None,
        Query(max_length=squares.MAX_EXCLUDE * 12, description="Squares to leave out, comma-separated"),
    ] = None,
) -> SquareOut:
    """A 1 km square few people have scanned, near `lon` and `lat` when given.

    Never one you have already done. Signed out, pass the squares in your
    drafts as `exclude`. Only squares with 1 m elevation are offered.
    """
    if (lon is None) != (lat is None):
        raise BadRequestError("Give both lon and lat, or neither.", code="invalid_point")
    names = split_list(exclude) or []
    if len(names) > squares.MAX_EXCLUDE:
        raise BadRequestError(f"Leave out at most {squares.MAX_EXCLUDE} squares.", code="too_many_excluded")
    left_out = {squares.name(squares.parse_square(text)) for text in names}
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
    dependencies=[Depends(rate_limit("squares_coverage", 1200, per_seconds=3600))],
)
def get_coverage(
    db: Db,
    response: Response,
    bbox: Annotated[str, Query(max_length=200, description="west,south,east,north")],
) -> CoverageCollection:
    """How many people have scanned each 1 km square in view, as polygons for the map.

    The box may span at most 2,500 square kilometres. The answer is the same
    for everyone.
    """
    try:
        box = split_bbox(bbox)
    except ValueError:
        raise InvalidBboxError() from None
    if not is_bbox(box):
        raise InvalidBboxError()
    cells = squares.coverage(db, box)
    response.headers["Cache-Control"] = "public, max-age=300"
    return CoverageCollection(features=[coverage_feature(cell) for cell in cells])
