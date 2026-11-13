"""Findings: list, map GeoJSON, create, read, edit, withdraw, sensitivity and exports.

Every response here depends on who is asking (Decision 0005), so each is
marked private and varies by cookie: a shared cache must never hand one
viewer's exact positions to another.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from fieldclub.api.deps import BBoxQuery, Contributor, CursorQuery, Db, OptionalUser, private, rate_limit

# Its home was here once. Kept importable for code written against that.
from fieldclub.errors import InvalidBboxError as InvalidBboxError
from fieldclub.errors import ValidationFailedError
from fieldclub.models import Finding, User
from fieldclub.schemas.common import MAX_LIMIT, Page, from_geojson, parse_bbox
from fieldclub.schemas.findings import (
    FindingCreate,
    FindingDetail,
    FindingFeatureCollection,
    FindingSummary,
    FindingUpdate,
    SensitivityChange,
    finding_feature,
)
from fieldclub.schemas.findings import Path as PathIn
from fieldclub.services import exports, findings, moderation, shape_edits, shapes
from fieldclub.services.findings import FindingFilters, FindingSort
from fieldclub.vocab import FeatureClass, FindingState, Sensitivity, Tier

router = APIRouter(tags=["findings"])

GEOJSON_DEFAULT_LIMIT = 500
GEOJSON_MAX_LIMIT = 1000
PAGE_DEFAULT_LIMIT = 50
EXPORT_DEFAULT_LIMIT = 1000


# A repeated filter can name each value at most once, so no list is longer than its vocabulary.
def list_filters(
    bbox: BBoxQuery = None,
    tier: Annotated[list[Tier] | None, Query(max_length=len(Tier))] = None,
    state: Annotated[
        list[FindingState] | None,
        Query(max_length=len(FindingState), description="Withdrawn findings only when asked for"),
    ] = None,
    feature_class: Annotated[list[FeatureClass] | None, Query(max_length=len(FeatureClass))] = None,
    author: Annotated[str | None, Query(max_length=64, description="A handle")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort: FindingSort = FindingSort.NEWEST,
) -> FindingFilters:
    return FindingFilters(
        bbox=parse_bbox(bbox),
        tier=tuple(dict.fromkeys(tier or ())),
        state=tuple(dict.fromkeys(state or ())),
        feature_class=tuple(dict.fromkeys(feature_class or ())),
        author=author,
        q=q,
        sort=sort,
    )


Filters = Annotated[FindingFilters, Depends(list_filters)]


def detail(db: Db, finding: Finding, viewer: User | None) -> FindingDetail:
    return FindingDetail.from_view(findings.finding_view(db, finding, viewer), viewer)


# Declared before `/findings/{public_id}` so that "export" isn't read as an id.
@router.get(
    "/findings/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/geo+json": {}}}},
    dependencies=[Depends(rate_limit("findings_export", 60, per_seconds=3600))],
)
def export_findings(
    db: Db,
    viewer: OptionalUser,
    filters: Filters,
    format: Literal["geojson", "csv"] = "geojson",
    limit: Annotated[int, Query(ge=1, le=exports.MAX_EXPORT)] = EXPORT_DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Response:
    """A filtered set of findings as GeoJSON or HER-ready CSV. The next cursor is in `X-Next-Cursor`."""
    page = findings.list_findings(db, viewer, filters, limit=limit, cursor=cursor)
    response = _download(db, page.findings, viewer, format, "openantiquity-findings")
    if page.next_cursor is not None:
        response.headers["X-Next-Cursor"] = page.next_cursor
    return response


def _download(
    db: Db,
    chosen: list[Finding],
    viewer: User | None,
    format: str,
    name: str,
) -> Response:
    rows = exports.export_rows(db, chosen, viewer)
    if format == "csv":
        body, media_type = exports.to_csv(rows), "text/csv; charset=utf-8"
    else:
        body, media_type = exports.to_feature_collection(rows).model_dump_json(), "application/geo+json"
    response = Response(content=body, media_type=media_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{name}.{format}"'
    private(response)
    return response


@router.get("/findings", response_model=Page[FindingSummary] | FindingFeatureCollection)
def list_findings(
    db: Db,
    viewer: OptionalUser,
    response: Response,
    filters: Filters,
    format: Literal["json", "geojson"] = "json",
    limit: Annotated[int | None, Query(ge=1, le=GEOJSON_MAX_LIMIT)] = None,
    cursor: CursorQuery = None,
    zoom: Annotated[
        int,
        Query(
            ge=shape_edits.MAP_ZOOM_MIN,
            le=shape_edits.MAP_ZOOM_MAX,
            description="The map's zoom, which sets how simplified GeoJSON shapes are",
        ),
    ] = shape_edits.MAP_ZOOM_DEFAULT,
) -> Page[FindingSummary] | FindingFeatureCollection:
    """Findings as this viewer may see them, as a page or as GeoJSON for the map.

    `bbox` matches the position the viewer may see, so an obscured finding
    matches by the centre of its square, and a line or shape the viewer sees
    exactly matches wherever it crosses the box. A page holds up to 200;
    GeoJSON up to 1000, with the next page's cursor as `next_cursor`, and each
    exact shape simplified for `zoom` and cut to the box.
    """
    private(response)
    if format == "geojson":
        page = findings.list_findings(
            db, viewer, filters, limit=limit or GEOJSON_DEFAULT_LIMIT, cursor=cursor
        )
        drawn = shape_edits.map_shapes(db, page.findings, viewer, zoom=zoom, bbox=filters.bbox)
        return FindingFeatureCollection(
            features=[finding_feature(finding, viewer, drawn.get(finding.id)) for finding in page.findings],
            next_cursor=page.next_cursor,
        )
    if limit is not None and limit > MAX_LIMIT:
        # The same answer as any other limit out of range, though the cap depends on the format.
        message = f"A page holds at most {MAX_LIMIT} findings, and GeoJSON {GEOJSON_MAX_LIMIT}."
        raise ValidationFailedError(details=[{"field": "query.limit", "message": message}])
    page = findings.list_findings(db, viewer, filters, limit=limit or PAGE_DEFAULT_LIMIT, cursor=cursor)
    authors = findings.users_by_id(db, (f.author_id for f in page.findings))
    return Page[FindingSummary](
        items=[FindingSummary.build(f, authors[f.author_id], viewer) for f in page.findings],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/findings",
    response_model=FindingDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("findings_create", 60, per_seconds=3600))],
)
def create_finding(body: FindingCreate, user: Contributor, db: Db, response: Response) -> FindingDetail:
    """Mark a finding. A point or a path, and a feature class, are all it needs.

    With a `client_ref` the same person has sent before, this answers 200
    with the finding that request made, and stores nothing.
    """
    fields = {
        "location": from_geojson(body.location, allowed=["Point"]) if body.location is not None else None,
        "feature_class": body.feature_class,
        "title": body.title,
        "description": body.description,
        "period": body.period,
        "path": _read_path(body.path),
        "outline": from_geojson(body.outline) if body.outline is not None else None,
        "view_state": body.view_state.to_stored() if body.view_state is not None else None,
        "requested_sensitivity": body.sensitivity,
    }
    if body.client_ref is None:
        finding = findings.create_finding(db, user, **fields)
    else:
        finding, created = findings.create_finding_once(db, user, body.client_ref, **fields)
        if not created:
            response.status_code = status.HTTP_200_OK
    db.commit()
    private(response)
    return detail(db, finding, user)


@router.get("/findings/{public_id}", response_model=FindingDetail)
def get_finding(public_id: str, db: Db, viewer: OptionalUser, response: Response) -> FindingDetail:
    """A finding's page. Other people's answers are left out until you have given yours."""
    private(response)
    return detail(db, findings.get_finding(db, public_id, viewer), viewer)


@router.patch(
    "/findings/{public_id}",
    response_model=FindingDetail,
    dependencies=[Depends(rate_limit("findings_edit", 120, per_seconds=3600))],
)
def update_finding(
    public_id: str, body: FindingUpdate, user: Contributor, db: Db, response: Response
) -> FindingDetail:
    """The finder corrects their finding. Fields left out are left alone."""
    changes = body.model_dump(exclude_unset=True)
    if "location" in changes:
        changes["location"] = from_geojson(body.location, allowed=["Point"]) if body.location else None
        if changes["location"] is None:
            raise findings.LocationRequiredError()
    if "path" in changes:
        changes["path"] = _read_path(body.path)
    if "outline" in changes:
        changes["outline"] = from_geojson(body.outline) if body.outline else None
    if "view_state" in changes:
        changes["view_state"] = body.view_state.to_stored() if body.view_state is not None else None
    finding = findings.lock_finding(db, public_id, user)
    findings.update_finding(db, finding, user, changes)
    db.commit()
    private(response)
    return detail(db, finding, user)


def _read_path(path: PathIn | None) -> shapes.Path | None:
    return shapes.read_path(path.model_dump()) if path is not None else None


@router.post(
    "/findings/{public_id}/withdraw",
    response_model=FindingDetail,
    dependencies=[Depends(rate_limit("findings_edit", 120, per_seconds=3600))],
)
def withdraw_finding(public_id: str, user: Contributor, db: Db, response: Response) -> FindingDetail:
    """The finder takes their finding back. It stays visible, marked withdrawn."""
    finding = findings.lock_finding(db, public_id, user)
    findings.withdraw_finding(db, finding, user)
    db.commit()
    private(response)
    return detail(db, finding, user)


@router.put(
    "/findings/{public_id}/sensitivity",
    response_model=FindingDetail,
    dependencies=[Depends(rate_limit("findings_sensitivity", 60, per_seconds=3600))],
)
def change_sensitivity(
    public_id: str, body: SensitivityChange, user: Contributor, db: Db, response: Response
) -> FindingDetail:
    """Raise a finding's level: its finder, a trusted member or a moderator.

    A moderator lowers a level with `PUT /mod/findings/{public_id}/sensitivity`, which logs it.
    A moderator raising someone else's finding here is logged too, with no reason.
    """
    finding = findings.lock_finding(db, public_id, user)
    moderation.raise_sensitivity(db, finding, user, Sensitivity(body.level))
    db.commit()
    private(response)
    return detail(db, finding, user)


@router.get(
    "/findings/{public_id}/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/geo+json": {}}}},
    dependencies=[Depends(rate_limit("findings_export", 60, per_seconds=3600))],
)
def export_finding(
    public_id: str,
    db: Db,
    viewer: OptionalUser,
    format: Literal["geojson", "csv"] = "geojson",
) -> Response:
    """One finding as GeoJSON or HER-ready CSV."""
    finding = findings.get_finding(db, public_id, viewer)
    return _download(db, [finding], viewer, format, f"openantiquity-finding-{finding.public_id}")
