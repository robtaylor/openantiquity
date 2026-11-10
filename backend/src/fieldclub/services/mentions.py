"""Mentions: places a finding was talked about, such as a video, an article, a podcast or a paper.

A finding has at most one live mention per address, compared by
`unfurl.Address.match_key`.
Adding one bumps the finding's `mention_count` and records `mention_added`,
which tells everyone following the finding except whoever added it. Everyone
who has helped with a finding follows it, the finder included, so they are
the people told. A mention found by the channel scan has no member against it
and no actor, so every follower is told.

A mention is not evidence. Nothing here touches the confidence engine, and a
mention never moves a finding's tier, state or score.

A removed mention keeps its row with `deleted_at` and `removed_by` set, and
disappears from every list. Someone removing their own mention blocks
nothing: anyone may add that address again, and so may the scan. A moderator
removing someone else's mention, or one the scan found, sets
`blocks_readding`, and then neither a member nor the scan can add that
address to that finding again. Otherwise anyone could bury a finding's real
video by adding it and removing it.

Adding fetches the address, which can take seconds. `add` takes a
`before_fetch` callback, and the router ends its transaction there, so no
database connection is held while a stranger's server answers.

Nothing here returns a position. The recent feed returns findings, and the
schema gives each one the position its viewer may see through
`schemas.findings.location_out`.

Services flush and never commit.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldclub.errors import ConflictError, ForbiddenError, NotFoundError
from fieldclub.models import Finding, Mention, User
from fieldclub.models.findings import MENTION_HOLDS_ADDRESS
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
    message = "A moderator removed that from this finding, so it can't be added again."


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


def _holding(db: Session, finding: Finding, address: unfurl.Address) -> Mention | None:
    """The mention that holds this address on the finding: a live one, or a removal that blocks it."""
    return db.scalar(
        select(Mention).where(
            Mention.finding_id == finding.id,
            Mention.match_key == address.match_key,
            Mention.deleted_at.is_(None) | Mention.blocks_readding,
        )
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
            match_key=draft.address.match_key,
            provider=draft.address.provider,
            title=meta.title,
            author_name=meta.author_name,
            thumbnail_url=meta.thumbnail_url,
            published_at=meta.published_at,
            start_seconds=draft.start_seconds,
            note=draft.note,
            auto_detected=auto_detected,
        )
        .on_conflict_do_nothing(
            index_elements=["finding_id", "match_key"], index_where=text(MENTION_HOLDS_ADDRESS)
        )
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


def _clean_note(note: str | None) -> str | None:
    """A note, or None when it has nothing visible in it."""
    if note is None:
        return None
    visible = "".join(char for char in note if unicodedata.category(char) != "Cf")
    return note.strip() if visible.strip() else None


def add(
    db: Session,
    finding: Finding,
    user: User,
    url: str,
    *,
    kind: MentionKind | None = None,
    start_seconds: int | None = None,
    note: str | None = None,
    before_fetch: Callable[[], None] | None = None,
) -> Mention:
    """Add a mention a member found. The address is fetched for its title, unless that fails.

    Raises `MentionExistsError` or `MentionRemovedError` when the finding
    already has this address, before anything is fetched. `before_fetch` is
    called just before the fetch, for the caller to end its transaction. The
    finding is read again after it, since it may have changed meanwhile.
    """
    findings.check_open(finding)
    address = unfurl.canonical(url)
    _refuse_existing(_holding(db, finding, address))
    if before_fetch is not None:
        before_fetch()
    fetched = unfurl.unfurl(address)
    db.refresh(finding)
    if finding.hidden_at is not None and not findings.may_see_hidden(finding, user):
        raise findings.FindingNotFoundError()
    findings.check_open(finding)
    draft = Draft(
        address=address,
        kind=kind or address.kind,
        metadata=fetched.metadata,
        start_seconds=start_seconds if start_seconds is not None else address.start_seconds,
        note=_clean_note(note),
    )
    mention = _insert(db, finding, user, draft, auto_detected=False)
    if mention is None:
        # Someone else added it between the check and the insert.
        _refuse_existing(_holding(db, finding, address))
        raise AssertionError("the insert conflicted, so the mention must exist")
    return mention


def add_detected(db: Session, finding: Finding, draft: Draft) -> Mention | None:
    """Add a mention the channel scan found, or None when the finding has it or a moderator removed it."""
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
    own = user.has_id(mention.user_id)
    if not (own or findings.is_moderator(user)):
        raise MentionForbiddenError()
    mention.deleted_at = datetime.now(UTC)
    mention.removed_by = user.id
    # A moderator's removal of a mention that isn't theirs sticks.
    mention.blocks_readding = not own
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
