"""Adding, listing and removing mentions, and who is told."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, Mention, Notification, User
from fieldclub.services import findings, mentions, unfurl
from fieldclub.vocab import ActivityKind, EvidenceKind, FeatureClass, MentionKind, Visible
from tests.findings.support import add_desk_evidence, answer, create
from tests.helpers import ClientAs, MakeFinding, MakeUser, count, error_code
from tests.mentions.support import (
    API,
    ARTICLE_URL,
    YOUTUBE_URL,
    ip_of,
    serve,
    serve_article,
    serve_youtube_oembed,
)


def post(client: TestClient, finding: Finding, url: str, **body: object):
    return client.post(f"{API}/findings/{finding.public_id}/mentions", json={"url": url, **body})


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------


def test_preview_fetches_without_saving(
    client_as: ClientAs, make_user: MakeUser, db: Session, offline: respx.MockRouter
) -> None:
    serve_youtube_oembed()
    response = client_as(make_user()).post(
        f"{API}/mentions/preview", json={"url": "https://youtu.be/dQw4w9WgXcQ?t=95"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["canonical_url"] == YOUTUBE_URL
    assert body["kind"] == "video"
    assert body["provider"] == "youtube"
    assert body["start_seconds"] == 95
    assert body["fetch_status"] == "ok"
    assert body["author_name"] == "Barrow Walks"
    assert count(db, Mention) == 0


def test_a_failed_preview_still_answers(
    client_as: ClientAs, make_user: MakeUser, offline: respx.MockRouter
) -> None:
    serve("www.youtube.com", "/oembed", b"", "text/html", status=500)
    body = client_as(make_user()).post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL}).json()
    assert body["fetch_status"] == "failed"
    assert body["title"] is None
    assert body["canonical_url"] == YOUTUBE_URL


def test_a_preview_of_a_private_address_is_refused_quietly(
    client_as: ClientAs, make_user: MakeUser, offline: respx.MockRouter
) -> None:
    body = (
        client_as(make_user()).post(f"{API}/mentions/preview", json={"url": "http://169.254.169.254/"}).json()
    )
    assert body["fetch_status"] == "refused"
    assert offline.calls.call_count == 0


def test_preview_needs_a_contributor(client: TestClient, client_as: ClientAs, newcomer: User) -> None:
    assert client.post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL}).status_code == 401
    response = client_as(newcomer).post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL})
    assert error_code(response) == "onboarding_required"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://example.org/", "x" * 2001, ""])
def test_preview_refuses_what_isnt_an_address(client_as: ClientAs, make_user: MakeUser, url: str) -> None:
    response = client_as(make_user()).post(f"{API}/mentions/preview", json={"url": url})
    assert response.status_code == 422


@pytest.mark.usefixtures("limits_on")
def test_preview_is_rate_limited_hard(
    client_as: ClientAs, make_user: MakeUser, offline: respx.MockRouter
) -> None:
    serve_youtube_oembed()
    client = client_as(make_user())
    codes = [client.post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL}).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429


# --------------------------------------------------------------------------
# Adding
# --------------------------------------------------------------------------


def test_a_member_adds_a_mention(
    client_as: ClientAs,
    make_user: MakeUser,
    make_finding: MakeFinding,
    db: Session,
    offline: respx.MockRouter,
) -> None:
    serve_youtube_oembed()
    finding = make_finding()
    adder = make_user()
    response = post(client_as(adder), finding, "https://youtu.be/dQw4w9WgXcQ?t=95&si=x", note="From 1:35.")
    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://youtu.be/dQw4w9WgXcQ?t=95&si=x"
    assert body["canonical_url"] == YOUTUBE_URL
    assert body["start_seconds"] == 95
    assert body["title"] == "We found a henge on LIDAR — Avebury part 2"
    assert body["note"] == "From 1:35."
    assert body["auto_detected"] is False
    assert body["added_by"]["handle"] == adder.handle
    db.refresh(finding)
    assert finding.mention_count == 1


def test_a_chosen_kind_and_start_win(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, offline: respx.MockRouter
) -> None:
    serve_youtube_oembed()
    body = post(
        client_as(make_user()), make_finding(), YOUTUBE_URL + "&t=5", kind="broadcast", start_seconds=60
    )
    assert (body.json()["kind"], body.json()["start_seconds"]) == ("broadcast", 60)


def test_a_mention_is_saved_with_the_address_alone_when_the_fetch_fails(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, offline: respx.MockRouter
) -> None:
    respx.get(host=ip_of("www.wiltshire-gazette.example")).mock(side_effect=httpx.ConnectTimeout("slow"))
    response = post(client_as(make_user()), make_finding(), ARTICLE_URL)
    assert response.status_code == 201
    assert response.json()["title"] is None
    assert response.json()["canonical_url"] == ARTICLE_URL


def test_a_mention_of_an_address_we_wont_fetch_is_saved_unfetched(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, offline: respx.MockRouter
) -> None:
    response = post(
        client_as(make_user()), make_finding(), "https://www.wiltshire-gazette.example:8443/story"
    )
    assert response.status_code == 201
    assert offline.calls.call_count == 0


def test_the_same_thing_twice_is_refused_without_fetching_again(
    client_as: ClientAs,
    make_user: MakeUser,
    make_finding: MakeFinding,
    db: Session,
    offline: respx.MockRouter,
) -> None:
    route = serve_youtube_oembed()
    finding = make_finding()
    client = client_as(make_user())
    first = post(client, finding, YOUTUBE_URL)
    again = post(client_as(make_user()), finding, "https://www.youtube.com/shorts/dQw4w9WgXcQ?t=3")
    assert again.status_code == 409
    assert error_code(again) == "mention_exists"
    assert again.json()["error"]["details"] == {"mention_id": first.json()["id"]}
    assert route.call_count == 1
    db.refresh(finding)
    assert finding.mention_count == 1
    # Another finding may mention the same video.
    assert post(client, make_finding(), YOUTUBE_URL).status_code == 201


def test_mentions_need_a_contributor(
    client: TestClient, client_as: ClientAs, newcomer: User, make_finding: MakeFinding
) -> None:
    finding = make_finding()
    assert post(client, finding, YOUTUBE_URL).status_code == 401
    assert error_code(post(client_as(newcomer), finding, YOUTUBE_URL)) == "onboarding_required"


def test_input_sizes_are_checked(client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding) -> None:
    client, finding = client_as(make_user()), make_finding()
    assert post(client, finding, YOUTUBE_URL, note="x" * 1001).status_code == 422
    assert post(client, finding, YOUTUBE_URL, start_seconds=-1).status_code == 422
    assert post(client, finding, YOUTUBE_URL, start_seconds=10**9).status_code == 422
    assert post(client, finding, YOUTUBE_URL, kind="hologram").status_code == 422
    assert post(client, finding, YOUTUBE_URL, note="a\u0000b").status_code == 422
    assert error_code(post(client, finding, "javascript:alert(1)")) == "invalid_address"


def test_a_withdrawn_finding_takes_no_mentions(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding = make_finding(state="withdrawn")
    assert error_code(post(client_as(make_user()), finding, YOUTUBE_URL)) == "finding_withdrawn"


def test_a_hidden_finding_is_not_found(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding = make_finding(hidden_at=datetime(2026, 11, 1, tzinfo=UTC))
    client = client_as(make_user())
    assert error_code(post(client, finding, YOUTUBE_URL)) == "finding_not_found"
    assert error_code(client.get(f"{API}/findings/{finding.public_id}/mentions")) == "finding_not_found"


# --------------------------------------------------------------------------
# Who is told
# --------------------------------------------------------------------------


def test_the_finder_and_everyone_who_helped_are_told_once_and_the_adder_never(
    db: Session, make_user: MakeUser, offline: respx.MockRouter
) -> None:
    serve_youtube_oembed()
    finder = make_user(handle="Finder")
    observer, evidencer, commenter, adder, stranger = (
        make_user(handle=name) for name in ("Observer", "Evidencer", "Commenter", "Adder", "Stranger")
    )
    finding = create(db, finder, feature_class=FeatureClass.ENCLOSURE)
    answer(db, finding, observer, Visible.YES)
    add_desk_evidence(db, finding, evidencer, EvidenceKind.AERIAL)
    findings.add_comment(db, finding, commenter, "Nice.")
    # The adder has helped too, and still isn't told of their own mention.
    findings.add_comment(db, finding, adder, "I saw this in a video.")
    db.commit()
    before = {n.id for n in db.scalars(select(Notification))}

    mentions.add(db, findings.get_finding(db, finding.public_id, adder), adder, YOUTUBE_URL)
    db.commit()

    told = db.scalars(select(Notification).where(Notification.id.not_in(before))).all()
    assert sorted(n.user_id for n in told) == sorted(u.id for u in (finder, observer, evidencer, commenter))
    assert {n.kind for n in told} == {ActivityKind.MENTION_ADDED.value}
    assert {n.actor_id for n in told} == {adder.id}
    assert stranger.id not in {n.user_id for n in told}
    (event,) = db.scalars(select(Activity).where(Activity.kind == ActivityKind.MENTION_ADDED.value)).all()
    assert event.actor_id == adder.id
    assert event.data is not None
    assert event.data["kind"] == "video"


def test_a_mention_never_moves_the_ladder(
    db: Session, make_user: MakeUser, offline: respx.MockRouter
) -> None:
    serve_youtube_oembed()
    serve_article()
    finder = make_user()
    finding = create(db, finder)
    answer(db, finding, make_user(), Visible.YES)
    db.refresh(finding)
    before = (finding.tier, finding.state, finding.confidence, finding.assessment, finding.open_steps)
    changes = count(db, Activity)
    for url in (YOUTUBE_URL, ARTICLE_URL):
        mentions.add(db, finding, make_user(role="expert"), url)
        db.commit()
    db.refresh(finding)
    assert (finding.tier, finding.state, finding.confidence, finding.assessment, finding.open_steps) == before
    kinds = db.scalars(select(Activity.kind).where(Activity.id > changes)).all()
    assert kinds == [ActivityKind.MENTION_ADDED.value] * 2


# --------------------------------------------------------------------------
# Listing and removing
# --------------------------------------------------------------------------


def add_three(db: Session, finding: Finding, user: User) -> list[Mention]:
    added = [
        mentions.add(db, finding, user, f"https://www.wiltshire-gazette.example:8443/story-{n}")
        for n in range(3)
    ]
    db.commit()
    return added


def test_a_findings_mentions_are_listed_newest_first_in_pages(
    client: TestClient, db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding = make_finding()
    added = add_three(db, finding, make_user())
    first = client.get(f"{API}/findings/{finding.public_id}/mentions", params={"limit": 2}).json()
    assert [m["id"] for m in first["items"]] == [added[2].id, added[1].id]
    rest = client.get(
        f"{API}/findings/{finding.public_id}/mentions", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [m["id"] for m in rest["items"]] == [added[0].id]
    assert rest["next_cursor"] is None


def test_the_adder_removes_their_mention(
    client: TestClient, client_as: ClientAs, db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    adder = make_user()
    finding = make_finding()
    mention, *_ = add_three(db, finding, adder)
    assert error_code(client_as(make_user()).delete(f"{API}/mentions/{mention.id}")) == "mention_forbidden"
    assert client_as(adder).delete(f"{API}/mentions/{mention.id}").status_code == 204
    assert error_code(client_as(adder).delete(f"{API}/mentions/{mention.id}")) == "mention_not_found"
    listed = client.get(f"{API}/findings/{finding.public_id}/mentions").json()["items"]
    assert mention.id not in {m["id"] for m in listed}
    db.refresh(finding)
    assert finding.mention_count == 2
    # Removing your own mention blocks nothing: the adder can put it back.
    again = post(client_as(adder), finding, mention.url)
    assert again.status_code == 201
    assert again.json()["id"] != mention.id
    db.refresh(finding)
    assert finding.mention_count == 3


def test_adding_then_removing_a_mention_cant_bury_it(
    client_as: ClientAs,
    db: Session,
    make_user: MakeUser,
    make_finding: MakeFinding,
    offline: respx.MockRouter,
) -> None:
    serve_youtube_oembed()
    finding = make_finding()
    griefer = client_as(make_user())
    added = post(griefer, finding, YOUTUBE_URL)
    assert added.status_code == 201
    assert griefer.delete(f"{API}/mentions/{added.json()['id']}").status_code == 204
    # Another member adds the same video, written another way.
    again = post(client_as(make_user()), finding, "https://youtu.be/dQw4w9WgXcQ")
    assert again.status_code == 201
    listed = client_as(make_user()).get(f"{API}/findings/{finding.public_id}/mentions").json()["items"]
    assert [m["id"] for m in listed] == [again.json()["id"]]
    # And so can the channel scan, once a member's own removal is all there is.
    removed = db.get(Mention, added.json()["id"])
    assert removed is not None
    assert removed.removed_by is not None
    assert removed.blocks_readding is False


def test_a_moderators_removal_sticks(
    client_as: ClientAs,
    db: Session,
    make_user: MakeUser,
    make_finding: MakeFinding,
    offline: respx.MockRouter,
) -> None:
    serve_youtube_oembed()
    serve_article()
    finding = make_finding()
    moderator = make_user("moderator")
    added = post(client_as(make_user()), finding, YOUTUBE_URL)
    assert client_as(moderator).delete(f"{API}/mentions/{added.json()['id']}").status_code == 204
    for user in (make_user(), moderator):
        again = post(client_as(user), finding, "https://youtu.be/dQw4w9WgXcQ")
        assert error_code(again) == "mention_removed"
    draft = mentions.Draft(
        address=unfurl.canonical(YOUTUBE_URL), kind=MentionKind.VIDEO, metadata=unfurl.NOTHING
    )
    assert mentions.add_detected(db, finding, draft) is None
    # A moderator removing a mention they added themselves blocks nothing.
    own = post(client_as(moderator), finding, ARTICLE_URL)
    assert own.status_code == 201
    assert client_as(moderator).delete(f"{API}/mentions/{own.json()['id']}").status_code == 204
    assert post(client_as(make_user()), finding, ARTICLE_URL).status_code == 201


def test_a_moderator_removes_anyones_including_the_scans(
    client_as: ClientAs, db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finding = make_finding()
    mention, *_ = add_three(db, finding, make_user())
    found = mentions.add_detected(
        db,
        finding,
        mentions.Draft(
            address=unfurl.canonical(YOUTUBE_URL),
            kind=MentionKind.VIDEO,
            metadata=unfurl.NOTHING,
        ),
    )
    db.commit()
    assert found is not None
    assert error_code(client_as(make_user()).delete(f"{API}/mentions/{found.id}")) == "mention_forbidden"
    moderator = client_as(make_user("moderator"))
    assert moderator.delete(f"{API}/mentions/{found.id}").status_code == 204
    assert moderator.delete(f"{API}/mentions/{mention.id}").status_code == 204


def test_delete_needs_a_contributor(
    client: TestClient, db: Session, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    mention, *_ = add_three(db, make_finding(), make_user())
    assert client.delete(f"{API}/mentions/{mention.id}").status_code == 401
    assert client.delete(f"{API}/mentions/999999").status_code == 401
