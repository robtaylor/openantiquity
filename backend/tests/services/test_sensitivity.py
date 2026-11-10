"""One function decides what location a viewer may see (Decision 0005).

The viewer table in docs/ARCHITECTURE.md, "Location sensitivity":

| Viewer                             | open  | protected   | restricted  |
| Signed out                         | exact | 1 km square | 1 km square |
| Member                             | exact | exact       | 1 km square |
| Finder, trusted, expert, moderator | exact | exact       | exact       |
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pyproj import Geod
from shapely.geometry import Point, box
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.errors import DataIntegrityError, ForbiddenError
from fieldclub.models import Finding, User
from fieldclub.models.common import db_point, to_db_geometry
from fieldclub.services import sensitivity
from fieldclub.services.sensitivity import (
    VisibleLocation,
    change_sensitivity,
    default_sensitivity,
    level_after_class_change,
    may_change_sensitivity,
    public_point,
    sees_exact,
    square_centre,
    starting_sensitivity,
    visible_location,
)
from fieldclub.vocab import FeatureClass, Sensitivity
from tests.helpers import MakeFinding, MakeUser, lon_lat

LON, LAT = -1.8542, 51.4286
OUTLINE = box(LON - 0.0005, LAT - 0.0003, LON + 0.0005, LAT + 0.0003)
GEOD = Geod(ellps="WGS84")
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

OPEN, PROTECTED, RESTRICTED = Sensitivity.OPEN, Sensitivity.PROTECTED, Sensitivity.RESTRICTED

# Every kind of viewer, and what the table says each one sees at each level.
EXACT, SQUARE = True, False
VIEWER_TABLE: dict[str, dict[Sensitivity, bool]] = {
    "signed_out": {OPEN: EXACT, PROTECTED: SQUARE, RESTRICTED: SQUARE},
    "member": {OPEN: EXACT, PROTECTED: EXACT, RESTRICTED: SQUARE},
    "finder": {OPEN: EXACT, PROTECTED: EXACT, RESTRICTED: EXACT},
    "trusted": {OPEN: EXACT, PROTECTED: EXACT, RESTRICTED: EXACT},
    "expert": {OPEN: EXACT, PROTECTED: EXACT, RESTRICTED: EXACT},
    "moderator": {OPEN: EXACT, PROTECTED: EXACT, RESTRICTED: EXACT},
    "admin": {OPEN: EXACT, PROTECTED: EXACT, RESTRICTED: EXACT},
    # A banned or deleted account is treated as signed out, whatever its role.
    "banned_expert": {OPEN: EXACT, PROTECTED: SQUARE, RESTRICTED: SQUARE},
    "deleted_moderator": {OPEN: EXACT, PROTECTED: SQUARE, RESTRICTED: SQUARE},
    "banned_finder": {OPEN: EXACT, PROTECTED: SQUARE, RESTRICTED: SQUARE},
}

CASES = [(viewer, level) for viewer in VIEWER_TABLE for level in Sensitivity]


def viewer_for(kind: str, finder: User, make_user: MakeUser, db: Session) -> User | None:
    if kind == "signed_out":
        return None
    if kind == "finder":
        return finder
    if kind == "banned_finder":
        finder.banned_at = NOW
        db.commit()
        return finder
    if kind == "banned_expert":
        return make_user("expert", banned_at=NOW)
    if kind == "deleted_moderator":
        return make_user("moderator", deleted_at=NOW)
    return make_user(kind)


def assert_exact(seen: VisibleLocation, lon: float = LON, lat: float = LAT) -> None:
    assert seen.obscured is False
    assert (seen.lon, seen.lat) == pytest.approx((lon, lat), abs=1e-9)
    assert seen.square is None


def assert_square(seen: VisibleLocation, square: str = "SU1069") -> None:
    assert seen.obscured is True
    assert seen.outline is None
    assert seen.square == square
    assert seen.grid_ref == gridref.parse_gridref(square).format()
    assert (seen.lon, seen.lat) == pytest.approx(gridref.centre_of_square(square), abs=1e-9)


# --------------------------------------------------------------------------
# The viewer table
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("viewer_kind", "level"), CASES, ids=[f"{v}-{lvl}" for v, lvl in CASES])
def test_every_viewer_against_every_level(
    viewer_kind: str, level: Sensitivity, make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    finder = make_user()
    finding = make_finding(finder, lon=LON, lat=LAT, sensitivity=level, outline=to_db_geometry(OUTLINE))
    viewer = viewer_for(viewer_kind, finder, make_user, db)
    seen = visible_location(finding, viewer)
    assert sees_exact(finding, viewer) is VIEWER_TABLE[viewer_kind][level]
    if VIEWER_TABLE[viewer_kind][level]:
        assert_exact(seen)
        assert seen.outline is not None
        assert seen.outline.equals_exact(OUTLINE, 1e-9)
        assert seen.grid_ref == "SU 1023 6996"
    else:
        assert_square(seen)
        # What a generalised viewer sees is exactly the stored public position.
        assert (seen.lon, seen.lat) == pytest.approx(lon_lat(finding.location_public), abs=1e-12)


def test_the_table_covers_every_level() -> None:
    assert all(set(row) == set(Sensitivity) for row in VIEWER_TABLE.values())


@pytest.mark.parametrize(("viewer_kind", "level"), CASES, ids=[f"{v}-{lvl}" for v, lvl in CASES])
def test_downloads_are_exact_only_where_the_page_is_and_never_for_a_plain_member(
    viewer_kind: str, level: Sensitivity, make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    """Decision 0005, rule 8: a member's download carries a protected finding at its square."""
    finder = make_user()
    finding = make_finding(finder, lon=LON, lat=LAT, sensitivity=level)
    viewer = viewer_for(viewer_kind, finder, make_user, db)
    expected = VIEWER_TABLE[viewer_kind][level] and (viewer_kind != "member" or level is Sensitivity.OPEN)
    assert sensitivity.downloads_exact(finding, viewer) is expected


def test_unsaved_objects_with_no_ids_are_not_mistaken_for_finder_and_finding() -> None:
    # Neither has been flushed, so both ids are None. None == None must not
    # read as "this viewer is the finder".
    finding = Finding(
        public_id="NEW002",
        title="Unsaved",
        feature_class="round_barrow",
        sensitivity="restricted",
        location=db_point(LON, LAT),
    )
    stranger = User(handle="Stranger", display_name="Stranger", role="member")
    assert (finding.author_id, stranger.id) == (None, None)
    assert_square(visible_location(finding, stranger))
    stranger.id = 7
    assert_square(visible_location(finding, stranger))


def test_works_on_a_finding_that_has_not_been_saved_yet(make_user: MakeUser) -> None:
    author = make_user()
    finding = Finding(
        public_id="NEW001",
        author_id=author.id,
        title="Unsaved",
        feature_class="round_barrow",
        sensitivity="restricted",
        location=db_point(LON, LAT),
        grid_ref="SU 1023 6996",
    )
    assert_square(visible_location(finding, None))
    assert visible_location(finding, author).obscured is False


def test_an_unknown_sensitivity_value_is_an_error_not_an_open_door(make_finding: MakeFinding) -> None:
    finding = make_finding(lon=LON, lat=LAT)
    finding.sensitivity = "classified"
    with pytest.raises(ValueError, match="classified"):
        visible_location(finding, None)


def test_an_unknown_role_is_an_error_not_an_open_door(make_finding: MakeFinding, make_user: MakeUser) -> None:
    finding = make_finding(lon=LON, lat=LAT, sensitivity="restricted")
    wizard = make_user()
    wizard.role = "wizard"
    with pytest.raises(ValueError, match="wizard"):
        visible_location(finding, wizard)


# --------------------------------------------------------------------------
# The square
# --------------------------------------------------------------------------


def test_the_square_point_is_the_same_wherever_in_the_square_the_finding_is(
    make_finding: MakeFinding,
) -> None:
    square = gridref.parse_gridref("SU1069")
    seen = set()
    for fe, fn in [(1, 1), (999, 1), (500, 500), (1, 999), (999, 999)]:
        lon, lat = gridref.to_lonlat(square.system, square.easting + fe, square.northing + fn)
        assert gridref.square_1km(lon, lat).ref == "SU1069"
        location = visible_location(make_finding(lon=lon, lat=lat, sensitivity="protected"), None)
        seen.add((round(location.lon, 9), round(location.lat, 9), location.grid_ref, location.square))
    assert len(seen) == 1


def test_the_square_point_is_within_the_square_and_under_a_kilometre_away(make_finding: MakeFinding) -> None:
    finding = make_finding(lon=LON, lat=LAT, sensitivity="restricted")
    seen = visible_location(finding, None)
    assert gridref.parse_gridref("SU1069").polygon().contains(Point(seen.lon, seen.lat))
    _, _, distance = GEOD.inv(LON, LAT, seen.lon, seen.lat)
    assert 100 < distance < 708


@pytest.mark.parametrize(("east", "north"), [(411_000, 169_500), (410_500, 170_000), (411_000, 170_000)])
def test_a_finding_on_a_square_edge_lands_in_one_square_and_stays_there(
    make_finding: MakeFinding, east: int, north: int
) -> None:
    # A point on a kilometre line belongs to exactly one square, and the
    # public point is that square's centre, 500 m from every edge, so
    # generalising it again gives the same point.
    lon, lat = gridref.to_lonlat(gridref.GridSystem.OSGB, east, north)
    finding = make_finding(lon=lon, lat=lat, sensitivity="protected")
    seen = visible_location(finding, None)
    expected = gridref.square_1km(lon, lat).ref
    assert_square(seen, expected)
    assert public_point(seen.lon, seen.lat, PROTECTED) == pytest.approx((seen.lon, seen.lat), abs=1e-9)
    _, _, distance = GEOD.inv(lon, lat, seen.lon, seen.lat)
    assert distance < 708


def test_one_metre_either_side_of_a_square_edge_gives_neighbouring_squares(make_finding: MakeFinding) -> None:
    west = gridref.to_lonlat(gridref.GridSystem.OSGB, 410_999, 169_500)
    east = gridref.to_lonlat(gridref.GridSystem.OSGB, 411_001, 169_500)
    seen_west = visible_location(make_finding(lon=west[0], lat=west[1], sensitivity="restricted"), None)
    seen_east = visible_location(make_finding(lon=east[0], lat=east[1], sensitivity="restricted"), None)
    assert (seen_west.square, seen_east.square) == ("SU1069", "SU1169")
    _, _, distance = GEOD.inv(seen_west.lon, seen_west.lat, seen_east.lon, seen_east.lat)
    assert distance == pytest.approx(1000, abs=2)


@pytest.mark.parametrize("level", [PROTECTED, RESTRICTED])
def test_northern_ireland_uses_the_irish_grid_square(make_finding: MakeFinding, level: Sensitivity) -> None:
    finding = make_finding(lon=-5.9301, lat=54.5964, sensitivity=level)
    seen = visible_location(finding, None)
    assert (seen.obscured, seen.grid_ref, seen.square) == (True, "J 33 73", "J3373")
    assert (seen.lon, seen.lat) == pytest.approx(gridref.centre_of_square("J3373"), abs=1e-9)
    system, easting, northing = gridref.to_grid(seen.lon, seen.lat)
    assert system is gridref.GridSystem.IRISH
    assert (easting % 1000, northing % 1000) == pytest.approx((500, 500), abs=0.01)


def test_an_irish_grid_square_edge(make_finding: MakeFinding) -> None:
    lon, lat = gridref.to_lonlat(gridref.GridSystem.IRISH, 334_000, 373_500)
    seen = visible_location(make_finding(lon=lon, lat=lat, sensitivity="protected"), None)
    assert seen.square == gridref.square_1km(lon, lat).ref
    assert seen.square is not None
    assert seen.square.startswith("J")
    assert public_point(seen.lon, seen.lat, PROTECTED) == pytest.approx((seen.lon, seen.lat), abs=1e-9)


@pytest.mark.parametrize(
    ("lon", "lat", "letters"),
    [
        (-6.19, 55.29, "D"),  # Rathlin Island: Irish Grid
        (-5.70, 55.30, "NR"),  # Mull of Kintyre, across the North Channel: British grid
    ],
)
def test_each_side_of_the_north_channel_uses_its_own_grid(
    make_finding: MakeFinding, lon: float, lat: float, letters: str
) -> None:
    seen = visible_location(make_finding(lon=lon, lat=lat, sensitivity="restricted"), None)
    assert seen.square is not None
    assert seen.square.rstrip("0123456789") == letters


def test_a_generalised_finding_off_the_grids_fails_closed(make_finding: MakeFinding) -> None:
    # Saving it fails, because there is no square to publish in its place.
    with pytest.raises(DataIntegrityError, match="outside the British and Irish grids"):
        make_finding(lon=2.3522, lat=48.8566, sensitivity="protected", grid_ref="none")


def test_an_open_finding_off_the_grids_is_public_as_it_is(make_finding: MakeFinding) -> None:
    finding = make_finding(lon=2.3522, lat=48.8566, grid_ref="none")
    assert lon_lat(finding.location_public) == pytest.approx((2.3522, 48.8566), abs=1e-12)
    assert visible_location(finding, None).obscured is False


# --------------------------------------------------------------------------
# The stored public position
# --------------------------------------------------------------------------


def stored_public(db: Session, finding: Finding) -> tuple[float, float]:
    db.expire_all()
    row = db.scalar(select(Finding).where(Finding.id == finding.id))
    assert row is not None
    return lon_lat(row.location_public)


@pytest.mark.parametrize("level", list(Sensitivity))
def test_location_public_is_written_when_a_finding_is_saved(
    make_finding: MakeFinding, db: Session, level: Sensitivity
) -> None:
    finding = make_finding(lon=LON, lat=LAT, sensitivity=level)
    expected = (LON, LAT) if level is OPEN else gridref.centre_of_square("SU1069")
    assert stored_public(db, finding) == pytest.approx(expected, abs=1e-9)


def test_location_public_follows_the_level_and_the_location(
    make_finding: MakeFinding, make_user: MakeUser, db: Session
) -> None:
    moderator = make_user("moderator")
    finding = make_finding(lon=LON, lat=LAT)
    assert stored_public(db, finding) == pytest.approx((LON, LAT), abs=1e-9)

    change_sensitivity(db, finding, moderator, RESTRICTED)
    db.commit()
    assert stored_public(db, finding) == pytest.approx(gridref.centre_of_square("SU1069"), abs=1e-9)

    # Moving it moves the public square too.
    moved = gridref.to_lonlat(gridref.GridSystem.OSGB, 411_500, 169_500)
    finding = db.get(Finding, finding.id)
    assert finding is not None
    finding.location = db_point(*moved)
    db.commit()
    assert stored_public(db, finding) == pytest.approx(gridref.centre_of_square("SU1169"), abs=1e-9)

    change_sensitivity(db, finding, moderator, OPEN)
    db.commit()
    assert stored_public(db, finding) == pytest.approx(moved, abs=1e-9)


def test_location_public_is_rewritten_when_sensitivity_is_set_directly(
    make_finding: MakeFinding, db: Session
) -> None:
    # The ORM writes it on every save, not only through change_sensitivity.
    finding = make_finding(lon=LON, lat=LAT)
    finding.sensitivity = "protected"
    db.commit()
    assert stored_public(db, finding) == pytest.approx(gridref.centre_of_square("SU1069"), abs=1e-9)


def test_a_save_that_touches_neither_level_nor_location_keeps_location_public(
    make_finding: MakeFinding, db: Session
) -> None:
    finding = make_finding(lon=LON, lat=LAT, sensitivity="protected")
    before = stored_public(db, finding)
    finding = db.get(Finding, finding.id)
    assert finding is not None
    finding.title = "Renamed"
    db.commit()
    assert stored_public(db, finding) == before


def test_a_bulk_update_that_would_leave_location_public_stale_is_refused(
    make_finding: MakeFinding, db: Session
) -> None:
    # A Core UPDATE skips the ORM listener. The database trigger refuses the
    # two changes that would expose or misreport a position.
    finding = make_finding(lon=LON, lat=LAT)
    with pytest.raises(IntegrityError, match="location_public_mismatch"):
        db.execute(update(Finding).where(Finding.id == finding.id).values(sensitivity="restricted"))
    db.rollback()

    protected = make_finding(lon=LON, lat=LAT, sensitivity="protected")
    moved = db_point(LON + 0.01, LAT)
    with pytest.raises(IntegrityError, match="location_public_mismatch"):
        db.execute(update(Finding).where(Finding.id == protected.id).values(sensitivity="open"))
    db.rollback()
    open_finding = make_finding(lon=LON, lat=LAT)
    with pytest.raises(IntegrityError, match="location_public_mismatch"):
        db.execute(update(Finding).where(Finding.id == open_finding.id).values(location=moved))
    db.rollback()


def test_a_bulk_update_that_changes_both_columns_together_is_allowed(
    make_finding: MakeFinding, db: Session
) -> None:
    finding = make_finding(lon=LON, lat=LAT)
    centre = db_point(*gridref.centre_of_square("SU1069"))
    db.execute(
        update(Finding)
        .where(Finding.id == finding.id)
        .values(sensitivity="restricted", location_public=centre)
    )
    db.commit()
    assert stored_public(db, finding) == pytest.approx(gridref.centre_of_square("SU1069"), abs=1e-9)


# --------------------------------------------------------------------------
# Default level
# --------------------------------------------------------------------------


@pytest.mark.parametrize("feature_class", list(FeatureClass))
def test_default_level_comes_from_the_feature_class(feature_class: FeatureClass) -> None:
    protected = {"round_barrow", "long_barrow", "ritual", "settlement"}
    expected = PROTECTED if feature_class.value in protected else OPEN
    assert default_sensitivity(feature_class) is expected


@pytest.mark.parametrize(
    ("feature_class", "expected"), [("round_barrow", "protected"), ("enclosure", "open")]
)
def test_a_new_finding_with_no_level_gets_its_class_default(
    db: Session, make_user: MakeUser, feature_class: str, expected: str
) -> None:
    finding = Finding(
        public_id=f"DEF{feature_class[:3].upper()}",
        author_id=make_user().id,
        title="No level given",
        feature_class=feature_class,
        location=db_point(LON, LAT),
    )
    db.add(finding)
    db.commit()
    assert finding.sensitivity == expected
    assert finding.location_public is not None


def test_default_sensitivity_refuses_an_unknown_class() -> None:
    with pytest.raises(ValueError, match="castle_in_the_air"):
        default_sensitivity("castle_in_the_air")


# --------------------------------------------------------------------------
# Who may raise and who may lower
# --------------------------------------------------------------------------

RAISES = [(OPEN, PROTECTED), (OPEN, RESTRICTED), (PROTECTED, RESTRICTED)]
LOWERS = [(PROTECTED, OPEN), (RESTRICTED, OPEN), (RESTRICTED, PROTECTED)]

MAY_RAISE = {"finder", "trusted", "expert", "moderator", "admin"}
MAY_LOWER = {"moderator", "admin"}
ACTORS = [*VIEWER_TABLE]


@pytest.mark.parametrize("actor_kind", ACTORS)
@pytest.mark.parametrize(("before", "after"), RAISES + LOWERS)
def test_who_may_change_a_level(
    actor_kind: str,
    before: Sensitivity,
    after: Sensitivity,
    make_user: MakeUser,
    make_finding: MakeFinding,
    db: Session,
) -> None:
    finder = make_user()
    finding = make_finding(finder, lon=LON, lat=LAT, sensitivity=before)
    actor = viewer_for(actor_kind, finder, make_user, db)
    allowed_set = MAY_RAISE if (before, after) in RAISES else MAY_LOWER
    allowed = actor_kind in allowed_set
    assert may_change_sensitivity(finding, actor, after) is allowed
    if actor is None:
        return
    if allowed:
        change_sensitivity(db, finding, actor, after)
        db.commit()
        assert finding.sensitivity == after.value
    else:
        with pytest.raises(ForbiddenError) as caught:
            change_sensitivity(db, finding, actor, after)
        assert caught.value.code == "sensitivity_change_forbidden"
        db.rollback()
        db.refresh(finding)
        assert finding.sensitivity == before.value


def test_setting_the_same_level_is_a_no_op_for_anyone_who_may_raise(
    make_user: MakeUser, make_finding: MakeFinding, db: Session
) -> None:
    finder = make_user()
    finding = make_finding(finder, sensitivity="protected")
    assert may_change_sensitivity(finding, finder, PROTECTED) is True
    assert may_change_sensitivity(finding, make_user(), PROTECTED) is False
    change_sensitivity(db, finding, finder, PROTECTED)
    assert finding.sensitivity == "protected"


def test_the_raise_and_lower_rules_are_one_table() -> None:
    assert sensitivity.MAY_LOWER_ROLES < sensitivity.MAY_RAISE_ROLES


# --------------------------------------------------------------------------
# The position that is safe to copy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", list(Sensitivity))
def test_square_centre_is_the_same_whatever_the_sensitivity(
    make_finding: MakeFinding, level: Sensitivity
) -> None:
    finding = make_finding(lon=LON, lat=LAT, sensitivity=level)
    centre = square_centre(finding)
    assert centre == pytest.approx(gridref.centre_of_square("SU1069"), abs=1e-9)
    finding.sensitivity = "restricted"
    public = visible_location(finding, None)
    assert centre == pytest.approx((public.lon, public.lat), abs=1e-12)


def test_square_centre_is_none_off_the_grids(make_finding: MakeFinding) -> None:
    assert square_centre(make_finding(lon=2.3522, lat=48.8566, grid_ref="none")) is None


# --------------------------------------------------------------------------
# Starting level and class changes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "feature_class", "requested", "expected"),
    [
        ("member", "round_barrow", None, PROTECTED),
        ("member", "round_barrow", OPEN, PROTECTED),
        ("member", "round_barrow", "restricted", RESTRICTED),
        ("trusted", "round_barrow", OPEN, PROTECTED),
        ("moderator", "round_barrow", OPEN, OPEN),
        ("admin", "round_barrow", OPEN, OPEN),
        ("member", "enclosure", OPEN, OPEN),
        ("member", "enclosure", PROTECTED, PROTECTED),
    ],
)
def test_a_finding_starts_at_the_higher_of_its_class_default_and_the_request(
    make_user: MakeUser, role: str, feature_class: str, requested: Sensitivity | None, expected: Sensitivity
) -> None:
    assert starting_sensitivity(feature_class, requested, make_user(role)) is expected


def test_a_signed_out_actor_cannot_lower_the_starting_level() -> None:
    assert starting_sensitivity("round_barrow", OPEN, None) is PROTECTED


@pytest.mark.parametrize(
    ("current", "old", "new", "expected"),
    [
        (OPEN, "enclosure", "round_barrow", PROTECTED),
        (RESTRICTED, "enclosure", "round_barrow", RESTRICTED),
        (PROTECTED, "round_barrow", "enclosure", PROTECTED),
        # A moderator lowered this barrow. Moving it to another protected class keeps that.
        (OPEN, "round_barrow", "long_barrow", OPEN),
        (OPEN, "enclosure", "field_system", OPEN),
    ],
)
def test_a_class_change_raises_the_level_and_never_lowers_it(
    current: Sensitivity, old: str, new: str, expected: Sensitivity
) -> None:
    assert level_after_class_change(current, old, new) is expected


def test_saving_a_class_change_raises_the_level_and_the_public_position(
    make_finding: MakeFinding, db: Session
) -> None:
    finding = make_finding(lon=LON, lat=LAT, feature_class=FeatureClass.ENCLOSURE)
    assert finding.sensitivity == "open"
    finding = db.get(Finding, finding.id)
    assert finding is not None
    finding.feature_class = FeatureClass.ROUND_BARROW.value
    db.commit()
    assert finding.sensitivity == "protected"
    assert stored_public(db, finding) == pytest.approx(gridref.centre_of_square("SU1069"), abs=1e-9)
