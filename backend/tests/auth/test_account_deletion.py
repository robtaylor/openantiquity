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

import pytest
from shapely.geometry import box
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.auth import accounts, sessions
from fieldclub.auth.accounts import HandleGenerationError, delete_account
from fieldclub.db import Base
from fieldclub.models import (
    AuthIdentity,
    Comment,
    Evidence,
    Investigation,
    MagicLink,
    Media,
    Mention,
    Notification,
    Report,
    ReputationEvent,
    SquareSurvey,
    User,
)
from fieldclub.models.common import to_db_geometry
from fieldclub.services import activity, findings, investigations, media, mentions, moderation
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
# Refused and hidden photos keep their rows, without their files, so the image stays blocked.
BLOCKERS_STAY = "blockers stay"

# Every column that points at `users`, and what deleting the account does to its rows.
WHAT_DELETION_DOES: dict[tuple[str, str], str] = {
    ("auth_identities", "user_id"): GOES,
    ("sessions", "user_id"): GOES,
    ("magic_links", "user_id"): GOES,
    ("follows", "user_id"): GOES,
    ("notifications", "user_id"): GOES,
    # A notification someone else received about them stays, naming no one.
    ("notifications", "actor_id"): STAYS,
    # A photo is personal data: every file goes, and evidence keeps no photo. The row of a
    # refused or hidden photo stays, because it refuses the same image from anyone.
    ("media", "user_id"): BLOCKERS_STAY,
    ("media", "approved_by"): STAYS,
    ("media", "rejected_by"): STAYS,
    # Private investigations go, memberships and invitations go. A shared investigation
    # stays, passed to an editor, so no row names them as owner afterwards either.
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


def _count(db: Session, table: str, column: str, user: User) -> int:
    rows = Base.metadata.tables[table]
    return db.scalar(select(func.count()).select_from(rows).where(rows.c[column] == user.id)) or 0


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
    endorsed, _ = add_desk_evidence(db, theirs_elsewhere, other, EvidenceKind.AERIAL)
    findings.vote(db, endorsed.id, gone, 1)
    said = comment(db, theirs_elsewhere, gone, "Worth a look from the footpath.")
    talked = mentions.add(db, theirs_elsewhere, gone, "https://www.wiltshire-gazette.example:8443/story")
    shown = photo(db, gone, approved_by=moderator)
    waiting = photo(db, gone, data=jpeg(colour=(1, 2, 3)))
    refused = photo(db, gone, data=jpeg(colour=(4, 5, 6)))
    moderation.reject_photo(db, refused.id, moderator, "A person's face.")
    hidden = photo(db, gone, approved_by=moderator, data=jpeg(colour=(7, 8, 9)))
    moderation.set_hidden(db, ReportTarget.PHOTO, str(hidden.id), moderator, hidden=True, reason="Abusive.")
    # The person approved one of someone else's photos and refused another.
    moderation.approve_photo(db, photo(db, other, data=jpeg(colour=(10, 11, 12))).id, gone)
    moderation.reject_photo(db, photo(db, other, data=jpeg(colour=(13, 14, 15))).id, gone, "Blurred.")
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
    # No service lets a trusted member verify evidence or resolve a report, so these are set on the
    # rows: what matters here is what deletion does to them.
    endorsed.verified_by = gone.id
    about.resolved_by = gone.id
    db.add(ReputationEvent(user_id=gone.id, delta=1.0, reason="test", finding_id=finding.id))
    private = make(db, gone, Visibility.PRIVATE, title="Private notes")
    shared = make(db, gone, Visibility.PUBLIC, members={InvestigationRole.EDITOR: [other]})
    add(db, shared, gone, kind=InvestigationItemKind.FINDING, finding=finding.public_id)
    elsewhere = make(db, other, Visibility.UNLISTED)
    access = investigations.load(db, elsewhere.public_id, other, Need.OWN, lock=True)
    investigations.put_member(db, access, gone, InvestigationRole.VIEWER)
    activity.notify_invitation(db, other, gone, shared)
    db.add(Notification(user_id=gone.id, kind="tier_changed", finding_id=theirs_elsewhere.id))
    db.add(AuthIdentity(user_id=gone.id, provider="google", subject="leaving"))
    db.add(MagicLink(email="leaving@example.org", token_hash="leaving", user_id=gone.id, expires_at=NOW))
    sessions.create_session(db, gone)
    db.commit()
    blockers = {refused.id, hidden.id}
    stored = [shown.storage_key, waiting.storage_key, hidden.storage_key]
    assert all(media.media_storage().exists(key) for key in stored)
    # Every column the walk judges has something in it to lose, or keep.
    empty = [key for key in WHAT_DELETION_DOES if not _count(db, *key, gone)]
    assert empty == [], "give the person a row in each of these"

    files = delete_account(db, gone, now=NOW)
    db.commit()
    db.expire_all()
    # The files go only once the deletion has committed.
    assert set(stored) <= set(files)
    assert all(media.media_storage().exists(key) for key in stored)
    media.delete_files(files)
    assert not any(media.media_storage().exists(key) for key in stored)

    for (table, column), does in WHAT_DELETION_DOES.items():
        left = _count(db, table, column, gone)
        if does == GOES:
            assert left == 0, (table, column)
        elif does == STAYS:
            assert left > 0, (table, column)
        else:
            assert does == BLOCKERS_STAY, (table, column)
            assert set(db.scalars(select(Media.id).where(Media.user_id == gone.id))) == blockers

    # Personal data has gone: the photo is off the evidence, and the shared investigation has passed on.
    assert db.get(Evidence, evidence.id).media_id is None  # pyright: ignore[reportOptionalMemberAccess]
    assert db.get(Investigation, private.id) is None
    assert db.get(Investigation, shared.id).owner_id == other.id  # pyright: ignore[reportOptionalMemberAccess]
    # The public record stays, credited to the same row, now "Former member".
    assert db.get(Mention, talked.id).deleted_at is None  # pyright: ignore[reportOptionalMemberAccess]
    assert db.get(Comment, said.id).deleted_at is None  # pyright: ignore[reportOptionalMemberAccess]
    assert {r.id for r in db.scalars(select(Report))} >= {reported.id, about.id}
    # Someone else's notification of the invitation stays, and names no one.
    item = client_as(other).get("/api/v1/notifications").json()["items"]
    assert [entry["actor"] for entry in item if entry["kind"] == "investigation_invitation"] == [None]
    assert db.get(User, gone.id).display_name == "Former member"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.parametrize("decision", ["refuse", "hide"])
def test_a_refused_or_hidden_image_stays_blocked_after_its_uploader_leaves(
    db: Session, make_user: MakeUser, client_as: ClientAs, decision: str
) -> None:
    leaver = make_user(handle="Leaving")
    moderator = make_user(Role.MODERATOR, handle="Moderator")
    raw = jpeg(colour=(200, 10, 10))
    if decision == "refuse":
        blocked = photo(db, leaver, data=raw)
        moderation.reject_photo(db, blocked.id, moderator, "Abusive.")
    else:
        blocked = photo(db, leaver, approved_by=moderator, data=raw)
        moderation.set_hidden(
            db, ReportTarget.PHOTO, str(blocked.id), moderator, hidden=True, reason="Abusive."
        )
    db.commit()
    newcomer = make_user(handle="Newcomer")
    with pytest.raises(media.MediaBlockedError):
        media.upload(db, newcomer, raw)
    db.rollback()

    assert client_as(leaver).delete("/api/v1/auth/me").status_code == 204
    db.expire_all()

    assert not media.media_storage().exists(blocked.storage_key), "the file is personal data and goes"
    with pytest.raises(media.MediaBlockedError):
        media.upload(db, newcomer, raw)
    db.rollback()
    # The row is kept to block the image, and nobody can download it, not even a moderator.
    assert client_as(moderator).get(f"/api/v1/media/{blocked.id}").status_code == 404


def test_a_failed_deletion_leaves_every_photo_and_its_file(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaver = make_user(handle="Leaving")
    kept = photo(db, leaver)

    def no_handle(*_: object) -> None:
        raise HandleGenerationError()

    monkeypatch.setattr(accounts, "_anonymise_handle", no_handle)
    with pytest.raises(HandleGenerationError):
        delete_account(db, leaver)
    db.rollback()
    assert db.get(Media, kept.id) is not None
    assert media.media_storage().exists(kept.storage_key)
