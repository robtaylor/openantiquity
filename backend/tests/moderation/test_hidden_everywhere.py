"""Hidden things leave every read route the app serves, whichever track built it.

The moderation track proved hiding against the routes on its own branch. The
feed, notifications, the event stream, profiles, mentions, investigations and
their exports were built beside it. This module builds one world holding one
of each hideable thing, hides each in turn, and reads every route
`tests/test_routes.py` sends here as every kind of viewer. Nobody but the
people the moderation rules let see a hidden thing may find it, by its text
or by its id in any field.

`WALKED` names the paths read for each route. A read route in `ROUTES` that
names `HIDDEN_EVERYWHERE` must be walked here, and one that isn't walked
must say in `ROUTES` why it holds nothing a moderator can hide, so a new read
route can't be left out by omission.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, Investigation, User
from fieldclub.services import feed, findings, investigations, mentions, moderation
from fieldclub.services.investigations import Need
from fieldclub.vocab import InvestigationItemKind, InvestigationRole, ReportTarget, Role
from tests.findings.support import add_desk_evidence, create
from tests.helpers import ClientFor, MakeUser
from tests.investigations.support import add, make
from tests.moderation.support import API, comment, photo

HIDDEN_EVERYWHERE = "tests.moderation.test_hidden_everywhere:test_hidden_content_leaves_every_read_route"
STREAM = "tests.moderation.test_hidden_everywhere:test_the_stream_announces_nothing_hidden"

VIEWERS = ("signed_out", "member", "trusted", "finder", "author", "editor", "moderator")
SECRET_FINDING = "Secret finding title"
SECRET_COMMENT = "Secret comment body"
SECRET_EVIDENCE = "Secret evidence title"
SECRET_MENTION = "Secret mention note"
SECRET_NOTEBOOK = "Secret notebook title"

# Who still sees each kind of thing once a moderator hides it, by viewer name.
STILL_SEEN_BY = {
    ReportTarget.FINDING: {"finder", "moderator"},
    ReportTarget.COMMENT: {"author", "moderator"},
    ReportTarget.EVIDENCE: {"moderator"},
    ReportTarget.MENTION: {"author", "moderator"},
    ReportTarget.PHOTO: {"author", "moderator"},
    ReportTarget.INVESTIGATION: {"author", "editor", "moderator"},
}
assert set(STILL_SEEN_BY) == moderation.HIDEABLE, "every hideable kind is walked"

# The paths read for each read route. `{pid}` is a finding with everything on it, `{gid}` the
# finding that is hidden, `{inv}` the investigation, `{photo}` the photo, `{author}` and
# `{finder}` handles.
F = "/findings/{pid}"
G = "/findings/{gid}"
INV = "/investigations/{inv}"
WALKED: dict[tuple[str, str], list[str]] = {
    ("GET", "/api/v1/auth/me"): ["/auth/me"],
    ("GET", "/api/v1/findings"): ["/findings", "/findings?format=geojson", "/findings?author={finder}"],
    ("GET", "/api/v1/findings/export"): ["/findings/export?format=geojson", "/findings/export?format=csv"],
    ("GET", "/api/v1/findings/{public_id}"): [F, G],
    ("GET", "/api/v1/findings/{public_id}/export"): [
        F + "/export?format=geojson",
        F + "/export?format=csv",
        G + "/export?format=geojson",
    ],
    ("GET", "/api/v1/findings/{public_id}/observations"): [F + "/observations", G + "/observations"],
    ("GET", "/api/v1/findings/{public_id}/comments"): [F + "/comments", G + "/comments"],
    ("GET", "/api/v1/findings/{public_id}/mentions"): [F + "/mentions", G + "/mentions"],
    ("GET", "/api/v1/findings/{public_id}/suggested-records"): [G + "/suggested-records"],
    ("GET", "/api/v1/mentions/recent"): ["/mentions/recent"],
    ("GET", "/api/v1/review/next"): ["/review/next"],
    ("GET", "/api/v1/review/tasks"): ["/review/tasks"],
    ("GET", "/api/v1/geo/search"): ["/geo/search?q={gid}", "/geo/search?q=Secret"],
    ("GET", "/api/v1/investigations"): [
        "/investigations",
        "/investigations?scope=mine",
        "/investigations?scope=invited",
        "/investigations?scope=unlisted",
    ],
    ("GET", "/api/v1/investigations/{public_id}"): [INV],
    ("GET", "/api/v1/investigations/{public_id}/items"): [INV + "/items"],
    ("GET", "/api/v1/investigations/{public_id}/members"): [INV + "/members"],
    ("GET", "/api/v1/investigations/{public_id}/export"): [
        INV + "/export?format=geojson",
        INV + "/export?format=csv",
        INV + "/export?format=html",
    ],
    ("GET", "/api/v1/users/{handle}"): ["/users/{author}", "/users/{finder}"],
    ("GET", "/api/v1/users/{handle}/findings"): ["/users/{finder}/findings"],
    ("GET", "/api/v1/users/{handle}/contributions"): [
        "/users/{author}/contributions",
        "/users/{author}/contributions?kind=comment",
        "/users/{author}/contributions?kind=evidence",
        "/users/{author}/contributions?kind=mention",
    ],
    ("GET", "/api/v1/users/{handle}/points"): ["/users/{finder}/points", "/users/{author}/points"],
    ("GET", "/api/v1/activity"): [
        "/activity",
        "/activity?finding={pid}",
        "/activity?finding={gid}",
        "/activity?investigation={inv}",
        "/activity?person={author}",
    ],
    ("GET", "/api/v1/notifications"): ["/notifications"],
    ("GET", "/api/v1/media/{media_id}"): ["/media/{photo}"],
    ("GET", "/api/v1/mod/media"): ["/mod/media"],
    ("GET", "/api/v1/mod/reports"): ["/mod/reports"],
    ("GET", "/api/v1/mod/actions"): ["/mod/actions"],
    ("GET", "/api/v1/mod/users/eligible"): ["/mod/users/eligible"],
}


@dataclass
class World:
    people: dict[str, User]
    finding: Finding
    hidden_finding: Finding
    investigation: Investigation
    # How each hideable thing is named to moderation, and the marks that give it away in a body.
    refs: dict[ReportTarget, str]
    texts: dict[ReportTarget, list[str]]
    ids: dict[ReportTarget, list[tuple[str, int]]]
    photo_id: int
    client: Callable[[str], TestClient]

    def paths(self) -> Iterator[str]:
        names = {
            "pid": self.finding.public_id,
            "gid": self.hidden_finding.public_id,
            "inv": self.investigation.public_id,
            "photo": str(self.photo_id),
            "author": self.people["author"].handle,
            "finder": self.people["finder"].handle,
        }
        for templates in WALKED.values():
            for template in templates:
                yield template.format(**names)


@pytest.fixture
def world(db: Session, make_user: MakeUser, app: FastAPI, client_for: ClientFor) -> World:
    people = {
        "finder": make_user(handle="Finder"),
        "author": make_user(handle="Author"),
        "member": make_user(handle="Member"),
        "trusted": make_user(Role.TRUSTED, handle="Trusted"),
        "editor": make_user(handle="Editor"),
        "moderator": make_user(Role.MODERATOR, handle="Moderator"),
    }
    finder, author, member = people["finder"], people["author"], people["member"]
    finding = create(db, finder, title="A finding everyone sees")
    hidden_finding = create(db, finder, title=SECRET_FINDING, lon=-1.85, lat=51.43)
    # The member follows both, so they are told of everything done on them.
    for found in (finding, hidden_finding):
        findings.follow(db, member, found)
    comment(db, hidden_finding, member, "A comment on the finding that is hidden.")
    said = comment(db, finding, author, SECRET_COMMENT)
    evidence, _ = add_desk_evidence(db, finding, author, title=SECRET_EVIDENCE)
    # Port 8443 is refused by the fetcher, so nothing is fetched.
    talked = mentions.add(
        db, finding, author, "https://www.wiltshire-gazette.example:8443/story", note=SECRET_MENTION
    )
    shown = photo(db, author, approved_by=people["trusted"])
    notebook = make(
        db,
        author,
        title=SECRET_NOTEBOOK,
        members={InvestigationRole.EDITOR: [people["editor"]]},
    )
    add(db, notebook, author, kind=InvestigationItemKind.FINDING, finding=finding.public_id)
    add(db, notebook, author, kind=InvestigationItemKind.FINDING, finding=hidden_finding.public_id)
    access = investigations.load(db, notebook.public_id, author, Need.OWN, lock=True)
    investigations.put_member(db, access, member, InvestigationRole.VIEWER)
    db.commit()
    clients = {name: client_for(app, user) for name, user in people.items()}
    clients["signed_out"] = client_for(app)
    return World(
        people=people,
        finding=finding,
        hidden_finding=hidden_finding,
        investigation=notebook,
        refs={
            ReportTarget.FINDING: hidden_finding.public_id,
            ReportTarget.COMMENT: str(said.id),
            ReportTarget.EVIDENCE: str(evidence.id),
            ReportTarget.MENTION: str(talked.id),
            ReportTarget.PHOTO: str(shown.id),
            ReportTarget.INVESTIGATION: notebook.public_id,
        },
        texts={
            ReportTarget.FINDING: [SECRET_FINDING, hidden_finding.public_id],
            ReportTarget.COMMENT: [SECRET_COMMENT],
            ReportTarget.EVIDENCE: [SECRET_EVIDENCE],
            ReportTarget.MENTION: [SECRET_MENTION],
            ReportTarget.PHOTO: [],
            ReportTarget.INVESTIGATION: [SECRET_NOTEBOOK, notebook.public_id],
        },
        ids={
            ReportTarget.FINDING: [],
            ReportTarget.COMMENT: [("comment", said.id)],
            ReportTarget.EVIDENCE: [("evidence", evidence.id)],
            ReportTarget.MENTION: [("mention", talked.id)],
            ReportTarget.PHOTO: [],
            ReportTarget.INVESTIGATION: [],
        },
        photo_id=shown.id,
        client=lambda name: clients[name],
    )


def _names(value: Any, kind: str, target_id: int) -> bool:
    """Whether a JSON value names the `kind` with this id anywhere: as `<kind>_id`, or as a kind and id."""
    if isinstance(value, dict):
        if value.get(f"{kind}_id") == target_id:
            return True
        if value.get("kind") == kind and value.get("id") == target_id:
            return True
        return any(_names(item, kind, target_id) for item in value.values())
    if isinstance(value, list):
        return any(_names(item, kind, target_id) for item in value)
    return False


def shows(world: World, kind: ReportTarget, path: str, response: Any) -> bool:
    """Whether the response gives the hidden thing away."""
    if kind is ReportTarget.PHOTO and path == f"/media/{world.photo_id}":
        return response.status_code == 200
    if any(text in response.text for text in world.texts[kind]):
        return True
    if "json" not in response.headers.get("content-type", ""):
        return False
    body = response.json()
    return any(_names(body, name, target_id) for name, target_id in world.ids[kind])


def what_shows(world: World, kind: ReportTarget, viewer: str) -> set[str]:
    client = world.client(viewer)
    return {path for path in world.paths() if shows(world, kind, path, client.get(API + path))}


@pytest.mark.parametrize("kind", sorted(moderation.HIDEABLE))
def test_hidden_content_leaves_every_read_route(world: World, db: Session, kind: ReportTarget) -> None:
    # Before it is hidden, the walk finds it, so a miss afterwards means something.
    for viewer in ("signed_out", "member"):
        assert what_shows(world, kind, viewer), (kind, viewer, "the walk should find it before hiding")
    moderation.set_hidden(
        db, kind, world.refs[kind], world.people["moderator"], hidden=True, reason="Breaks the terms."
    )
    db.commit()
    for viewer in VIEWERS:
        if viewer not in STILL_SEEN_BY[kind]:
            assert what_shows(world, kind, viewer) == set(), (kind, viewer)
    for viewer in STILL_SEEN_BY[kind] - {"moderator"}:
        assert what_shows(world, kind, viewer), (kind, viewer, "those who may still see it lose nothing")


def test_the_routes_sent_here_are_the_routes_walked() -> None:
    from tests.test_routes import ROUTES

    sent = {key for key, expect in ROUTES.items() if expect.hidden_test == HIDDEN_EVERYWHERE}
    assert sent == set(WALKED)


@pytest.mark.parametrize("kind", sorted(moderation.HIDEABLE - {ReportTarget.PHOTO}))
def test_the_stream_announces_nothing_hidden(world: World, db: Session, kind: ReportTarget) -> None:
    """The stream announces only what a signed-out visitor's feed lists (`feed.public_event`)."""
    events = list(db.scalars(select(Activity.id).order_by(Activity.id)))
    before = {event for event in events if feed.public_event(db, event) is not None}
    moderation.set_hidden(
        db, kind, world.refs[kind], world.people["moderator"], hidden=True, reason="Breaks the terms."
    )
    db.commit()
    after = {event for event in events if feed.public_event(db, event) is not None}
    assert after < before, kind


def test_profile_counts_leave_hidden_contributions_out(world: World, db: Session) -> None:
    def counts(viewer: str) -> dict[str, int]:
        return world.client(viewer).get(f"{API}/users/{world.people['author'].handle}").json()["counts"]

    before = counts("member")
    assert (before["comments"], before["evidence"], before["mentions"]) == (1, 1, 1)
    for kind in (ReportTarget.COMMENT, ReportTarget.EVIDENCE, ReportTarget.MENTION):
        moderation.set_hidden(
            db, kind, world.refs[kind], world.people["moderator"], hidden=True, reason="Breaks the terms."
        )
    db.commit()
    for viewer in ("signed_out", "member", "finder"):
        after = counts(viewer)
        assert (after["comments"], after["evidence"], after["mentions"]) == (0, 0, 0), viewer
    own = counts("author")
    # The author still sees their own hidden comment and mention, as on the finding's page.
    assert (own["comments"], own["evidence"], own["mentions"]) == (1, 0, 1)
