from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from fieldclub.ingest.adapters.common import AdapterError, IncompleteReadError, UpstreamFormatError
from fieldclub.ingest.adapters.rest import RestJson, dig
from tests.ingest.adapters.support import NoWait

URL = "https://api.example/works"


def make() -> RestJson:
    return RestJson(httpx.Client(), polite=NoWait(), where="Example")


def linked(page: list[str], following: str | None, total: int) -> httpx.Response:
    body: dict[str, Any] = {
        "data": [{"id": name} for name in page],
        "meta": {"total": total},
        "links": {"next": following} if following else {},
    }
    return httpx.Response(200, json=body)


def test_dig_follows_a_dotted_path_and_gives_none_for_a_missing_step() -> None:
    body = {"message": {"items": [1, 2], "next-cursor": "abc"}}
    assert dig(body, "message.items") == [1, 2]
    assert dig(body, "message.nope.deeper") is None
    assert dig(body, "") is body
    assert dig([1], "x") is None


@respx.mock
def test_next_links_are_followed_to_the_end_and_counted() -> None:
    respx.get(URL, params={"size": "2"}).mock(return_value=linked(["a", "b"], f"{URL}?cursor=2", 3))
    respx.get(URL, params={"cursor": "2"}).mock(return_value=linked(["c"], None, 3))
    got = list(
        make().items(
            URL, params={"size": "2"}, items="data", total="meta.total", next_url="links.next", id_path="id"
        )
    )
    assert [item["id"] for item in got] == ["a", "b", "c"]


@respx.mock
def test_a_cursor_is_sent_back_as_a_parameter_until_a_page_is_empty() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params["cursor"]
        pages = {"*": (["a", "b"], "k1"), "k1": (["c"], "k2"), "k2": ([], "k2")}
        names, following = pages[cursor]
        body = {"message": {"items": [{"DOI": name} for name in names], "next-cursor": following}}
        return httpx.Response(200, json=body)

    route = respx.get(URL).mock(side_effect=answer)
    got = list(
        make().items(
            URL,
            params={"rows": "2", "cursor": "*"},
            items="message.items",
            cursor="message.next-cursor",
            cursor_param="cursor",
        )
    )
    assert [item["DOI"] for item in got] == ["a", "b", "c"]
    assert [call.request.url.params["cursor"] for call in route.calls] == ["*", "k1", "k2"]
    assert all(call.request.url.params["rows"] == "2" for call in route.calls)


@respx.mock
def test_with_no_way_to_page_the_one_answer_is_everything() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"features": [{"n": 1}, {"n": 2}]}))
    assert list(make().items(URL, items="features")) == [{"n": 1}, {"n": 2}]
    assert route.call_count == 1


@respx.mock
def test_fewer_distinct_items_than_promised_is_an_incomplete_read() -> None:
    # The second page repeats "b" where it skipped "c": three items arrive, two of them distinct.
    respx.get(URL, params={"size": "2"}).mock(return_value=linked(["a", "b"], f"{URL}?cursor=2", 3))
    respx.get(URL, params={"cursor": "2"}).mock(return_value=linked(["b"], None, 3))
    with pytest.raises(IncompleteReadError, match="said it had 3 items and gave 2"):
        list(
            make().items(
                URL,
                params={"size": "2"},
                items="data",
                total="meta.total",
                next_url="links.next",
                id_path="id",
            )
        )


@respx.mock
def test_a_page_that_points_back_stops_the_read() -> None:
    respx.get(URL).mock(return_value=linked(["a"], f"{URL}?cursor=1", 5))
    with pytest.raises(UpstreamFormatError, match="already given"):
        list(make().items(URL, items="data", next_url="links.next"))


@respx.mock
def test_an_answer_of_the_wrong_shape_is_an_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"error": "gone"}))
    with pytest.raises(UpstreamFormatError, match="no list at 'data'"):
        list(make().items(URL, items="data"))
    respx.get(URL).mock(return_value=httpx.Response(200, json={"data": [], "meta": {"total": "many"}}))
    with pytest.raises(UpstreamFormatError, match="no count"):
        list(make().items(URL, items="data", total="meta.total"))
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>Maintenance</html>"))
    with pytest.raises(UpstreamFormatError, match="did not answer with JSON"):
        list(make().items(URL, items="data"))


@respx.mock
def test_a_busy_service_is_retried_after_the_gap_it_asks_for() -> None:
    polite = NoWait()
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"data": [{"id": "a"}]}),
        ]
    )
    pages = RestJson(httpx.Client(), polite=polite)
    assert list(pages.items(URL, items="data")) == [{"id": "a"}]
    assert route.call_count == 2
    assert polite.slept == [7.0]


@respx.mock
def test_closing_the_read_early_asks_for_no_more_pages() -> None:
    route = respx.get(URL).mock(return_value=linked(["a", "b"], f"{URL}?cursor=2", 100))
    reader = make().items(URL, items="data", total="meta.total", next_url="links.next", id_path="id")
    assert next(reader)["id"] == "a"
    reader.close()
    assert route.call_count == 1


@respx.mock
def test_a_document_is_kept_on_disk_and_not_asked_for_again(tmp_path: Path) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b'[{"n": NaN}, {"n": 2}]'))
    pages = make()
    dest = tmp_path / "all.json"
    body, fetched_at = pages.document(URL, dest=dest, params={"country": "GB"}, max_age=timedelta(hours=1))
    assert body == [{"n": None}, {"n": 2}]
    again, same_time = pages.document(URL, dest=dest, params={"country": "GB"}, max_age=timedelta(hours=1))
    assert again == body
    assert same_time == fetched_at
    assert route.call_count == 1
    assert route.calls[0].request.url.params["country"] == "GB"


@respx.mock
def test_a_document_that_is_not_json_is_an_error(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="not json at all"))
    with pytest.raises(UpstreamFormatError, match="did not answer with JSON"):
        make().document(URL, dest=tmp_path / "x.json")


@respx.mock
def test_kept_pages_are_not_asked_for_again_and_a_stopped_read_resumes(tmp_path: Path) -> None:
    first = respx.get(URL, params={"size": "2"}).mock(return_value=linked(["a", "b"], f"{URL}?cursor=2", 3))
    second = respx.get(URL, params={"cursor": "2"}).mock(return_value=httpx.Response(503))

    def read() -> list[str]:
        reader = RestJson(httpx.Client(), polite=NoWait(retries=0), where="Example")
        return [
            item["id"]
            for item in reader.items(
                URL,
                params={"size": "2"},
                items="data",
                total="meta.total",
                next_url="links.next",
                id_path="id",
                cache=tmp_path / "pages",
            )
        ]

    with pytest.raises(AdapterError):
        read()
    assert (first.call_count, second.call_count) == (1, 1)
    second.mock(return_value=linked(["c"], None, 3))
    assert read() == ["a", "b", "c"]
    # The first page came from disk, the second was asked for.
    assert (first.call_count, second.call_count) == (1, 2)
    assert read() == ["a", "b", "c"]
    assert (first.call_count, second.call_count) == (1, 2)


@respx.mock
def test_a_kept_page_for_another_request_or_an_old_one_is_asked_for_again(tmp_path: Path) -> None:
    route = respx.get(URL).mock(return_value=linked(["a"], None, 1))

    def read(size: str, max_age: timedelta) -> None:
        list(
            make().items(
                URL,
                params={"size": size},
                items="data",
                next_url="links.next",
                cache=tmp_path,
                max_age=max_age,
            )
        )

    read("1", timedelta(days=1))
    read("1", timedelta(days=1))
    assert route.call_count == 1
    read("2", timedelta(days=1))
    assert route.call_count == 2
    read("2", timedelta(seconds=-1))
    assert route.call_count == 3


@pytest.mark.parametrize(
    "elsewhere",
    [
        "http://169.254.169.254/computeMetadata/v1/",
        "http://api.example/works?cursor=2",
        "https://api.example:8443/works?cursor=2",
        "https://internal.example/works?cursor=2",
        "https://user:pw@api.example/works?cursor=2",
        "file:///etc/passwd",
    ],
)
@respx.mock
def test_a_next_page_on_another_server_is_refused_unasked(elsewhere: str) -> None:
    """The next page's address is the publisher's to give, so it could point anywhere."""
    respx.get(URL).mock(return_value=linked(["a"], elsewhere, 5))
    with pytest.raises(UpstreamFormatError, match="another server"):
        list(make().items(URL, items="data", next_url="links.next"))
    assert len(respx.calls) == 1
