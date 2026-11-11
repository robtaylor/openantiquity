"""`POST /media`, `GET /media/{id}` and the approval queue (Decision 0009, Decision 0005)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import ExifTags, Image
from sqlalchemy.orm import Session

from fieldclub.config import get_settings
from fieldclub.models import Media, User
from fieldclub.services import media
from fieldclub.vocab import Role
from tests.findings.support import create
from tests.helpers import ClientAs, ClientFor, MakeUser, count, error_code
from tests.media.support import phone_photo
from tests.moderation.support import API, REASON, jpeg, log_entries


def upload(client: TestClient, data: bytes, content_type: str = "image/jpeg"):
    return client.post(f"{API}/media", content=data, headers={"Content-Type": content_type})


@pytest.fixture
def people(make_user: MakeUser) -> dict[str, User]:
    return {
        "uploader": make_user(handle="Uploader"),
        "member": make_user(handle="Member"),
        "trusted": make_user(Role.TRUSTED, handle="Trusted"),
        "expert": make_user(Role.EXPERT, handle="Expert"),
        "moderator": make_user(Role.MODERATOR, handle="Mod"),
    }


def test_an_upload_with_a_position_comes_back_without_it(
    db: Session, client_as: ClientAs, people: dict[str, User]
) -> None:
    client = client_as(people["uploader"])
    response = upload(client, phone_photo(orientation=6))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["approved"], body["rejected"], body["hidden"]) == (False, False, False)
    assert (body["width"], body["height"]) == (20, 40)
    assert body["url"] == f"/api/v1/media/{body['id']}"
    served = client.get(f"{API}/media/{body['id']}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    image = Image.open(io.BytesIO(served.content))
    assert dict(image.getexif()) == {}
    assert image.getexif().get_ifd(ExifTags.IFD.GPSInfo) == {}
    for marker in (b"GPS", b"Silbury", b"PhoneMaker", b"Exif"):
        assert marker not in served.content


def test_the_stored_key_is_random_and_never_sent(
    db: Session, client_as: ClientAs, people: dict[str, User]
) -> None:
    client = client_as(people["uploader"])
    first = upload(client, jpeg()).json()
    second = upload(client, jpeg(colour=(1, 2, 3))).json()
    rows = {row.id: row for row in db.query(Media)}
    for body in (first, second):
        key = rows[body["id"]].storage_key
        assert len(key.split(".")[0]) == 32
        assert key not in str(body)
        assert key not in client.get(f"{API}/media/{body['id']}").headers.get("content-disposition", "")
    assert rows[first["id"]].storage_key[:8] != rows[second["id"]].storage_key[:8]
    # On disk under var/media, where nothing serves it but the API.
    stored = Path(get_settings().var_dir) / "media" / rows[first["id"]].storage_key
    assert stored.is_file()


def test_a_photo_is_served_so_no_browser_runs_it(client_as: ClientAs, people: dict[str, User]) -> None:
    client = client_as(people["uploader"])
    created = upload(client, jpeg(), content_type="text/html").json()
    served = client.get(f"{API}/media/{created['id']}")
    assert served.headers["content-type"] == "image/jpeg"
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert (
        served.headers["content-disposition"] == f'inline; filename="openantiquity-photo-{created["id"]}.jpg"'
    )
    assert served.headers["cache-control"] == "private, no-cache"


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"<script>alert(1)</script>", 422, "not_an_image"),
        (jpeg(300, 300)[:500], 422, "not_an_image"),
        (b"\xff" * (media.MAX_UPLOAD_BYTES + 10), 413, "image_too_large"),
    ],
    ids=["script", "truncated", "oversized"],
)
def test_hostile_uploads_are_refused_and_nothing_is_stored(
    data: bytes, status: int, code: str, db: Session, client_as: ClientAs, people: dict[str, User]
) -> None:
    response = upload(client_as(people["uploader"]), data)
    assert (response.status_code, error_code(response)) == (status, code)
    assert count(db, Media) == 0


def test_an_oversized_upload_is_refused_from_its_declared_length(
    client_as: ClientAs, people: dict[str, User]
) -> None:
    client = client_as(people["uploader"])
    response = client.post(
        f"{API}/media",
        content=b"tiny",
        headers={"Content-Type": "image/jpeg", "Content-Length": str(media.MAX_UPLOAD_BYTES + 1)},
    )
    assert (response.status_code, error_code(response)) == (413, "image_too_large")


def test_uploading_needs_a_contributor_and_is_rate_limited(
    limits_on: None, client: TestClient, client_as: ClientAs, make_user: MakeUser
) -> None:
    assert upload(client, jpeg()).status_code == 401
    newcomer = make_user(age_band=None, terms_accepted_at=None)
    refused = upload(client_as(newcomer), jpeg())
    assert (refused.status_code, error_code(refused)) == (403, "onboarding_required")
    regular = client_as(make_user())
    codes = [upload(regular, jpeg(colour=(i, i, i))).status_code for i in range(31)]
    assert codes[:30] == [201] * 30
    assert codes[30] == 429


def test_an_unapproved_photo_cannot_be_fetched_by_another_member_through_any_route(
    db: Session, client_as: ClientAs, client_for: ClientFor, app: FastAPI, people: dict[str, User]
) -> None:
    owner = client_as(people["uploader"])
    created = upload(owner, jpeg()).json()
    photo_id = created["id"]
    finding = create(db, people["uploader"])
    added = owner.post(
        f"{API}/findings/{finding.public_id}/evidence",
        json={"kind": "photo", "media_id": photo_id, "outcome": "supports", "occurred_on": "2026-11-01"},
    )
    assert added.status_code == 201, added.text
    member, signed_out = client_as(people["member"]), client_for(app)
    for client in (member, signed_out):
        assert client.get(f"{API}/media/{photo_id}").status_code == 404
        page = client.get(f"{API}/findings/{finding.public_id}").json()
        assert [item["media_id"] for item in page["evidence"]] == [None]
        assert f"/media/{photo_id}" not in client.get(f"{API}/findings/{finding.public_id}").text
    # An unused id and a guessed one answer alike.
    never = member.get(f"{API}/media/{photo_id + 1}")
    assert (never.status_code, error_code(never)) == (404, "media_not_found")
    assert error_code(member.get(f"{API}/media/{photo_id}")) == "media_not_found"
    assert member.get(f"{API}/media/0").status_code == 422
    queue = member.get(f"{API}/mod/media")
    assert (queue.status_code, error_code(queue)) == (403, "photo_approvers_only")
    approve = member.post(f"{API}/mod/media/{photo_id}/approve")
    assert (approve.status_code, error_code(approve)) == (403, "photo_approvers_only")
    # Its uploader, trusted members and moderators see it, to judge it.
    for name in ("uploader", "trusted", "expert", "moderator"):
        assert client_as(people[name]).get(f"{API}/media/{photo_id}").status_code == 200, name


def test_approval_shows_it_to_everyone_who_sees_the_finding_exactly(
    db: Session, client_as: ClientAs, client_for: ClientFor, app: FastAPI, people: dict[str, User]
) -> None:
    owner = client_as(people["uploader"])
    open_photo = upload(owner, jpeg()).json()["id"]
    barrow_photo = upload(owner, jpeg(colour=(9, 9, 9))).json()["id"]
    open_finding = create(db, people["uploader"])
    barrow = create(db, people["uploader"], feature_class="round_barrow", lon=-1.81, lat=51.40)
    for finding, photo_id in ((open_finding, open_photo), (barrow, barrow_photo)):
        response = owner.post(
            f"{API}/findings/{finding.public_id}/evidence",
            json={"kind": "photo", "media_id": photo_id, "outcome": "supports", "occurred_on": "2026-11-01"},
        )
        assert response.status_code == 201
    trusted = client_as(people["trusted"])
    queue = trusted.get(f"{API}/mod/media").json()["items"]
    assert [(i["id"], i["uploader"]["handle"], i["findings"]) for i in queue] == [
        (open_photo, "Uploader", [open_finding.public_id]),
        (barrow_photo, "Uploader", [barrow.public_id]),
    ]
    for photo_id in (open_photo, barrow_photo):
        approved = trusted.post(f"{API}/mod/media/{photo_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["approved"] is True
    assert trusted.get(f"{API}/mod/media").json()["items"] == []

    signed_out, member = client_for(app), client_as(people["member"])
    assert signed_out.get(f"{API}/media/{open_photo}").status_code == 200
    # The barrow is protected: its photo is for people who see where it is.
    assert signed_out.get(f"{API}/media/{barrow_photo}").status_code == 404
    assert member.get(f"{API}/media/{barrow_photo}").status_code == 200
    page = member.get(f"{API}/findings/{barrow.public_id}").json()
    assert [item["media_id"] for item in page["evidence"]] == [barrow_photo]
    assert [e.action for e in log_entries(db)] == ["approve_photo", "approve_photo"]


def test_nobody_decides_on_their_own_photo(client_as: ClientAs, people: dict[str, User]) -> None:
    moderator = client_as(people["moderator"])
    own = upload(moderator, jpeg()).json()["id"]
    assert moderator.get(f"{API}/mod/media").json()["items"] == []
    for verb, body, code in (
        ("approve", None, "media_approval_forbidden"),
        ("reject", REASON, "media_rejection_forbidden"),
    ):
        response = moderator.post(f"{API}/mod/media/{own}/{verb}", json=body)
        assert (response.status_code, error_code(response)) == (403, code)
    assert client_as(people["trusted"]).post(f"{API}/mod/media/{own}/approve").status_code == 200


def test_refusing_a_photo_deletes_it_and_blocks_the_same_file(
    db: Session, client_as: ClientAs, people: dict[str, User]
) -> None:
    owner = client_as(people["uploader"])
    raw = phone_photo()
    photo_id = upload(owner, raw).json()["id"]
    row = db.get(Media, photo_id)
    assert row is not None
    stored = Path(get_settings().var_dir) / "media" / row.storage_key
    assert stored.is_file()
    trusted = client_as(people["trusted"])
    refused = trusted.post(f"{API}/mod/media/{photo_id}/reject", json={"reason": "A person's face."})
    assert refused.status_code == 200
    assert refused.json()["rejected"] is True
    assert not stored.exists()
    for name in ("uploader", "trusted", "moderator"):
        assert client_as(people[name]).get(f"{API}/media/{photo_id}").status_code == 404, name
    again = upload(owner, raw)
    assert (again.status_code, error_code(again)) == (422, "media_blocked")
    late = trusted.post(f"{API}/mod/media/{photo_id}/approve")
    assert (late.status_code, error_code(late)) == (404, "media_not_found")
    (entry,) = log_entries(db)
    assert (entry.action, entry.reason) == ("reject_photo", "A person's face.")


def test_a_refusal_that_fails_to_commit_leaves_the_file(
    db: Session, client_as: ClientAs, people: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    photo_id = upload(client_as(people["uploader"]), phone_photo()).json()["id"]
    row = db.get(Media, photo_id)
    assert row is not None
    stored = Path(get_settings().var_dir) / "media" / row.storage_key
    trusted = client_as(people["trusted"])

    def fail(self: Session) -> None:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(Session, "commit", fail)
    with pytest.raises(RuntimeError, match="went away"):
        trusted.post(f"{API}/mod/media/{photo_id}/reject", json={"reason": "A person's face."})
    monkeypatch.undo()
    db.expire_all()
    # The refusal didn't happen, so the photo still has its file and can still be judged.
    assert stored.is_file()
    assert db.get(Media, photo_id).rejected_at is None  # pyright: ignore[reportOptionalMemberAccess]


def test_an_approved_photo_is_hidden_not_refused(
    db: Session, client_as: ClientAs, people: dict[str, User]
) -> None:
    photo_id = upload(client_as(people["uploader"]), jpeg()).json()["id"]
    trusted = client_as(people["trusted"])
    trusted.post(f"{API}/mod/media/{photo_id}/approve")
    refused = client_as(people["moderator"]).post(f"{API}/mod/media/{photo_id}/reject", json=REASON)
    assert (refused.status_code, error_code(refused)) == (409, "media_already_decided")


def test_a_banned_uploaders_photos_leave_the_queue_and_the_public(
    db: Session, client_as: ClientAs, client_for: ClientFor, app: FastAPI, people: dict[str, User]
) -> None:
    owner = client_as(people["uploader"])
    waiting = upload(owner, jpeg()).json()["id"]
    shown = upload(owner, jpeg(colour=(3, 3, 3))).json()["id"]
    trusted = client_as(people["trusted"])
    trusted.post(f"{API}/mod/media/{shown}/approve")
    client_as(people["moderator"]).post(f"{API}/mod/users/Uploader/ban", json=REASON)
    assert trusted.get(f"{API}/mod/media").json()["items"] == []
    assert client_for(app).get(f"{API}/media/{shown}").status_code == 404
    assert client_as(people["moderator"]).get(f"{API}/media/{waiting}").status_code == 200
