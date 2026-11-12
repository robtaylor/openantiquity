"""Unique constraints, checks and foreign keys hold in the database itself."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from shapely.geometry import MultiPolygon, Point, Polygon, box
from sqlalchemy import func, insert, inspect, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DataError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.orm import Session

from fieldclub.models import (
    Activity,
    AdminArea,
    AuthIdentity,
    Comment,
    Evidence,
    EvidenceVote,
    Finding,
    Follow,
    IngestRun,
    Investigation,
    InvestigationItem,
    InvestigationMember,
    MagicLink,
    Media,
    Mention,
    Notification,
    Observation,
    Place,
    Record,
    Report,
    ReputationEvent,
    Source,
    SquareSurvey,
    User,
    UserSession,
    WatchChannel,
)
from fieldclub.models.common import db_point, to_db_geometry
from tests.helpers import MakeFinding, MakeUser

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
POINT = db_point(-1.8542, 51.4286)
SQUARE = to_db_geometry(box(-1.86, 51.42, -1.85, 51.43))


def expect_violation(db: Session, *objects: Any, match: str) -> None:
    """Adding `objects` and flushing must break the constraint whose name contains `match`."""
    db.add_all(objects)
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    db.rollback()
    assert match in str(caught.value), f"expected {match} in: {caught.value}"


@pytest.fixture
def source(db: Session) -> Source:
    row = Source(
        key="test-source",
        name="Test source",
        publisher="Tests",
        licence="OGL v3.0",
        attribution="Test data",
        category="monument",
        access="bulk",
        reuse="open",
    )
    db.add(row)
    db.commit()
    return row


def make_record(source: Source, external_id: str = "A1", **columns: Any) -> Record:
    return Record(
        source_key=source.key,
        external_id=external_id,
        name=columns.pop("name", "Bowl barrow on Overton Hill"),
        category=columns.pop("category", "monument"),
        geom=columns.pop("geom", POINT),
        centroid=columns.pop("centroid", POINT),
        ingested_at=NOW,
        **columns,
    )


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------

# The columns docs/ARCHITECTURE.md lists for the people and records tables,
# plus the `id` and `created_at` every table has. A column added to a model, or
# dropped from one, has to be changed in the contract too.
CONTRACT_COLUMNS: dict[type, set[str]] = {
    User: {
        "id",
        "created_at",
        "handle",
        "display_name",
        "email",
        "email_verified_at",
        "avatar_url",
        "age_band",
        "terms_accepted_at",
        "role",
        "reputation",
        "bio",
        "settings",
        "last_seen_at",
        "banned_at",
        "deleted_at",
    },
    AuthIdentity: {"id", "created_at", "user_id", "provider", "subject", "email"},
    UserSession: {
        "id",
        "created_at",
        "user_id",
        "token_hash",
        "expires_at",
        "last_used_at",
        "user_agent",
        "ip_hash",
    },
    MagicLink: {
        "id",
        "created_at",
        "email",
        "token_hash",
        "user_id",
        "expires_at",
        "used_at",
        "browser_hash",
    },
    ReputationEvent: {"id", "created_at", "user_id", "delta", "reason", "finding_id"},
    Source: {
        "key",
        "created_at",
        "name",
        "publisher",
        "licence",
        "licence_url",
        "attribution",
        "licence_label",
        "credit",
        "reuse",
        "homepage",
        "coverage",
        "category",
        "access",
        "record_count",
        "last_ingest_at",
        "enabled",
    },
    Record: {
        "id",
        "created_at",
        "source_key",
        "external_id",
        "name",
        "summary",
        "category",
        "record_type",
        "monument_types",
        "periods",
        "geom",
        "centroid",
        "precision_m",
        "url",
        "raw",
        "source_updated_at",
        "ingested_at",
        "search",
    },
    IngestRun: {"id", "created_at", "source_key", "started_at", "finished_at", "status", "stats", "error"},
    Place: {"id", "created_at", "name", "kind", "district", "county", "nation", "geom", "rank", "source"},
    AdminArea: {"id", "created_at", "kind", "code", "name", "geom"},
}


@pytest.mark.parametrize("model", CONTRACT_COLUMNS, ids=lambda model: model.__tablename__)
def test_people_and_records_tables_have_exactly_the_contract_columns(model: type) -> None:
    assert set(model.__table__.columns.keys()) == CONTRACT_COLUMNS[model]


def test_the_database_has_exactly_the_columns_the_models_declare(db: Session, database: Engine) -> None:
    from fieldclub.db import Base

    inspector = inspect(database)
    for table in Base.metadata.sorted_tables:
        in_database = {column["name"] for column in inspector.get_columns(table.name)}
        assert in_database == set(table.columns.keys()), table.name


def test_there_is_no_trace_of_guest_accounts_in_the_schema(db: Session) -> None:
    assert "is_guest" not in User.__table__.columns
    role_check = db.scalar(
        text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_users_role_valid'")
    )
    assert role_check is not None
    assert "guest" not in role_check
    for role in ("member", "trusted", "expert", "moderator", "admin"):
        assert f"'{role}'" in role_check


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


def test_user_handle_is_unique_whatever_the_case(db: Session, make_user: MakeUser) -> None:
    make_user(handle="QuietBarrow42")
    expect_violation(db, User(handle="quietbarrow42", display_name="Copy"), match="uq_users_handle")


def test_user_email_is_unique_whatever_the_case(db: Session, make_user: MakeUser) -> None:
    make_user(email="Digger@example.org")
    expect_violation(
        db, User(handle="Other", display_name="Other", email="digger@EXAMPLE.org"), match="uq_users_email"
    )


def test_many_users_may_have_no_email(make_user: MakeUser) -> None:
    assert make_user().email is None
    assert make_user().email is None


def test_handle_lookup_ignores_case(db: Session, make_user: MakeUser) -> None:
    user = make_user(handle="MossyCairn7")
    assert db.scalar(select(User.id).where(User.handle == "mossycairn7")) == user.id


def test_user_defaults(db: Session) -> None:
    user = User(handle="Fresh", display_name="Fresh")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert (user.role, user.reputation) == ("member", 0.0)
    assert user.created_at.tzinfo is not None
    assert (user.banned_at, user.deleted_at, user.avatar_url) == (None, None, None)
    assert (user.is_banned, user.is_deleted) == (False, False)


def test_a_user_inserted_without_a_role_is_a_member(db: Session) -> None:
    # The server default, for anything that writes the table without the model.
    db.execute(text("INSERT INTO users (handle, display_name) VALUES ('Raw', 'Raw')"))
    db.commit()
    assert db.scalar(select(User.role).where(User.handle == "Raw")) == "member"


@pytest.mark.parametrize("role", ["wizard", "guest"])
def test_user_role_must_be_known(db: Session, role: str) -> None:
    expect_violation(db, User(handle="Odd", display_name="Odd", role=role), match="role_valid")


def test_avatar_and_deletion_round_trip(db: Session, make_user: MakeUser) -> None:
    user = make_user(avatar_url="https://example.org/a.png", deleted_at=NOW)
    db.refresh(user)
    assert (user.avatar_url, user.deleted_at, user.is_deleted) == ("https://example.org/a.png", NOW, True)


def test_auth_identity_keeps_the_email_the_provider_asserted(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    db.add(AuthIdentity(user_id=user.id, provider="google", subject="1", email="Rob@Example.org"))
    db.add(AuthIdentity(user_id=user.id, provider="osm", subject="2"))
    db.commit()
    by_email = db.scalar(select(AuthIdentity.provider).where(AuthIdentity.email == "rob@example.org"))
    assert by_email == "google", "the address is compared without regard to case"
    assert db.scalar(select(AuthIdentity.email).where(AuthIdentity.provider == "osm")) is None


def test_auth_identity_is_unique_per_provider_and_subject(db: Session, make_user: MakeUser) -> None:
    first, second = make_user(), make_user()
    db.add(AuthIdentity(user_id=first.id, provider="google", subject="123"))
    db.add(AuthIdentity(user_id=first.id, provider="osm", subject="123"))
    db.commit()
    expect_violation(
        db,
        AuthIdentity(user_id=second.id, provider="google", subject="123"),
        match="uq_auth_identities_provider_subject",
    )


def test_session_token_hash_is_unique(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    db.add(UserSession(user_id=user.id, token_hash="abc", expires_at=NOW))
    db.commit()
    expect_violation(
        db, UserSession(user_id=user.id, token_hash="abc", expires_at=NOW), match="uq_sessions_token_hash"
    )


def test_magic_link_token_hash_is_unique(db: Session) -> None:
    db.add(MagicLink(email="a@example.org", token_hash="abc", expires_at=NOW))
    db.commit()
    expect_violation(
        db,
        MagicLink(email="b@example.org", token_hash="abc", expires_at=NOW),
        match="uq_magic_links_token_hash",
    )


def test_deleting_a_user_removes_their_sessions(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    db.add(UserSession(user_id=user.id, token_hash="abc", expires_at=NOW))
    db.commit()
    db.delete(user)
    db.commit()
    assert db.scalar(select(func.count()).select_from(UserSession)) == 0


def test_reputation_event_round_trip(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> None:
    user = make_user()
    finding = make_finding(user)
    db.add(ReputationEvent(user_id=user.id, delta=2, reason="finding_seen", finding_id=finding.id))
    db.commit()
    assert db.scalar(select(func.sum(ReputationEvent.delta))) == 2


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


def test_finding_defaults(make_finding: MakeFinding, db: Session) -> None:
    finding = make_finding()
    db.refresh(finding)
    assert (finding.tier, finding.state, finding.sensitivity, finding.period) == (
        "spotted",
        "open",
        "open",
        "unknown",
    )
    assert finding.confidence == 10
    assert finding.assessment == {}
    assert (
        finding.observation_count,
        finding.evidence_count,
        finding.comment_count,
        finding.mention_count,
    ) == (
        0,
        0,
        0,
        0,
    )
    assert finding.updated_at.tzinfo is not None
    assert finding.hidden_at is None


def test_finding_public_id_is_unique(db: Session, make_finding: MakeFinding, make_user: MakeUser) -> None:
    first = make_finding(public_id="ABC123")
    clash = Finding(
        public_id="ABC123",
        author_id=first.author_id,
        title="Another",
        feature_class="enclosure",
        location=POINT,
    )
    expect_violation(db, clash, match="uq_findings_public_id")


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("feature_class", "spaceship", "feature_class_valid"),
        ("community_class", "spaceship", "community_class_valid"),
        ("period", "jurassic", "period_valid"),
        ("sensitivity", "secret", "sensitivity_valid"),
        ("tier", "legendary", "tier_valid"),
        ("state", "lost", "state_valid"),
        ("state_reason", "boredom", "state_reason_valid"),
        ("nation", "france", "nation_valid"),
        ("confidence", 101, "confidence_range"),
        ("confidence", -1, "confidence_range"),
    ],
)
def test_finding_checks(db: Session, make_user: MakeUser, column: str, value: Any, constraint: str) -> None:
    # A Core insert skips the ORM, which refuses an unknown class or level
    # before the database is asked. This tests the database's own checks.
    author = make_user()
    columns = {"feature_class": "enclosure", "sensitivity": "open", column: value}
    with pytest.raises(IntegrityError, match=constraint):
        db.execute(
            insert(Finding).values(
                public_id="CHK001",
                author_id=author.id,
                title="Check",
                location=POINT,
                location_public=POINT,
                **columns,
            )
        )
    db.rollback()


def test_finding_needs_an_author_that_exists(db: Session) -> None:
    orphan = Finding(
        public_id="ORPHAN", author_id=999_999, title="Orphan", feature_class="moat", location=POINT
    )
    expect_violation(db, orphan, match="fk_findings_author_id_users")


@pytest.mark.parametrize("column", ["location", "location_public"])
def test_finding_locations_must_be_points(db: Session, make_user: MakeUser, column: str) -> None:
    author = make_user()
    values = {"location": POINT, "location_public": POINT, column: SQUARE}
    with pytest.raises((DataError, InternalError, ProgrammingError)):
        db.execute(
            insert(Finding).values(
                public_id="NOTPNT", author_id=author.id, title="Bad", feature_class="moat", **values
            )
        )
    db.rollback()


def test_finding_location_public_is_required(db: Session, make_user: MakeUser) -> None:
    author = make_user()
    with pytest.raises(IntegrityError, match="location_public"):
        db.execute(
            insert(Finding).values(
                public_id="NOPUB", author_id=author.id, title="Bad", feature_class="moat", location=POINT
            )
        )
    db.rollback()


def test_the_orm_refuses_a_finding_whose_location_is_not_a_point(db: Session, make_user: MakeUser) -> None:
    author = make_user()
    db.add(
        Finding(public_id="NOTPNT", author_id=author.id, title="Bad", feature_class="moat", location=SQUARE)
    )
    with pytest.raises(AssertionError, match="non-point location"):
        db.flush()
    db.rollback()


def test_finding_outline_can_be_any_geometry(db: Session, make_finding: MakeFinding) -> None:
    finding = make_finding(outline=SQUARE)
    kind = db.scalar(select(func.ST_GeometryType(Finding.outline)).where(Finding.id == finding.id))
    assert kind == "ST_Polygon"
    assert db.scalar(select(func.ST_SRID(Finding.location)).where(Finding.id == finding.id)) == 4326


def test_updated_at_moves_when_a_finding_changes(db: Session, make_finding: MakeFinding) -> None:
    finding = make_finding(updated_at=NOW - timedelta(days=30))
    finding.title = "Renamed"
    db.commit()
    db.refresh(finding)
    assert finding.updated_at > NOW - timedelta(days=1)


def test_one_observation_per_person_per_finding(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding, watcher = make_finding(), make_user()
    db.add(Observation(finding_id=finding.id, user_id=watcher.id, visible="yes", role_at_answer="member"))
    db.commit()
    expect_violation(
        db,
        Observation(finding_id=finding.id, user_id=watcher.id, visible="no", role_at_answer="member"),
        match="uq_observations_finding_id_user_id",
    )


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("visible", "maybe", "visible_valid"),
        ("feature_class", "spaceship", "feature_class_valid"),
        ("period", "jurassic", "period_valid"),
        ("explanation", "aliens", "explanation_valid"),
        ("role_at_answer", "overlord", "role_at_answer_valid"),
    ],
)
def test_observation_checks(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, column: str, value: str, constraint: str
) -> None:
    columns = {"visible": "yes", "role_at_answer": "member", column: value}
    observation = Observation(finding_id=make_finding().id, user_id=make_user().id, **columns)
    expect_violation(db, observation, match=constraint)


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("kind", "hunch", "kind_valid"),
        ("stance", "shrug", "stance_valid"),
        ("relation", "cousin", "relation_valid"),
        ("outcome", "maybe", "outcome_valid"),
    ],
)
def test_evidence_checks(
    db: Session, make_user: MakeUser, make_finding: MakeFinding, column: str, value: str, constraint: str
) -> None:
    columns = {"kind": "aerial", "stance": "supports", column: value}
    evidence = Evidence(finding_id=make_finding().id, user_id=make_user().id, **columns)
    expect_violation(db, evidence, match=constraint)


def test_evidence_vote_is_one_per_person_and_plus_or_minus_one(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding, voter = make_finding(), make_user()
    evidence = Evidence(finding_id=finding.id, user_id=finding.author_id, kind="historic_map")
    db.add(evidence)
    db.commit()
    assert evidence.stance == "supports"

    db.add(EvidenceVote(evidence_id=evidence.id, user_id=voter.id, value=1, role_at_vote="member"))
    db.commit()
    with pytest.raises(IntegrityError, match="pk_evidence_votes"):
        db.execute(
            insert(EvidenceVote).values(
                evidence_id=evidence.id, user_id=voter.id, value=-1, role_at_vote="member"
            )
        )
    db.rollback()
    other = make_user()
    expect_violation(
        db,
        EvidenceVote(evidence_id=evidence.id, user_id=other.id, value=2, role_at_vote="member"),
        match="value_valid",
    )
    expect_violation(
        db,
        EvidenceVote(evidence_id=evidence.id, user_id=other.id, value=0, role_at_vote="member"),
        match="value_valid",
    )


def test_mention_is_unique_per_finding_and_match_key(db: Session, make_finding: MakeFinding) -> None:
    first, second = make_finding(), make_finding()
    url = "https://www.youtube.com/watch?v=abc"
    db.add(Mention(finding_id=first.id, kind="video", url=url + "&t=10", canonical_url=url))
    db.add(Mention(finding_id=second.id, kind="video", url=url, canonical_url=url))
    db.commit()
    assert db.scalars(select(Mention.auto_detected)).all() == [False, False]
    expect_violation(
        db,
        Mention(finding_id=first.id, kind="video", url=url, canonical_url=url),
        match="uq_mentions_finding_id_match_key",
    )
    # A removal that doesn't block re-adding leaves the address free.
    db.execute(update(Mention).where(Mention.finding_id == first.id).values(deleted_at=func.now()))
    db.add(Mention(finding_id=first.id, kind="video", url=url, canonical_url=url))
    db.commit()
    expect_violation(
        db,
        Mention(finding_id=first.id, kind="hologram", url="https://x.example", canonical_url="x"),
        match="kind_valid",
    )


def test_follow_is_one_per_person_per_finding(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding, follower = make_finding(), make_user()
    db.add(Follow(user_id=follower.id, finding_id=finding.id))
    db.commit()
    with pytest.raises(IntegrityError, match="pk_follows"):
        db.execute(insert(Follow).values(user_id=follower.id, finding_id=finding.id))
    db.rollback()


def test_deleting_a_finding_removes_what_hangs_off_it(
    db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding, other = make_finding(), make_user()
    evidence = Evidence(finding_id=finding.id, user_id=other.id, kind="aerial")
    comment = Comment(finding_id=finding.id, user_id=other.id, body="Looks like a ring ditch to me.")
    db.add_all(
        [
            evidence,
            comment,
            Observation(finding_id=finding.id, user_id=other.id, visible="yes", role_at_answer="member"),
            Follow(user_id=other.id, finding_id=finding.id),
            Mention(
                finding_id=finding.id, kind="article", url="https://x.example/a", canonical_url="x.example/a"
            ),
            Notification(user_id=other.id, kind="tier_changed", finding_id=finding.id),
            Activity(kind="finding_created", finding_id=finding.id, actor_id=finding.author_id),
        ]
    )
    db.flush()
    db.add(EvidenceVote(evidence_id=evidence.id, user_id=finding.author_id, value=1, role_at_vote="member"))
    db.add(Comment(finding_id=finding.id, user_id=other.id, body="Agreed.", parent_id=comment.id))
    db.commit()

    db.delete(finding)
    db.commit()
    for model in (Evidence, EvidenceVote, Comment, Observation, Follow, Mention, Notification, Activity):
        assert db.scalar(select(func.count()).select_from(model)) == 0, model.__name__


def test_media_storage_key_is_unique(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    db.add(
        Media(user_id=user.id, storage_key="media/a.jpg", content_type="image/jpeg", bytes=10, sha256="aa")
    )
    db.commit()
    expect_violation(
        db,
        Media(user_id=user.id, storage_key="media/a.jpg", content_type="image/jpeg", bytes=10, sha256="bb"),
        match="uq_media_storage_key",
    )


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


def test_source_access_must_be_known(db: Session) -> None:
    source = Source(
        key="bad",
        name="Bad",
        publisher="P",
        licence="L",
        attribution="A",
        category="monument",
        access="carrier-pigeon",
        reuse="open",
    )
    expect_violation(db, source, match="access_valid")


def test_source_needs_licence_and_attribution(db: Session) -> None:
    source = Source(key="bare", name="Bare", publisher="P", category="monument", access="bulk", reuse="open")
    expect_violation(db, source, match="licence")


def source_with(**columns: Any) -> Source:
    values = {
        "key": "reuse-test",
        "name": "Reuse",
        "publisher": "P",
        "licence": "L",
        "attribution": "A",
        "category": "monument",
        "access": "bulk",
    }
    return Source(**{**values, **columns})


@pytest.mark.parametrize("reuse", ["open", "share_alike", "non_commercial", "link_only"])
def test_source_reuse_classes(db: Session, reuse: str) -> None:
    db.add(source_with(reuse=reuse))
    db.commit()
    assert db.scalar(select(Source.reuse)) == reuse


def test_source_reuse_is_required_and_must_be_known(db: Session) -> None:
    # No default: a source has to say what its licence allows.
    expect_violation(db, source_with(), match="reuse")
    expect_violation(db, source_with(reuse="commercial"), match="reuse_valid")


def test_record_is_unique_per_source_and_external_id(db: Session, source: Source) -> None:
    db.add(make_record(source, "A1"))
    db.add(make_record(source, "A2"))
    db.commit()
    expect_violation(db, make_record(source, "A1"), match="uq_records_source_key_external_id")


def test_record_category_must_be_known(db: Session, source: Source) -> None:
    expect_violation(db, make_record(source, category="rumour"), match="category_valid")


def test_record_centroid_cannot_be_empty(db: Session, source: Source) -> None:
    # An empty centroid would hide the record from every distance query.
    empty = to_db_geometry(Point())
    expect_violation(db, make_record(source, centroid=empty), match="centroid_not_empty")


def test_record_needs_a_source_that_exists(db: Session, source: Source) -> None:
    record = make_record(source)
    record.source_key = "no-such-source"
    expect_violation(db, record, match="fk_records_source_key_sources")


def test_record_search_vector_is_generated_and_weighted(db: Session, source: Source) -> None:
    db.add(
        make_record(
            source,
            "A1",
            name="Windmill Hill causewayed enclosure",
            record_type="Scheduled Monument",
            monument_types=["CAUSEWAYED ENCLOSURE", "ROUND BARROW"],
            summary="Neolithic enclosure with three concentric ditches.",
        )
    )
    db.add(
        make_record(source, "A2", name="Silbury Hill", summary="A barrow-like mound, the largest in Europe.")
    )
    db.commit()

    def search(words: str) -> list[str]:
        query = func.websearch_to_tsquery("english", words)
        return list(
            db.scalars(
                select(Record.external_id)
                .where(Record.search.op("@@")(query))
                .order_by(func.ts_rank(Record.search, query).desc())
            )
        )

    assert search("windmill") == ["A1"]
    assert search("barrows") == ["A1", "A2"], (
        "a type term outranks a mention in the summary, and plurals match"
    )
    assert search("scheduled monument") == ["A1"]
    assert search("ditches") == ["A1"]
    assert search("hillfort") == []


def test_record_search_vector_follows_updates(db: Session, source: Source) -> None:
    record = make_record(source, "A1", name="Unnamed mound")
    db.add(record)
    db.commit()
    record.name = "Adam's Grave long barrow"
    db.commit()
    hit = db.scalar(
        select(Record.id).where(Record.search.op("@@")(func.websearch_to_tsquery("english", "grave")))
    )
    assert hit == record.id


def test_record_search_is_not_loaded_unless_asked_for(db: Session, source: Source) -> None:
    db.add(make_record(source))
    db.commit()
    db.expire_all()
    record = db.scalars(select(Record)).one()
    assert "search" not in record.__dict__


def test_record_name_trigram_search(db: Session, source: Source) -> None:
    db.add(make_record(source, "A1", name="West Kennet Long Barrow"))
    db.add(make_record(source, "A2", name="Durrington Walls"))
    db.commit()
    best = db.scalars(
        select(Record.external_id).order_by(func.similarity(Record.name, "west kennett long barow").desc())
    ).first()
    assert best == "A1"


def test_deleting_a_record_keeps_evidence_that_cited_it(
    db: Session, source: Source, make_finding: MakeFinding
) -> None:
    record = make_record(source)
    db.add(record)
    db.flush()
    finding = make_finding()
    evidence = Evidence(
        finding_id=finding.id,
        user_id=finding.author_id,
        kind="record_link",
        record_id=record.id,
        relation="same_as",
    )
    db.add(evidence)
    db.commit()

    db.delete(record)
    db.commit()
    db.refresh(evidence)
    assert evidence.record_id is None


def test_deleting_a_source_removes_its_records_and_runs(db: Session, source: Source) -> None:
    db.add(make_record(source))
    db.add(IngestRun(source_key=source.key, started_at=NOW, status="completed"))
    db.commit()
    db.delete(source)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Record)) == 0
    assert db.scalar(select(func.count()).select_from(IngestRun)) == 0


def test_ingest_run_status_must_be_known(db: Session, source: Source) -> None:
    expect_violation(
        db, IngestRun(source_key=source.key, started_at=NOW, status="napping"), match="status_valid"
    )


def test_admin_area_is_unique_per_kind_and_code(db: Session) -> None:
    shape = to_db_geometry(MultiPolygon([box(-2, 51, -1, 52)]))
    db.add(AdminArea(kind="nation", code="england", name="England", geom=shape))
    db.add(AdminArea(kind="county", code="england", name="A county with an odd code", geom=shape))
    db.commit()
    expect_violation(
        db,
        AdminArea(kind="nation", code="england", name="Again", geom=shape),
        match="uq_admin_areas_kind_code",
    )
    expect_violation(db, AdminArea(kind="parish", code="x", name="X", geom=shape), match="kind_valid")


def test_admin_area_geometry_is_stored_as_a_multipolygon(db: Session) -> None:
    # PostGIS promotes a lone polygon to a multipolygon, and refuses anything else.
    single = to_db_geometry(Polygon([(-2, 51), (-1, 51), (-1, 52), (-2, 51)]))
    db.add(AdminArea(kind="county", code="x", name="X", geom=single))
    db.commit()
    assert db.scalar(select(func.ST_GeometryType(AdminArea.geom))) == "ST_MultiPolygon"

    db.add(AdminArea(kind="county", code="y", name="Y", geom=POINT))
    with pytest.raises((DataError, InternalError, ProgrammingError)):
        db.flush()
    db.rollback()


def test_place_round_trip(db: Session) -> None:
    db.add(
        Place(
            name="Avebury",
            kind="village",
            county="Wiltshire",
            nation="england",
            geom=POINT,
            rank=3,
            source="os",
        )
    )
    db.commit()
    assert db.scalar(select(Place.name).where(Place.name.op("%")("Avebry"))) == "Avebury"
    expect_violation(
        db,
        Place(name="X", kind="town", nation="narnia", geom=POINT, rank=1, source="os"),
        match="nation_valid",
    )


# --------------------------------------------------------------------------
# Collaboration
# --------------------------------------------------------------------------


def test_investigation_public_id_is_unique_and_private_by_default(db: Session, make_user: MakeUser) -> None:
    owner = make_user()
    first = Investigation(public_id="INV001", owner_id=owner.id, title="Parish survey")
    db.add(first)
    db.commit()
    assert first.visibility == "private"
    expect_violation(
        db,
        Investigation(public_id="INV001", owner_id=owner.id, title="Clash"),
        match="uq_investigations_public_id",
    )
    expect_violation(
        db,
        Investigation(public_id="INV002", owner_id=owner.id, title="Odd", visibility="whispered"),
        match="visibility_valid",
    )


def test_investigation_members_and_items(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> None:
    owner, helper = make_user(), make_user()
    # Public, because a private investigation can't take a second member.
    investigation = Investigation(
        public_id="INV010", owner_id=owner.id, title="Ridgeway barrows", visibility="public"
    )
    db.add(investigation)
    db.flush()
    db.add(InvestigationMember(investigation_id=investigation.id, user_id=helper.id, role="editor"))
    db.add(
        InvestigationItem(
            investigation_id=investigation.id,
            kind="finding",
            finding_id=make_finding(owner).id,
            position=0,
            added_by=owner.id,
        )
    )
    db.commit()

    with pytest.raises(IntegrityError, match="pk_investigation_members"):
        db.execute(
            insert(InvestigationMember).values(
                investigation_id=investigation.id, user_id=helper.id, role="viewer"
            )
        )
    db.rollback()
    expect_violation(
        db,
        InvestigationMember(investigation_id=investigation.id, user_id=owner.id, role="boss"),
        match="role_valid",
    )
    expect_violation(
        db,
        InvestigationItem(investigation_id=investigation.id, kind="doodle", position=1, added_by=owner.id),
        match="kind_valid",
    )

    db.delete(investigation)
    db.commit()
    assert db.scalar(select(func.count()).select_from(InvestigationMember)) == 0
    assert db.scalar(select(func.count()).select_from(InvestigationItem)) == 0


def test_one_square_survey_per_person_per_square(db: Session, make_user: MakeUser) -> None:
    first, second = make_user(), make_user()
    db.add(SquareSurvey(user_id=first.id, square="SU1069", geom=SQUARE, result="nothing"))
    db.add(SquareSurvey(user_id=second.id, square="SU1069", geom=SQUARE, result="marked", findings_count=2))
    db.commit()
    expect_violation(
        db,
        SquareSurvey(user_id=first.id, square="SU1069", geom=SQUARE, result="skipped"),
        match="uq_square_surveys_user_id_square",
    )
    expect_violation(
        db, SquareSurvey(user_id=first.id, square="SU1070", geom=SQUARE, result="bored"), match="result_valid"
    )


def test_activity_kind_must_be_known(db: Session) -> None:
    expect_violation(db, Activity(kind="something_else"), match="kind_valid")


def test_report_defaults_to_open(db: Session, make_user: MakeUser) -> None:
    report = Report(reporter_id=make_user().id, target_kind="comment", target_id=1, reason="spam")
    db.add(report)
    db.commit()
    assert report.status == "open"
    expect_violation(
        db,
        Report(
            reporter_id=report.reporter_id, target_kind="comment", target_id=1, reason="spam", status="lost"
        ),
        match="status_valid",
    )


def test_watch_channel_is_unique_per_provider(db: Session) -> None:
    db.add(WatchChannel(provider="youtube", channel_id="UC123"))
    db.commit()
    expect_violation(
        db,
        WatchChannel(provider="youtube", channel_id="UC123"),
        match="uq_watch_channels_provider_channel_id",
    )


# --------------------------------------------------------------------------
# Added for the contract of 2026-11-10
# --------------------------------------------------------------------------


def test_age_band_and_terms_are_empty_until_the_welcome_sheet(db: Session) -> None:
    user = User(handle="Newcomer", display_name="Newcomer")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert (user.age_band, user.terms_accepted_at) == (None, None)


@pytest.mark.parametrize("band", ["16_17", "18_plus"])
def test_age_band_accepts_the_two_bands(db: Session, make_user: MakeUser, band: str) -> None:
    user = make_user(age_band=band, terms_accepted_at=NOW)
    db.refresh(user)
    assert (user.age_band, user.terms_accepted_at) == (band, NOW)


@pytest.mark.parametrize("band", ["under_16", "13_15", "18+", ""])
def test_age_band_must_be_known(db: Session, band: str) -> None:
    expect_violation(db, User(handle="Kid", display_name="Kid", age_band=band), match="age_band_valid")


def test_media_approval_round_trip_and_survives_the_approver(db: Session, make_user: MakeUser) -> None:
    uploader, approver = make_user(), make_user("moderator")
    media = Media(
        user_id=uploader.id, storage_key="media/x.jpg", content_type="image/jpeg", bytes=1, sha256="a"
    )
    db.add(media)
    db.commit()
    assert (media.approved_at, media.approved_by) == (None, None)
    media.approved_at, media.approved_by = NOW, approver.id
    db.commit()
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": approver.id})
    db.commit()
    db.refresh(media)
    assert (media.approved_at, media.approved_by) == (NOW, None)


def test_media_approver_must_exist(db: Session, make_user: MakeUser) -> None:
    media = Media(
        user_id=make_user().id,
        storage_key="media/y.jpg",
        content_type="image/jpeg",
        bytes=1,
        sha256="b",
        approved_by=999_999,
    )
    expect_violation(db, media, match="fk_media_approved_by_users")
