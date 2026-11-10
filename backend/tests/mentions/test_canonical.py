"""One canonical address per thing, whichever way its link was written."""

from __future__ import annotations

import pytest

from fieldclub.services.unfurl import InvalidAddressError, canonical, parse_start
from fieldclub.vocab import MentionKind

VIDEO = "dQw4w9WgXcQ"
WATCH = f"https://www.youtube.com/watch?v={VIDEO}"

YOUTUBE_FORMS = [
    f"https://www.youtube.com/watch?v={VIDEO}",
    f"http://www.youtube.com/watch?v={VIDEO}",
    f"https://youtube.com/watch?v={VIDEO}",
    f"https://m.youtube.com/watch?v={VIDEO}",
    f"https://music.youtube.com/watch?v={VIDEO}",
    f"https://WWW.YouTube.com/watch?v={VIDEO}",
    f"www.youtube.com/watch?v={VIDEO}",
    f"youtube.com/watch?v={VIDEO}",
    f"https://www.youtube.com/watch?feature=share&v={VIDEO}",
    f"https://www.youtube.com/watch?v={VIDEO}&list=PL123&index=2",
    f"https://www.youtube.com/watch?v={VIDEO}&utm_source=newsletter&si=abcdef",
    f"https://www.youtube.com/watch/?v={VIDEO}",
    f"https://youtu.be/{VIDEO}",
    f"https://youtu.be/{VIDEO}?si=Zx9_yWq",
    f"youtu.be/{VIDEO}",
    f"https://www.youtube.com/shorts/{VIDEO}",
    f"https://youtube.com/shorts/{VIDEO}?feature=share",
    f"https://www.youtube.com/live/{VIDEO}",
    f"https://www.youtube.com/live/{VIDEO}?si=abc",
    f"https://www.youtube.com/embed/{VIDEO}",
    f"https://www.youtube.com/embed/{VIDEO}?rel=0",
    f"https://www.youtube-nocookie.com/embed/{VIDEO}",
    f"https://www.youtube.com/v/{VIDEO}?version=3",
    f"https://www.youtube.com/e/{VIDEO}",
    f"https://www.youtube.com/watch?v={VIDEO}#comments",
]

# Each form with a start time, and the seconds it means.
YOUTUBE_TIMED = [
    (f"https://www.youtube.com/watch?v={VIDEO}&t=90", 90),
    (f"https://www.youtube.com/watch?v={VIDEO}&t=90s", 90),
    (f"https://www.youtube.com/watch?v={VIDEO}&t=1m30s", 90),
    (f"https://www.youtube.com/watch?v={VIDEO}&t=1h2m3s", 3723),
    (f"https://youtu.be/{VIDEO}?t=754", 754),
    (f"https://youtu.be/{VIDEO}?si=abc&t=12", 12),
    (f"https://www.youtube.com/embed/{VIDEO}?start=45", 45),
    (f"https://www.youtube.com/watch?v={VIDEO}#t=2m", 120),
    (f"https://www.youtube.com/shorts/{VIDEO}?t=5", 5),
    (f"https://www.youtube.com/live/{VIDEO}?t=3600", 3600),
    (f"https://www.youtube.com/watch?time_continue=17&v={VIDEO}", 17),
]


@pytest.mark.parametrize("link", YOUTUBE_FORMS)
def test_every_youtube_form_has_the_same_canonical_address(link: str) -> None:
    address = canonical(link)
    assert address.canonical_url == WATCH
    assert address.kind is MentionKind.VIDEO
    assert address.provider == "youtube"
    assert address.item_id == VIDEO
    assert address.start_seconds is None


@pytest.mark.parametrize(("link", "seconds"), YOUTUBE_TIMED)
def test_a_start_time_is_kept_apart_from_the_address(link: str, seconds: int) -> None:
    address = canonical(link)
    assert address.canonical_url == WATCH
    assert address.start_seconds == seconds


def test_the_typed_address_is_kept_as_given() -> None:
    assert canonical(f"  youtu.be/{VIDEO}?t=5 ").url == f"https://youtu.be/{VIDEO}?t=5"


@pytest.mark.parametrize(
    "link",
    [
        "https://www.youtube.com/@barrowwalks",
        "https://www.youtube.com/watch?v=tooshort",
        "https://youtu.be/",
        "https://www.youtube.com/playlist?list=PL123",
    ],
)
def test_a_youtube_link_that_names_no_video_is_an_ordinary_page(link: str) -> None:
    address = canonical(link)
    assert address.kind is MentionKind.ARTICLE
    assert address.item_id is None


@pytest.mark.parametrize(
    ("link", "expected", "start"),
    [
        ("https://vimeo.com/76979871", "https://vimeo.com/76979871", None),
        ("https://www.vimeo.com/76979871?share=copy", "https://vimeo.com/76979871", None),
        ("https://vimeo.com/76979871#t=90s", "https://vimeo.com/76979871", 90),
        ("https://player.vimeo.com/video/76979871", "https://vimeo.com/76979871", None),
        (
            "https://player.vimeo.com/video/76979871?h=8272103f6e",
            "https://vimeo.com/76979871/8272103f6e",
            None,
        ),
        ("https://vimeo.com/76979871/8272103f6e", "https://vimeo.com/76979871/8272103f6e", None),
        ("https://vimeo.com/channels/staffpicks/76979871", "https://vimeo.com/76979871", None),
        ("https://vimeo.com/groups/archaeology/videos/76979871", "https://vimeo.com/76979871", None),
        ("https://vimeo.com/showcase/123/video/76979871", "https://vimeo.com/76979871", None),
    ],
)
def test_vimeo_links(link: str, expected: str, start: int | None) -> None:
    address = canonical(link)
    assert (address.canonical_url, address.kind, address.provider, address.start_seconds) == (
        expected,
        MentionKind.VIDEO,
        "vimeo",
        start,
    )


@pytest.mark.parametrize(
    "link",
    [
        "10.5284/1040209",
        "doi:10.5284/1040209",
        "DOI: 10.5284/1040209",
        "https://doi.org/10.5284/1040209",
        "http://dx.doi.org/10.5284/1040209",
        "https://www.doi.org/10.5284/1040209",
        "https://doi.org/10.5284%2F1040209",
        "doi.org/10.5284/1040209",
    ],
)
def test_a_doi_in_any_form_becomes_its_doi_org_address(link: str) -> None:
    address = canonical(link)
    assert address.canonical_url == "https://doi.org/10.5284/1040209"
    assert address.kind is MentionKind.PAPER
    assert address.provider == "doi"
    assert address.item_id == "10.5284/1040209"


def test_dois_ignore_case() -> None:
    assert (
        canonical("10.1017/S0079497X00000117").canonical_url
        == canonical("https://doi.org/10.1017/s0079497x00000117").canonical_url
    )


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        (
            "HTTPS://WWW.Wiltshire-Gazette.Example/News/Lost?utm_source=x&utm_medium=y&id=4#comments",
            "https://www.wiltshire-gazette.example/News/Lost?id=4",
        ),
        ("https://example.org", "https://example.org/"),
        ("https://example.org:443/a", "https://example.org/a"),
        ("https://example.org:8443/a", "https://example.org:8443/a"),
        ("https://example.org/a?fbclid=123&gclid=4&mc_eid=5", "https://example.org/a"),
        ("https://example.org/a?page=2&ref_src=twsrc", "https://example.org/a?page=2"),
        ("https://xn--mnchen-3ya.example/a", "https://xn--mnchen-3ya.example/a"),
        ("https://münchen.example/a", "https://xn--mnchen-3ya.example/a"),
    ],
)
def test_articles_lose_case_fragments_and_tracking(link: str, expected: str) -> None:
    address = canonical(link)
    assert address.canonical_url == expected
    assert address.kind is MentionKind.ARTICLE


@pytest.mark.parametrize(
    ("link", "kind"),
    [
        ("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk?si=abc", MentionKind.PODCAST),
        ("https://podcasts.apple.com/gb/podcast/dig/id123?i=1000", MentionKind.PODCAST),
        ("https://www.bbc.co.uk/iplayer/episode/m001", MentionKind.BROADCAST),
        ("https://www.bbc.co.uk/sounds/play/m002", MentionKind.PODCAST),
        ("https://bsky.app/profile/someone/post/3k", MentionKind.SOCIAL),
        ("https://www.bbc.co.uk/news/articles/c1", MentionKind.ARTICLE),
    ],
)
def test_the_kind_follows_the_site(link: str, kind: MentionKind) -> None:
    assert canonical(link).kind is kind


def test_a_podcast_keeps_its_episode_parameter_and_loses_the_share_one() -> None:
    assert (
        canonical("https://podcasts.apple.com/gb/podcast/dig/id123?i=1000&si=x").canonical_url
        == "https://podcasts.apple.com/gb/podcast/dig/id123?i=1000"
    )
    assert (
        canonical("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk?si=abc").canonical_url
        == "https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk"
    )


@pytest.mark.parametrize(
    "link",
    [
        "",
        "   ",
        "javascript:alert(1)",
        "mailto:someone@example.org",
        "ftp://example.org/file",
        "file:///etc/passwd",
        "data:text/html,hello",
        "https://user:secret@example.org/",
        "https://localhost/",
        "https://example.org/a b",
        "https://example.org/\u0000",
        "doi:11.1234/x",
        "https://" + "a" * 2000 + ".example/",
    ],
)
def test_what_isnt_a_web_address_is_refused(link: str) -> None:
    with pytest.raises(InvalidAddressError):
        canonical(link)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("90", 90),
        ("90s", 90),
        ("1m30s", 90),
        ("1h", 3600),
        ("1:30", 90),
        ("1:02:03", 3723),
        ("0", None),
        ("", None),
        ("abc", None),
        ("-5", None),
        ("999999", None),
    ],
)
def test_start_times(text: str, seconds: int | None) -> None:
    assert parse_start(text) == seconds
