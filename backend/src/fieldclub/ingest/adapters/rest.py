"""Paged JSON over HTTP, and single JSON documents, read politely.

    pages = RestJson(client, polite=Polite(delay_s=1), where="DataCite")
    for item in pages.items(
        "https://api.datacite.org/dois",
        params={"client-id": "bl.ads", "page[cursor]": "1", "page[size]": "1000"},
        items="data",
        total="meta.total",
        next_url="links.next",
        id_path="id",
    ): ...

    body, fetched_at = pages.document(url, params=..., dest=cache_dir(...) / "all.json", max_age=...)

`items` follows the next page the way the service says to: `next_url` names
the field that holds the whole address of the next page (JSON:API's
`links.next`), and `cursor` with `cursor_param` names the field that holds a
cursor value to send back as a query parameter (Crossref's
`message.next-cursor`). With neither, the one answer is the whole result.
Paths are dotted, such as `message.items`.

The read stops on an empty page or when no next page is named. When the
service says how many items there are (`total`), the read counts the distinct
ones by `id_path` and raises `IncompleteReadError` if fewer arrive, so a
truncated or shifting answer fails the run instead of deleting records. A
next address or cursor that repeats stops the read with an error, because
following it would loop for ever.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from fieldclub.ingest.adapters.common import (
    Polite,
    Tally,
    UpstreamFormatError,
    json_body,
    plain_tree,
    short_url,
)
from fieldclub.ingest.adapters.download import download

logger = logging.getLogger(__name__)

# A safety stop. No source read so far has more than a few hundred pages.
MAX_PAGES = 5000


def dig(value: Any, path: str) -> Any:
    """The value at a dotted `path` inside nested objects, or None where any step is missing.

    An empty path is the value itself.
    """
    for step in path.split(".") if path else ():
        if not isinstance(value, dict):
            return None
        value = value.get(step)
    return value


class RestJson:
    def __init__(
        self,
        client: httpx.Client,
        *,
        polite: Polite | None = None,
        where: str = "The JSON service",
        tolerance: float = 0.0,
    ) -> None:
        self.client = client
        self.polite = polite or Polite()
        self.where = where
        self.tolerance = tolerance

    def get(self, url: str, params: dict[str, str] | None = None) -> Any:
        """One request, parsed as JSON. NaN and infinities in it are turned into None."""
        response = self.polite.request(
            self.client, "GET", url, params=params, headers={"Accept": "application/json"}
        )
        return plain_tree(json_body(response, f"{self.where} ({short_url(url)})"))

    def document(
        self,
        url: str,
        *,
        dest: Path,
        params: dict[str, str] | None = None,
        max_age: timedelta | None = None,
    ) -> tuple[Any, datetime]:
        """One JSON document kept at `dest`, fetched only when the copy is older than `max_age`.

        Returns the parsed document and when it was obtained. For answers too
        big to ask for again on every run.
        """
        fetched = download(url, dest, client=self.client, polite=self.polite, max_age=max_age, params=params)
        try:
            text = fetched.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise UpstreamFormatError(f"{self.where} ({short_url(url)}) is not UTF-8 text.") from None
        try:
            return plain_tree(json.loads(text)), fetched.fetched_at
        except ValueError:
            raise UpstreamFormatError(f"{self.where} ({short_url(url)}) did not answer with JSON.") from None

    def items(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        items: str,
        total: str | None = None,
        next_url: str | None = None,
        cursor: str | None = None,
        cursor_param: str | None = None,
        id_path: str | None = None,
        cache: Path | None = None,
        max_age: timedelta | None = None,
    ) -> Generator[Any]:
        """Every item of every page, in order. See the module docstring for what the arguments name.

        With `cache`, a directory, each page is kept there as it arrives and
        read from there for `max_age` (a day by default), so a run that stops
        part way, or a second run the same day, asks the service only for the
        pages it has not got. A kept page counts only for the same address and parameters.
        """
        assert not (next_url and cursor), "name the next page by its address or by a cursor, not both"
        assert (cursor is None) == (cursor_param is None), "a cursor path needs a cursor parameter and back"
        params = dict(params or {})
        tally: Tally | None = None
        seen_next: set[str] = set()
        request_url: str | None = url
        for page_number in range(1, MAX_PAGES + 1):
            assert request_url is not None
            if cache is None:
                body = self.get(request_url, params or None)
            else:
                body = self._kept_page(cache / f"page-{page_number:05d}.json", request_url, params, max_age)
            page = dig(body, items)
            if not isinstance(page, list):
                raise UpstreamFormatError(f"{self.where} gave no list at {items!r} on page {page_number}.")
            if page_number == 1 and total is not None:
                promised = dig(body, total)
                if not isinstance(promised, int) or isinstance(promised, bool) or promised < 0:
                    raise UpstreamFormatError(f"{self.where} gave no count at {total!r}: {promised!r}.")
                logger.info("%s: %d items promised", self.where, promised)
                tally = Tally(self.where, promised, self.tolerance, what="items")
            for item in page:
                if tally is not None:
                    tally.add(dig(item, id_path) if id_path else None)
                yield item
            following = self._following(body, next_url, cursor)
            if not page or following is None:
                break
            if following in seen_next:
                raise UpstreamFormatError(f"{self.where} pointed back to a page it had already given.")
            seen_next.add(following)
            if next_url:
                _check_same_service(url, following, self.where)
                request_url, params = following, {}
            else:
                assert cursor_param is not None
                params[cursor_param] = following
        else:
            raise UpstreamFormatError(f"{self.where} was still paging after {MAX_PAGES} pages.")
        if tally is not None:
            tally.check()

    def _kept_page(self, path: Path, url: str, params: dict[str, str], max_age: timedelta | None) -> Any:
        """A page from `path` when kept for this request and young enough, else asked for and kept."""
        wanted = {"url": url, "params": params}
        limit = (max_age or timedelta(days=1)).total_seconds()
        try:
            if time.time() - path.stat().st_mtime <= limit:
                kept = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(kept, dict) and kept.get("request") == wanted and "body" in kept:
                    return kept["body"]
        except (OSError, ValueError):
            pass
        body = self.get(url, params or None)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_text(json.dumps({"request": wanted, "body": body}), encoding="utf-8")
        part.replace(path)
        return body

    @staticmethod
    def _following(body: Any, next_url: str | None, cursor: str | None) -> str | None:
        path = next_url or cursor
        if path is None:
            return None
        value = dig(body, path)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise UpstreamFormatError(f"The next page at {path!r} is not text: {value!r}.")
        return value


def _check_same_service(first: str, following: str, where: str) -> None:
    """Refuse a next-page address on another scheme, host or port than the first page's.

    The address comes from the publisher's answer, and the shared client goes
    wherever it is sent, so a hostile or broken answer must not steer a run at
    another server, such as one inside the network the job runs in.
    """
    a, b = urlsplit(first), urlsplit(following)
    same = (a.scheme.lower(), a.hostname, a.port) == (b.scheme.lower(), b.hostname, b.port)
    if not same or b.scheme.lower() not in ("http", "https") or b.username or b.password:
        raise UpstreamFormatError(f"{where} gave a next page on another server: {following[:200]!r}.")
