"""Fetching a mention's title, author, thumbnail and date, without keys, from recorded answers."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import respx

from fieldclub.services import unfurl
from fieldclub.services.unfurl import FetchStatus, canonical, page_metadata
from tests.mentions.support import (
    ARTICLE_URL,
    YOUTUBE_URL,
    data,
    ip_of,
    serve,
    serve_article,
    serve_youtube_oembed,
)


def test_youtube_comes_from_its_oembed_endpoint(offline: respx.MockRouter) -> None:
    route = serve_youtube_oembed()
    result = unfurl.unfurl(canonical("https://youtu.be/dQw4w9WgXcQ?t=30"))
    assert result.status is FetchStatus.OK
    assert result.metadata.title == "We found a henge on LIDAR — Avebury part 2"
    assert result.metadata.author_name == "Barrow Walks"
    assert result.metadata.thumbnail_url == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    params = route.calls.last.request.url.params
    assert params["url"] == YOUTUBE_URL
    assert params["format"] == "json"
    assert route.calls.last.request.headers["host"] == "www.youtube.com"


def test_vimeo_comes_from_its_oembed_endpoint(offline: respx.MockRouter) -> None:
    route = serve("vimeo.com", "/api/oembed.json", data("vimeo-oembed.json"), "application/json")
    result = unfurl.unfurl(canonical("https://player.vimeo.com/video/76979871"))
    assert result.metadata.title == "Earthworks from the air"
    assert result.metadata.author_name == "Field Films"
    assert result.metadata.thumbnail_url is not None
    assert result.metadata.thumbnail_url.startswith("https://i.vimeocdn.com/")
    assert result.metadata.published_at == datetime(2013, 8, 26, 11, 13, tzinfo=UTC)
    assert route.calls.last.request.url.params["url"] == "https://vimeo.com/76979871"


def test_a_doi_comes_from_content_negotiation_through_its_redirect(offline: respx.MockRouter) -> None:
    doi = "10.1017/s0079497x00000117"
    hop = serve(
        "doi.org",
        f"/{doi}",
        b"",
        "text/html",
        status=302,
        headers={"location": f"https://api.crossref.org/v1/works/{doi}/transform"},
    )
    answer = serve(
        "api.crossref.org",
        f"/v1/works/{doi}/transform",
        data("doi-csl.json"),
        "application/vnd.citationstyles.csl+json",
    )
    result = unfurl.unfurl(canonical(f"doi:{doi.upper()}"))
    assert result.status is FetchStatus.OK
    assert result.metadata.title == "Maiden Castle revisited: the hillfort and its hinterland"
    assert result.metadata.author_name == "Niall Sharples, Ann Woodward, Peter Marshall and others"
    assert result.metadata.published_at == datetime(2011, 5, 3, tzinfo=UTC)
    # The same Accept header on every hop.
    for route in (hop, answer):
        assert route.calls.last.request.headers["accept"] == "application/vnd.citationstyles.csl+json"


def test_an_article_comes_from_its_open_graph_tags(offline: respx.MockRouter) -> None:
    serve_article()
    result = unfurl.unfurl(canonical(ARTICLE_URL + "?utm_source=x"))
    assert result.metadata == unfurl.Metadata(
        title='Amateurs spot "lost" enclosure near Avebury',
        author_name="Jo Bloggs",
        # A page's own image is never kept: it would tell the site who looked.
        thumbnail_url=None,
        published_at=datetime(2026, 11, 3, 8, 30, tzinfo=UTC),
    )


def test_a_page_without_open_graph_falls_back_to_its_title() -> None:
    meta = page_metadata("<html><head><title>  Old\n  Sarum </title></head><body></body></html>", ARTICLE_URL)
    assert meta.title == "Old Sarum"
    assert meta.thumbnail_url is None


def test_page_text_is_cleaned_before_it_is_kept() -> None:
    html = (
        '<head><meta property="og:title" content="Bad\u202e\u0007title\u200b here">'
        f'<meta property="og:site_name" content="{"x" * 500}"></head>'
    )
    meta = page_metadata(html, ARTICLE_URL)
    assert meta.title == "Bad title here"
    assert meta.author_name is not None
    assert len(meta.author_name) == unfurl.AUTHOR_MAX


def test_a_pages_own_image_is_never_kept() -> None:
    # The page's site is whichever site the member chose, so its image would
    # tell that site the address of everyone who looks at the finding.
    for image in (
        "https://images.wiltshire-gazette.example/2026/11/enclosure.jpg",
        "https://tracker.elsewhere.example/pixel.gif",
        "http://images.wiltshire-gazette.example/a.jpg",
        "https://images.wiltshire-gazette.example:8443/a.jpg",
        "javascript:alert(1)",
    ):
        html = f'<head><meta property="og:image" content="{image}"></head>'
        assert page_metadata(html, ARTICLE_URL).thumbnail_url is None, image


def test_a_video_thumbnail_must_be_on_the_providers_image_hosts(offline: respx.MockRouter) -> None:
    body = json.loads(data("youtube-oembed.json"))
    body["thumbnail_url"] = "https://evil.example/thumb.jpg"
    serve("www.youtube.com", "/oembed", json.dumps(body).encode(), "application/json")
    assert unfurl.unfurl(canonical(YOUTUBE_URL)).metadata.thumbnail_url is None


def test_a_failed_fetch_gives_nothing_and_no_error(offline: respx.MockRouter) -> None:
    serve("www.youtube.com", "/oembed", b"Not Found", "text/html", status=404)
    result = unfurl.unfurl(canonical(YOUTUBE_URL))
    assert result.status is FetchStatus.FAILED
    assert result.metadata == unfurl.NOTHING


def test_an_address_we_wont_fetch_is_refused_quietly(offline: respx.MockRouter) -> None:
    result = unfurl.unfurl(canonical("http://192.168.1.1/admin"))
    assert result.status is FetchStatus.REFUSED
    assert offline.calls.call_count == 0


def test_json_that_isnt_an_object_fails(offline: respx.MockRouter) -> None:
    serve("www.youtube.com", "/oembed", b"[1, 2]", "application/json")
    assert unfurl.unfurl(canonical(YOUTUBE_URL)).status is FetchStatus.FAILED


def test_results_are_cached_so_a_preview_and_a_save_fetch_once(offline: respx.MockRouter) -> None:
    route = serve_youtube_oembed()
    first = unfurl.unfurl(canonical(YOUTUBE_URL))
    second = unfurl.unfurl(canonical("https://youtu.be/dQw4w9WgXcQ"))
    assert first == second
    assert route.call_count == 1


def test_a_failure_is_cached_too(offline: respx.MockRouter) -> None:
    route = respx.get(host=ip_of("www.youtube.com")).mock(side_effect=httpx.ConnectError("down"))
    unfurl.unfurl(canonical(YOUTUBE_URL))
    unfurl.unfurl(canonical(YOUTUBE_URL))
    assert route.call_count == 1


def test_every_format_character_is_taken_out_of_page_text() -> None:
    assert unfurl.clean_text("a\ufeffb\nc\u00adx\u061cy\u202ez\u2066w", 100) == "ab cxyzw"
    assert unfurl.clean_text("\u200b\u202e", 100) is None
