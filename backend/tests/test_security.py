"""The security headers, the Content-Security-Policy, the request body limit and the production docs."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub import security
from fieldclub.config import Environment, get_settings
from fieldclub.main import create_app
from fieldclub.services import context
from tests.helpers import BASE_URL, WEB, ClientAs, ClientFor, MakeUser

SHELL = """<!doctype html>
<html><head><style>html,body{background:#14161a;margin:0}</style>
<script type="module" crossorigin src="/assets/index-abc.js"></script></head>
<body><div id="root"></div></body></html>"""


def _directives(policy: str) -> dict[str, list[str]]:
    return {name: values for name, *values in (part.split() for part in policy.split(";"))}


@pytest.fixture
def built(tmp_path: Path, db: Session) -> Iterator[TestClient]:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)")
    (tmp_path / "index.html").write_text(SHELL)
    app = create_app(get_settings().model_copy(update={"frontend_dist": tmp_path}))
    with TestClient(app, base_url=BASE_URL, headers=WEB) as client:
        yield client


@pytest.mark.parametrize(
    "path", ["/", "/f/ABC123", "/assets/index-abc.js", "/healthz", "/api/v1/meta", "/api/v1/nothing-here"]
)
def test_every_answer_carries_the_headers(built: TestClient, path: str) -> None:
    response = built.get(path)
    headers = response.headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    policy = _directives(headers["content-security-policy"])
    assert policy["frame-ancestors"] == ["'none'"]
    assert policy["script-src"] == ["'self'"]
    assert policy["object-src"] == ["'none'"]
    assert policy["base-uri"] == ["'none'"]


def test_an_error_answer_carries_them_too(built: TestClient) -> None:
    response = built.post("/api/v1/findings", json={})
    assert response.status_code == 401
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_the_policy_allows_what_the_map_needs_and_nothing_else(built: TestClient) -> None:
    policy = _directives(built.get("/").headers["content-security-policy"])
    assert "'unsafe-inline'" not in " ".join(policy["script-src"] + policy["style-src"])
    assert "'unsafe-eval'" not in " ".join(policy["script-src"])
    # MapLibre's workers and the images it builds.
    assert policy["worker-src"] == ["'self'", "blob:"]
    assert {"data:", "blob:"} <= set(policy["img-src"])
    # The shell's inline style, by its hash.
    hashes = [value for value in policy["style-src"] if value.startswith("'sha256-")]
    assert len(hashes) == 1
    # Every tile, style and live-source host the catalogues send the browser to, and no other.
    for host in security.map_hosts():
        assert host in policy["connect-src"]
        assert host in policy["img-src"]
    for source in context.shown_live_sources():
        assert any(source["endpoint"].startswith(host) for host in policy["connect-src"])
    assert "https://tiles.openfreemap.org" in policy["connect-src"]
    assert "https:" not in policy["connect-src"] + policy["img-src"]
    assert "https://i.ytimg.com" in policy["img-src"]
    # No sign-in provider's picture host: pictures from providers aren't shown.
    assert not any("googleusercontent" in host or "fbcdn" in host for host in policy["img-src"])


def test_the_shell_may_not_carry_an_inline_script(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    index.write_text("<html><head><script>alert(1)</script></head></html>")
    with pytest.raises(AssertionError, match="inline <script>"):
        security.inline_style_hashes(index)
    index.write_text('<html><head><script type="module" src="/assets/a.js"></script></head></html>')
    assert security.inline_style_hashes(index) == []


def test_a_photo_and_the_report_keep_their_own_stricter_policy(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    from tests.investigations.support import make
    from tests.moderation.support import photo

    uploader = make_user()
    waiting = photo(db, uploader)
    db.commit()
    client = client_as(uploader)
    served = client.get(f"/api/v1/media/{waiting.id}")
    assert served.status_code == 200
    assert served.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert served.headers["x-frame-options"] == "DENY"
    notebook = make(db, uploader)
    report = client.get(f"/api/v1/investigations/{notebook.public_id}/export", params={"format": "html"})
    assert report.status_code == 200
    assert report.headers["content-security-policy"].startswith("default-src 'none'")


def test_hsts_is_sent_only_where_the_site_is_https(db: Session) -> None:
    https = create_app(get_settings().model_copy(update={"public_url": "https://openantiquity.org"}))
    with TestClient(https, base_url=BASE_URL) as client:
        response = client.get("/healthz")
    assert response.headers["strict-transport-security"] == security.HSTS
    assert response.headers["content-security-policy"].endswith("upgrade-insecure-requests")
    plain = create_app(get_settings().model_copy(update={"public_url": "http://localhost:5173"}))
    with TestClient(plain, base_url=BASE_URL) as client:
        assert "strict-transport-security" not in client.get("/healthz").headers


# --------------------------------------------------------------------------
# The docs pages
# --------------------------------------------------------------------------


def test_production_serves_no_docs_and_no_schema(db: Session) -> None:
    """Swagger UI loads its scripts from a CDN, which must never run on the production origin."""
    prod = create_app(get_settings().model_copy(update={"env": Environment.PROD}))
    with TestClient(prod, base_url=BASE_URL) as client:
        for path in ("/api/docs", "/api/openapi.json", "/api/docs/oauth2-redirect", "/api/redoc"):
            assert client.get(path).status_code == 404, path
    # The schema is still there to generate the frontend's types from.
    assert "/api/v1/meta" in prod.openapi()["paths"]


def test_development_keeps_its_docs(client: TestClient) -> None:
    docs = client.get("/api/docs")
    assert docs.status_code == 200
    # Its CDN scripts would be refused by the app's policy, so it goes without one.
    assert "content-security-policy" not in docs.headers
    assert docs.headers["x-frame-options"] == "DENY"
    assert client.get("/api/openapi.json").status_code == 200


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------


def test_a_large_body_is_refused_unread_before_any_sign_in_check(client: TestClient) -> None:
    body = b"[" + b'{"a":0},' * 200_000 + b"{}]"
    assert len(body) > security.BODY_MAX_BYTES
    response = client.post("/api/v1/findings", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert "frame-ancestors" in response.headers["content-security-policy"]


def test_a_large_body_without_a_length_is_refused_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"["
        for _ in range(40):
            yield b"0," * 20_000
        yield b"0]"

    response = client.post("/api/v1/findings", content=chunks(), headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_a_body_without_a_length_under_the_limit_reaches_the_route(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"email": "ann@'
        yield b'example.org"}'

    response = client.post(
        "/api/v1/auth/email/verify", content=chunks(), headers={"content-type": "application/json"}
    )
    # Read whole and validated: no token in it.
    assert response.status_code == 422


def test_the_longest_notes_an_investigation_takes_fit_in_the_limit() -> None:
    from fieldclub.schemas.investigations import NOTES_MAX

    # Every character escaped as \\uXXXX, six bytes each.
    assert NOTES_MAX * 6 < security.BODY_MAX_BYTES


def test_a_photo_has_its_own_larger_limit(client_as: ClientAs, make_user: MakeUser) -> None:
    from fieldclub.services import media

    client = client_as(make_user())
    big = b"\xff" * (security.BODY_MAX_BYTES + 10)
    response = client.post("/api/v1/media", content=big, headers={"content-type": "image/jpeg"})
    # Read by the route, which refuses it as an image, not as too large a request.
    assert response.status_code == 422
    assert response.json()["error"]["code"] != "request_too_large"
    assert len(big) < media.MAX_UPLOAD_BYTES


# --------------------------------------------------------------------------
# Caching an answer that sets a cookie
# --------------------------------------------------------------------------


def test_an_answer_that_sets_a_cookie_is_never_stored(client: TestClient) -> None:
    response = client.post("/api/v1/auth/dev-login", json={"handle": "TestRob"})
    assert "set-cookie" in response.headers
    assert response.headers["cache-control"] == "private, no-store"


# --------------------------------------------------------------------------
# Tiles and other public answers
# --------------------------------------------------------------------------


def test_one_address_can_ask_for_only_so_many_tiles_a_minute(
    app: FastAPI, client_for: ClientFor, limits_on: None
) -> None:
    from fieldclub.api import record_tiles

    caller = client_for(app)
    caller.headers["X-Forwarded-For"] = "203.0.113.9"
    # The bucket refills as the test runs, so ask until it is refused.
    allowed = 0
    while (refused := caller.get("/tiles/records/0/0/0.mvt")).status_code == 200:
        allowed += 1
        assert allowed < 2 * record_tiles.TILES_PER_MINUTE, "never refused"
    assert allowed >= record_tiles.TILES_PER_MINUTE
    assert refused.status_code == 429
    assert "retry-after" in refused.headers
    other = client_for(app)
    other.headers["X-Forwarded-For"] = "198.51.100.9"
    assert other.get("/tiles/records/0/0/0.mvt").status_code == 200


def test_two_people_panning_hard_behind_one_address_are_not_refused_tiles(
    app: FastAPI, client_for: ClientFor, limits_on: None
) -> None:
    """One browser panning and zooming for a minute asked for about 1,200 tiles in the review's
    measurement. A household or a school shares an address, and MapLibre leaves a hole for a refused tile."""
    caller = client_for(app)
    caller.headers["X-Forwarded-For"] = "203.0.113.10"
    answers = {caller.get("/tiles/records/0/0/0.mvt").status_code for _ in range(2 * 1200)}
    assert answers == {200}


def test_a_public_answer_never_carries_a_session_cookie(
    db: Session, make_user: MakeUser, app: FastAPI, client_for: ClientFor
) -> None:
    """A shared cache that kept it would hand the session to the next person."""
    import time_machine

    with time_machine.travel(datetime(2026, 11, 10, 9, 0, tzinfo=UTC), tick=False):
        member = client_for(app, make_user())
    with time_machine.travel(datetime(2026, 11, 11, 9, 0, tzinfo=UTC), tick=False):
        coverage = member.get("/api/v1/squares/coverage", params={"bbox": "-1.9,51.4,-1.8,51.5"})
        assert coverage.headers["cache-control"].startswith("public")
        assert "set-cookie" not in coverage.headers
        # A private answer refreshes the session as usual.
        refreshed = member.get("/api/v1/auth/me")
        assert "set-cookie" in refreshed.headers
        assert refreshed.headers["cache-control"] == "private, no-store"


def test_the_policy_allows_every_thumbnail_host_a_mention_keeps() -> None:
    from fieldclub.services import unfurl

    for host in security.VIDEO_IMAGE_HOSTS:
        assert unfurl.video_thumbnail(f"{host}/vi/dQw4w9WgXcQ/hqdefault.jpg") is not None, host
    assert unfurl.video_thumbnail("https://i10.ytimg.com/vi/x/hqdefault.jpg") is None
