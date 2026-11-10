"""An uploaded photo is shown to other people only once it is approved (Decision 0009)."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from fieldclub.models import Media, User
from fieldclub.services.media import (
    MediaApprovalForbiddenError,
    approve_media,
    may_approve_media,
    may_see_media,
)
from tests.helpers import MakeUser

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
_keys = itertools.count(1)


@pytest.fixture
def upload(db: Session, make_user: MakeUser) -> Media:
    media = Media(
        user_id=make_user().id,
        storage_key=f"media/{next(_keys)}.jpg",
        content_type="image/jpeg",
        bytes=1234,
        sha256="ab" * 32,
    )
    db.add(media)
    db.commit()
    return media


def uploader(db: Session, media: Media) -> User:
    user = db.get(User, media.user_id)
    assert user is not None
    return user


ROLES = ["member", "trusted", "expert", "moderator", "admin"]


def test_the_uploader_always_sees_their_photo(db: Session, upload: Media) -> None:
    assert upload.approved_at is None
    assert may_see_media(upload, uploader(db, upload)) is True


def test_nobody_else_sees_an_unapproved_photo(upload: Media, make_user: MakeUser) -> None:
    assert may_see_media(upload, None) is False
    assert may_see_media(upload, make_user("member")) is False


@pytest.mark.parametrize("role", ["trusted", "expert", "moderator", "admin"])
def test_those_who_approve_photos_see_the_queue(upload: Media, make_user: MakeUser, role: str) -> None:
    # Someone has to look at a photo to approve it.
    assert may_see_media(upload, make_user(role)) is True


@pytest.mark.parametrize("role", ROLES)
def test_everyone_sees_an_approved_photo(db: Session, upload: Media, make_user: MakeUser, role: str) -> None:
    approve_media(db, upload, make_user("moderator"), now=NOW)
    db.commit()
    assert upload.approved_at == NOW
    assert may_see_media(upload, None) is True
    assert may_see_media(upload, make_user(role)) is True


def test_a_banned_or_deleted_account_counts_as_signed_out(
    db: Session, upload: Media, make_user: MakeUser
) -> None:
    assert may_see_media(upload, make_user("moderator", banned_at=NOW)) is False
    assert may_see_media(upload, make_user("trusted", deleted_at=NOW)) is False
    owner = uploader(db, upload)
    owner.banned_at = NOW
    assert may_see_media(upload, owner) is False


@pytest.mark.parametrize(
    ("role", "allowed"),
    [("member", False), ("trusted", True), ("expert", True), ("moderator", True), ("admin", True)],
)
def test_who_may_approve(db: Session, upload: Media, make_user: MakeUser, role: str, allowed: bool) -> None:
    approver = make_user(role)
    assert may_approve_media(upload, approver) is allowed
    if allowed:
        approve_media(db, upload, approver, now=NOW)
        assert upload.approved_by == approver.id
    else:
        with pytest.raises(MediaApprovalForbiddenError) as caught:
            approve_media(db, upload, approver, now=NOW)
        assert caught.value.code == "media_approval_forbidden"
        assert upload.approved_at is None


def test_nobody_approves_their_own_photo(db: Session, make_user: MakeUser) -> None:
    moderator = make_user("moderator")
    media = Media(
        user_id=moderator.id, storage_key="media/own.jpg", content_type="image/jpeg", bytes=1, sha256="cd"
    )
    db.add(media)
    db.commit()
    assert may_approve_media(media, moderator) is False
    assert may_approve_media(media, None) is False
    assert may_approve_media(media, make_user("moderator", banned_at=NOW)) is False


def test_unsaved_objects_are_not_mistaken_for_the_uploader() -> None:
    media = Media(storage_key="media/new.jpg", content_type="image/jpeg", bytes=1, sha256="ef")
    stranger = User(handle="Stranger", display_name="Stranger", role="member")
    assert (media.user_id, stranger.id) == (None, None)
    assert may_see_media(media, stranger) is False


def test_deleting_the_approver_keeps_the_approval(db: Session, upload: Media, make_user: MakeUser) -> None:
    approver = make_user("trusted")
    approve_media(db, upload, approver, now=NOW)
    db.commit()
    db.delete(approver)
    db.commit()
    db.refresh(upload)
    assert (upload.approved_at, upload.approved_by) == (NOW, None)
    assert may_see_media(upload, None) is True
