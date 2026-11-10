"""Published files: download once, cache under `var/`, resume after a dropped connection.

    result = download(url, cache_dir(settings, key) / "monuments.gpkg", client=connector.http,
                      max_age=timedelta(hours=20))
    for feature in read_vector(result.path): ...

The file is written to `<name>.part` and renamed into place only when it is
complete, so a half-written file is never read. A dropped connection resumes
with `Range` and `If-Range`, so if the file changed upstream in the meantime
the server sends it whole and the download starts again. A file younger than
`max_age` is not fetched at all.

ArcGIS Hub answers 202 with `{"status": "ExportingData"}` while it rebuilds
an export. The downloader waits, with growing gaps, up to `max_wait_s`.
Hub's redirect targets are short-lived, so always pass the Hub address and let
the client follow the redirect each time.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from fieldclub.ingest.adapters.common import RETRY_STATUSES, AdapterError, Polite, short_url

logger = logging.getLogger(__name__)

_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)")


@dataclass(frozen=True)
class Download:
    path: Path
    # True when the cached copy was young enough and nothing was fetched.
    from_cache: bool
    size: int
    fetched_at: datetime


def _meta_path(path: Path) -> Path:
    return path.with_name(path.name + ".json")


def _read_meta(path: Path) -> dict[str, Any]:
    try:
        meta = json.loads(_meta_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _write_meta(path: Path, meta: dict[str, Any]) -> None:
    _meta_path(path).write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")


def _validator(response: httpx.Response) -> str | None:
    """What `If-Range` can be: a strong ETag, or else Last-Modified."""
    etag = response.headers.get("etag")
    if etag and not etag.startswith("W/"):
        return etag
    return response.headers.get("last-modified")


def _encoded(response: httpx.Response) -> bool:
    """Whether the body was sent compressed, as ArcGIS sends GeoJSON, and is decompressed as it is read."""
    return response.headers.get("content-encoding", "identity").strip().lower() not in ("", "identity")


def download(
    url: str,
    dest: Path,
    *,
    client: httpx.Client,
    polite: Polite | None = None,
    max_age: timedelta | None = None,
    max_wait_s: float = 1800.0,
    params: dict[str, str] | None = None,
) -> Download:
    """Fetch `url` to `dest`, or reuse `dest` if it is younger than `max_age`."""
    polite = polite or Polite()
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = _read_meta(dest)
    if max_age is not None and dest.is_file() and "fetched_at" in meta:
        fetched_at = datetime.fromisoformat(meta["fetched_at"])
        if polite.now() - fetched_at < max_age:
            logger.info("%s: using the copy fetched at %s", dest.name, fetched_at.isoformat())
            return Download(dest, True, dest.stat().st_size, fetched_at)

    part = dest.with_name(dest.name + ".part")
    part_meta = _read_meta(part)
    # Kept apart, so a long wait for an export doesn't use up the retries for errors.
    retries = 0
    polls = 0
    waited = 0.0
    while True:
        have = part.stat().st_size if part.is_file() else 0
        headers: dict[str, str] = {}
        if have and part_meta.get("validator"):
            headers = {"Range": f"bytes={have}-", "If-Range": part_meta["validator"]}
        polite.wait_turn()
        try:
            done = _fetch(client, url, params, headers, part, have, part_meta)
        except _Retry as retry:
            retries += 1
            if retries > polite.retries:
                raise AdapterError(f"Download of {short_url(url)} kept failing: {retry.reason}") from None
            wait = polite.backoff(retries, retry.response)
            logger.warning("Download of %s: %s, retrying in %.0f s", short_url(url), retry.reason, wait)
            polite.sleep(wait)
            continue
        except _Exporting:
            wait = min(10.0 * 2 ** min(polls, 4), 120.0)
            polls += 1
            waited += wait
            if waited > max_wait_s:
                raise AdapterError(
                    f"{short_url(url)} was still preparing the export after {waited:.0f} s."
                ) from None
            logger.info("%s is preparing the export, asking again in %.0f s", short_url(url), wait)
            polite.sleep(wait)
            continue
        if done:
            break
        retries = 0

    size = part.stat().st_size
    expected = part_meta.get("total")
    if isinstance(expected, int) and expected != size:
        raise AdapterError(f"Download of {short_url(url)} has {size} bytes, not the {expected} promised.")
    part.replace(dest)
    _meta_path(part).unlink(missing_ok=True)
    fetched_at = polite.now()
    _write_meta(dest, {"url": url, "fetched_at": fetched_at.isoformat(), "size": size, **part_meta})
    logger.info("%s: downloaded %d bytes", dest.name, size)
    return Download(dest, False, size, fetched_at)


class _Retry(Exception):  # noqa: N818 - control flow, never seen outside this module
    def __init__(self, reason: str, response: httpx.Response | None = None) -> None:
        self.reason = reason
        self.response = response


class _Exporting(Exception):  # noqa: N818 - control flow, never seen outside this module
    pass


def _fetch(
    client: httpx.Client,
    url: str,
    params: dict[str, str] | None,
    headers: dict[str, str],
    part: Path,
    have: int,
    part_meta: dict[str, Any],
) -> bool:
    """One request. Returns True when the file is complete, False to go round again."""
    try:
        with client.stream("GET", url, params=params, headers=headers) as response:
            status = response.status_code
            if status == 202:
                response.read()
                raise _Exporting()
            if status == 416:
                # Nothing left to send, or the part file is not what the server has.
                if response.headers.get("content-range", "").endswith(f"/{have}"):
                    part_meta["total"] = have
                    return True
                part.unlink(missing_ok=True)
                part_meta.clear()
                return False
            if status in RETRY_STATUSES:
                response.read()
                raise _Retry(f"HTTP {status}", response)
            if status >= 400:
                response.read()
                raise AdapterError(f"Download of {short_url(url)} answered {status}: {response.text[:200]!r}")
            if status == 206:
                match = _CONTENT_RANGE.match(response.headers.get("content-range", ""))
                if match is None or int(match.group(1)) != have:
                    raise AdapterError(f"{short_url(url)} sent a range that doesn't continue the file.")
                mode = "ab"
                total = None if match.group(3) == "*" else int(match.group(3))
            else:
                assert status == 200, f"unexpected status {status} after redirects"
                # A full body: the server ignored the range, or the file changed.
                mode = "wb"
                length = response.headers.get("content-length")
                total = int(length) if length and length.isdigit() else None
                part_meta.clear()
                part_meta["validator"] = _validator(response)
                if _encoded(response):
                    # The length counts the compressed bytes, and the client writes them
                    # decompressed, so neither the length nor a byte range applies to the file.
                    total = None
                    part_meta["validator"] = None
            if total is not None:
                part_meta["total"] = total
            _write_meta(part, part_meta)
            with part.open(mode) as out:
                for chunk in response.iter_bytes():
                    out.write(chunk)
    except httpx.TransportError as exc:
        # Whatever reached the part file stays, and the next request resumes after it.
        raise _Retry(f"{type(exc).__name__}: {exc}") from None
    size = part.stat().st_size
    total = part_meta.get("total")
    if isinstance(total, int) and size < total:
        raise _Retry(f"the connection closed at {size} of {total} bytes")
    return True
