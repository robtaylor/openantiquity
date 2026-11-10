"""Mentions: places a finding was talked about, such as a video, an article, a podcast or a paper.

A finding has at most one mention per canonical address (`services.unfurl`).
Adding one bumps the finding's `mention_count` and records `mention_added`,
which tells everyone following the finding except whoever added it. Everyone
who has helped with a finding follows it, the finder included, so they are
the people told. A mention found by the channel scan has no member against it
and no actor, so every follower is told.

A mention is not evidence. Nothing here touches the confidence engine, and a
mention never moves a finding's tier, state or score.

A removed mention keeps its row with `deleted_at` set. It disappears from
every list, and because the row still holds the address, neither the scan
nor anyone else can add that address to that finding again.

Nothing here returns a position. The recent feed returns findings, and the
schema gives each one the position its viewer may see through
`schemas.findings.location_out`.

Services flush and never commit.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldclub.errors import ConflictError, ForbiddenError, NotFoundError
from fieldclub.models import Finding, Mention, User
from fieldclub.schemas.common import int_from_cursor, paginate
from fieldclub.services import activity, findings, unfurl
from fieldclub.vocab import ActivityKind, FindingState, MentionKind

logger = logging.getLogger(__name__)

NOTE_MAX = 1000


class MentionNotFoundError(NotFoundError):
    code = "mention_not_found"
    message = "There's no such mention."


class MentionExistsError(ConflictError):
    code = "mention_exists"
    message = "That's already mentioned on this finding."


class MentionRemovedError(ConflictError):
    code = "mention_removed"
    message = "That mention was removed from this finding, so it can't be added again."


class MentionForbiddenError(ForbiddenError):
    code = "mention_forbidden"
    message = "Only the person who added a mention, or a moderator, can remove it."


@dataclass(frozen=True)
class Draft:
    """A mention ready to store: where it is, what it is, and what is known about it."""

    address: unfurl.Address
    kind: MentionKind
    metadata: unfurl.Metadata
    start_seconds: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class Preview:
    address: unfurl.Address
    status: unfurl.FetchStatus
    metadata: unfurl.Metadata


def preview(url: str) -> Preview:
    """What a mention of `url` would show, fetched now or from the cache. Nothing is stored."""
    address = unfurl.canonical(url)
    fetched = unfurl.unfurl(address)
    return Preview(address, fetched.status, fetched.metadata)


def _existing(db: Session, finding: Finding, canonical_url: str) -> Mention | None:
    return db.scalar(
        select(Mention).where(Mention.finding_id == finding.id, Mention.canonical_url == canonical_url)
    )


def _refuse_existing(found: Mention | None) -> None:
    if found is None:
        return
    if found.deleted_at is not None:
        raise MentionRemovedError()
    raise MentionExistsError(details={"mention_id": found.id})


def _insert(
    db: Session, finding: Finding, user: User | None, draft: Draft, auto_detected: bool
) -> Mention | None:
    """Store a mention and tell people, or return None when the finding already has that address."""
    meta = draft.metadata
    new_id = db.scalar(
        insert(Mention)
        .values(
            finding_id=finding.id,
            user_id=user.id if user is not None else None,
            kind=draft.kind.value,
            url=draft.address.url,
            canonical_url=draft.address.canonical_url,
            provider=draft.address.provider,
            title=meta.title,
            author_name=meta.author_name,
            thumbnail_url=meta.thumbnail_url,
            published_at=meta.published_at,
            start_seconds=draft.start_seconds,
            note=draft.note,
            auto_detected=auto_detected,
        )
        .on_conflict_do_nothing(index_elements=["finding_id", "canonical_url"])
        .returning(Mention.id)
    )
    if new_id is None:
        return None
    db.execute(
        update(Finding).where(Finding.id == finding.id).values(mention_count=Finding.mention_count + 1)
    )
    if user is not None:
        # Anyone who contributes to a finding follows it. They are the actor, so they aren't told.
        findings.follow(db, user, finding)
    activity.record(
        db, ActivityKind.MENTION_ADDED, user, finding, data={"mention_id": new_id, "kind": draft.kind.value}
    )
    db.refresh(finding, ["mention_count"])
    mention = db.get(Mention, new_id)
    assert mention is not None, "the mention just inserted has gone"
    return mention


def add(
    db: Session,
    finding: Finding,
    user: User,
    url: str,
    *,
    kind: MentionKind | None = None,
    start_seconds: int | None = None,
    note: str | None = None,
) -> Mention:
    """Add a mention a member found. The address is fetched for its title, unless that fails.

    Raises `MentionExistsError` or `MentionRemovedError` when the finding
    already has this address, before anything is fetched.
    """
    findings.check_open(finding)
    address = unfurl.canonical(url)
    _refuse_existing(_existing(db, finding, address.canonical_url))
    fetched = unfurl.unfurl(address)
    draft = Draft(
        address=address,
        kind=kind or address.kind,
        metadata=fetched.metadata,
        start_seconds=start_seconds if start_seconds is not None else address.start_seconds,
        note=note or None,
    )
    mention = _insert(db, finding, user, draft, auto_detected=False)
    if mention is None:
        # Someone else added it between the check and the insert.
        _refuse_existing(_existing(db, finding, address.canonical_url))
        raise AssertionError("the insert conflicted, so the mention must exist")
    return mention


def add_detected(db: Session, finding: Finding, draft: Draft) -> Mention | None:
    """Add a mention the channel scan found, or None when the finding already has it (or had it)."""
    if finding.hidden_at is not None or finding.state == FindingState.WITHDRAWN.value:
        return None
    return _insert(db, finding, None, draft, auto_detected=True)


def remove(db: Session, mention_id: int, user: User) -> Mention:
    """Remove a mention, by whoever added it or a moderator."""
    mention = db.get(Mention, mention_id)
    if mention is None or mention.deleted_at is not None:
        raise MentionNotFoundError()
    finding = db.get(Finding, mention.finding_id)
    assert finding is not None, "a mention always belongs to a finding"
    if finding.hidden_at is not None and not findings.may_see_hidden(finding, user):
        raise MentionNotFoundError()
    if not (user.has_id(mention.user_id) or findings.is_moderator(user)):
        raise MentionForbiddenError()
    mention.deleted_at = datetime.now(UTC)
    db.execute(
        update(Finding)
        .where(Finding.id == finding.id)
        .values(mention_count=func.greatest(Finding.mention_count - 1, 0))
    )
    db.flush()
    return mention


@dataclass(frozen=True)
class MentionPage:
    mentions: list[Mention]
    # Who added each, by id. Mentions from the channel scan have nobody.
    adders: dict[int, User]
    next_cursor: str | None
    # The finding each mention is on, and its finder, by id. Filled for the recent feed.
    finding_by_id: dict[int, Finding]
    finders: dict[int, User]


def _page(
    db: Session, rows: Sequence[Mention], limit: int, found: dict[int, Finding] | None = None
) -> MentionPage:
    items, next_cursor = paginate(rows, limit, lambda mention: [mention.id])
    adders = findings.users_by_id(db, (m.user_id for m in items if m.user_id is not None))
    on = found or {}
    authors = findings.users_by_id(db, (finding.author_id for finding in on.values()))
    return MentionPage(items, adders, next_cursor, on, authors)


def for_finding(db: Session, finding: Finding, *, limit: int, cursor: str | None = None) -> MentionPage:
    """A finding's mentions, newest first."""
    query = (
        select(Mention)
        .where(Mention.finding_id == finding.id, Mention.deleted_at.is_(None))
        .order_by(Mention.id.desc())
    )
    if cursor is not None:
        query = query.where(Mention.id < int_from_cursor(cursor))
    return _page(db, db.scalars(query.limit(limit + 1)).all(), limit)


def recent(db: Session, viewer: User | None, *, limit: int, cursor: str | None = None) -> MentionPage:
    """The newest mentions across the map, on findings this viewer may list."""
    query = (
        select(Mention, Finding)
        .join(Finding, Finding.id == Mention.finding_id)
        .where(
            Mention.deleted_at.is_(None),
            findings.not_hidden_clause(viewer),
            Finding.state != FindingState.WITHDRAWN.value,
        )
        .order_by(Mention.id.desc())
    )
    if cursor is not None:
        query = query.where(Mention.id < int_from_cursor(cursor))
    rows = db.execute(query.limit(limit + 1)).all()
    found = {finding.id: finding for _, finding in rows[:limit]}
    return _page(db, [mention for mention, _ in rows], limit, found)
