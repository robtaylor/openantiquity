"""What deleting an account does to every table that names a person.

Personal data goes; the public record of contributions stays, credited to
"Former member" (Decisions 0002 and 0009). `WHAT_DELETION_DOES` says, for
every column that points at `users`, which of the two it is. A new column
that points at `users` fails the walk until it is added there, so nobody can
add a table holding something of a person's without deciding what deletion
does to it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shapely.geometry import box
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.auth.accounts import delete_account
from fieldclub.db import Base
from fieldclub.models import (
    Comment,
    Evidence,
    Finding,
    Follow,
    Investigation,
    InvestigationItem,
    InvestigationMember,
    Media,
    Mention,
    Notification,
    Observation,
    Report,
    SquareSurvey,
    User,
)
from fieldclub.models.common import to_db_geometry
from fieldclub.services import activity, investigations, media, mentions, moderation
from fieldclub.services.investigations import Need
from fieldclub.vocab import (
    EvidenceKind,
    InvestigationItemKind,
    InvestigationRole,
    ReportReason,
    ReportTarget,
    Role,
    Visibility,
)
from tests.findings.support import add_desk_evidence, answer, create
from tests.helpers import ClientAs, MakeUser
from tests.investigations.support import add, make
from tests.moderation.support import comment, jpeg, photo

GOES = "goes"
STAYS = "stays"

# Every column that points at `users`, and what deleting the account does to its rows.
WHAT_DELETION_DOES: dict[tuple[str, str], str] = {
    ("auth_identities", "user_id"): GOES,
    ("sessions", "user_id"): GOES,
    ("magic_links", "user_id"): GOES,
    ("follows", "user_id"): GOES,
    ("notifications", "user_id"): GOES,
    # A notification someone else received about them stays, naming no one.
    ("notifications", "actor_id"): STAYS,
    # A photo is personal data: the file and the row go, and evidence keeps no photo.
    ("media", "user_id"): GOES,
    ("media", "approved_by"): STAYS,
    ("media", "rejected_by"): STAYS,
    # Private investigations go, shared ones pass to an editor, memberships and invitations go.
    ("investigations", "owner_id"): GOES,
    ("investigation_members", "user_id"): GOES,
    ("investigation_items", "added_by"): STAYS,
    ("findings", "author_id"): STAYS,
    ("observations", "user_id"): STAYS,
    ("evidence", "user_id"): STAYS,
    ("evidence", "verified_by"): STAYS,
    ("evidence_votes", "user_id"): STAYS,
    ("comments", "user_id"): STAYS,
    ("mentions", "user_id"): STAYS,
    ("square_surveys", "user_id"): STAYS,
    ("activity", "actor_id"): STAYS,
    # Points set the weight of what they did, and nobody else reads the items.
    ("reputation_events", "user_id"): STAYS,
    # What moderation keeps: reports they made and resolved, and the log.
    ("reports", "reporter_id"): STAYS,
    ("reports", "resolved_by"): STAYS,
    ("moderation_actions", "actor_id"): STAYS,
}

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


def test_every_column_that_names_a_person_has_a_decision() -> None:
    found = {
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if any(fk.column.table.name == "users" for fk in column.foreign_keys)
    }
    assert found == set(WHAT_DELETION_DOES), "say what deleting an account does to each new user column"


def test_deleting_takes_personal_data_and_leaves_the_public_record(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    gone = make_user(Role.TRUSTED, handle="Leaving")
    other = make_user(handle="Staying")
    moderator = make_user(Role.MODERATOR, handle="Moderator")
    finding = create(db, gone)
    theirs_elsewhere = create(db, other, lon=-1.85, lat=51.43)
    answer(db, theirs_elsewhere, gone)
    evidence, _ = add_desk_evidence(db, theirs_elsewhere, gone, EvidenceKind.AERIAL)
    said = comment(db, theirs_elsewhere, gone, "Worth a look from the footpath.")
    talked = mentions.add(db, theirs_elsewhere, gone, "https://www.wiltshire-gazette.example:8443/story")
    shown = photo(db, gone, approved_by=moderator)
    waiting = photo(db, gone, data=jpeg(colour=(1, 2, 3)))
    evidence.media_id = shown.id
    db.add(
        SquareSurvey(
            user_id=gone.id,
            square="SU1069",
            geom=to_db_geometry(box(-1.86, 51.42, -1.84, 51.43)),
            result="nothing",
        )
    )
    spam = str(comment(db, finding, other).id)
    reported = moderation.create_report(db, gone, ReportTarget.COMMENT, spam, ReportReason.SPAM, "Spam")
    about = moderation.create_report(db, other, ReportTarget.USER, gone.handle, ReportReason.ABUSE, None)
    private = make(db, gone, Visibility.PRIVATE, title="Private notes")
    shared = make(db, gone, Visibility.PUBLIC, members={InvestigationRole.EDITOR: [other]})
    add(db, shared, gone, kind=InvestigationItemKind.FINDING, finding=finding.public_id)
    elsewhere = make(db, other, Visibility.UNLISTED)
    access = investigations.load(db, elsewhere.public_id, other, Need.OWN, lock=True)
    investigations.put_member(db, access, gone, InvestigationRole.VIEWER)
    activity.notify_invitation(db, other, gone, shared)
    db.commit()
    stored = [shown.storage_key, waiting.storage_key]
    assert all(media.media_storage().exists(key) for key in stored)

    delete_account(db, gone, now=NOW)
    db.commit()
    db.expire_all()

    # Personal data has gone: photos, file and row, and every membership and invitation.
    assert db.scalars(select(Media.id).where(Media.user_id == gone.id)).all() == []
    assert not any(media.media_storage().exists(key) for key in stored)
    assert db.get(Evidence, evidence.id).media_id is None  # pyright: ignore[reportOptionalMemberAccess]
    assert db.get(Investigation, private.id) is None
    assert (
        db.scalars(select(InvestigationMember.user_id).where(InvestigationMember.user_id == gone.id)).all()
        == []
    )
    assert db.get(Investigation, shared.id).owner_id == other.id  # pyright: ignore[reportOptionalMemberAccess]
    assert db.scalars(select(Follow.user_id).where(Follow.user_id == gone.id)).all() == []

    # The public record stays, credited to the same row, now "Former member".
    for model, column in (
        (Finding, Finding.author_id),
        (Observation, Observation.user_id),
        (Evidence, Evidence.user_id),
        (Comment, Comment.user_id),
        (Mention, Mention.user_id),
        (SquareSurvey, SquareSurvey.user_id),
        (InvestigationItem, InvestigationItem.added_by),
    ):
        assert db.scalar(select(func.count()).select_from(model).where(column == gone.id)), model.__name__
    assert db.get(Mention, talked.id).deleted_at is None  # pyright: ignore[reportOptionalMemberAccess]
    assert db.get(Comment, said.id).deleted_at is None  # pyright: ignore[reportOptionalMemberAccess]
    assert {r.id for r in db.scalars(select(Report))} >= {reported.id, about.id}
    # Someone else's notification of the invitation stays, and names no one.
    item = client_as(other).get("/api/v1/notifications").json()["items"]
    assert [entry["actor"] for entry in item if entry["kind"] == "investigation_invitation"] == [None]
    assert db.get(User, gone.id).display_name == "Former member"  # pyright: ignore[reportOptionalMemberAccess]
    assert (
        db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == gone.id)) == 0
    )
