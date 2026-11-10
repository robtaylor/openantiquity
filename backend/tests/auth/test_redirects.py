"""`next` after sign-in: a relative path on this site, and nothing else."""

from __future__ import annotations

import pytest

from fieldclub.auth.redirects import MAX_NEXT_LENGTH, app_url, safe_next
from tests.helpers import settings

UNSAFE = [
    None,
    "",
    "https://evil.example",
    "HTTPS://evil.example",
    "//evil.example",
    "///evil.example",
    "////evil.example",
    "/\\evil.example",
    "\\evil.example",
    "\\\\evil.example",
    "/x\\y",
    "/%5Cevil.example",
    "/%5cevil.example",
    "/%2F%2Fevil.example",
    "/%2F/evil.example",
    "%2F%2Fevil.example",
    "/%252F%252Fevil.example",
    "/%25252F%25252Fevil.example",
    # Four layers deep: legitimate links are never encoded this many times.
    "/%2525252Fx",
    "/\t/evil.example",
    "/\n/evil.example",
    "/\r/evil.example",
    "/\x00",
    "/\x7f",
    "/%09/evil.example",
    "/%0D%0A/evil.example",
    "/%00",
    "/%7F",
    "/%E2%80%AE/evil",
    "/%E2%80%8B",
    "/\u202e/evil",
    "/\u200b",
    "/caf\u00e9",
    "/ /evil.example",
    " /f/1",
    "javascript:alert(1)",
    "data:text/html,hi",
    "mailto:a@b",
    "evil.example",
    "f/7K3QXM",
    "?next=/",
    "#/f/1",
    "/" + "a" * MAX_NEXT_LENGTH,
    # Dot segments: a browser resolves these to `//evil.example`, another host.
    "/.//evil.example",
    "/a/..//evil.example",
    "/%2e//evil.example",
    "/%2E%2E//evil.example",
    "/.%2e//evil.example",
    "/a/%252e%252e//evil.example",
    "/a/b/../c",
    "/./f/1",
    "/f/..",
    "/f/.?x=1",
]

SAFE = [
    "/",
    "/f/7K3QXM",
    "/f/7K3QXM?layer=slope&zoom=16.5",
    "/u/QuietBarrow42#findings",
    "/f/a%20b",
    "/search?q=caf%C3%A9",
    "/f/%2541",
    "/f/.hidden",
    "/f/a..b",
    "/search?q=../x",
    "/" + "a" * (MAX_NEXT_LENGTH - 1),
]


@pytest.mark.parametrize("value", UNSAFE)
def test_anything_that_could_leave_the_site_becomes_the_home_page(value: str | None) -> None:
    assert safe_next(value) == "/"


@pytest.mark.parametrize("value", SAFE)
def test_a_plain_relative_path_is_kept_as_sent(value: str) -> None:
    assert safe_next(value) == value


@pytest.mark.parametrize("value", ["/javascript:alert(1)", "/f/1?t=12:30"])
def test_a_colon_after_the_first_slash_is_part_of_a_path(value: str) -> None:
    # Prefixed with this site's address, neither can be read as a scheme.
    assert safe_next(value) == value


def test_app_url_always_names_this_site() -> None:
    config = settings(public_url="https://fieldclub.test/")
    assert app_url(config, "/") == "https://fieldclub.test/"
    assert app_url(config, "/f/1?a=b#c") == "https://fieldclub.test/f/1?a=b#c"
    assert (
        app_url(config, "/f/1", signin_error="cancelled")
        == "https://fieldclub.test/f/1?signin_error=cancelled"
    )
    # A code already in the address is replaced, not doubled.
    assert (
        app_url(config, "/f/1?signin_error=old&x=1", signin_error="new")
        == "https://fieldclub.test/f/1?x=1&signin_error=new"
    )


def test_app_url_refuses_a_path_that_was_not_checked() -> None:
    with pytest.raises(AssertionError, match="not a safe local path"):
        app_url(settings(), "//evil.example")
