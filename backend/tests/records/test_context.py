from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.services import context
from tests.helpers import AVEBURY, admin_area
from tests.records import context_data

BELFAST = (-5.93, 54.597)
PARIS = (2.35, 48.86)


def test_the_packaged_files_match_the_work_lists() -> None:
    """Regenerate with `uv run python -m tests.records.context_data` when this fails."""
    for name, items in context_data.build().items():
        shipped = (context_data.DATA / name).read_text(encoding="utf-8")
        assert shipped == context_data.render(items), f"{name} is out of date"


def test_live_sources_leave_out_the_unconfirmed() -> None:
    worklist = json.loads((context_data.WORKLISTS / "sources.json").read_text(encoding="utf-8"))
    unconfirmed = {entry["key"] for entry in worklist["live_unconfirmed"]}
    not_records = {entry["key"] for entry in worklist["non_record"]}
    keys = {item["key"] for item in context.live_sources()}
    assert unconfirmed
    assert keys.isdisjoint(unconfirmed | not_records)
    assert keys == {entry["key"] for entry in worklist["live"] if entry["cors"].startswith("yes")}
    assert "ads-catalogue-search" in keys
    for item in context.live_sources():
        assert item["endpoint"].startswith("https://")
        assert item["attribution"]
        assert item["licence"]


def test_deep_links_leave_out_the_excluded() -> None:
    keys = {link["key"] for link in context.deep_links()}
    assert keys.isdisjoint(context_data.EXCLUDED_LINKS)
    assert "he-nhle-list-entry" in keys
    record_link = next(link for link in context.deep_links() if link["key"] == "he-nhle-list-entry")
    assert not record_link["for_point"]


def test_no_link_the_research_held_back_is_served() -> None:
    worklist = json.loads((context_data.WORKLISTS / "deep-links.json").read_text(encoding="utf-8"))
    notes = {entry["key"]: entry["notes"] or "" for entry in worklist}
    held_back = {
        key for key, note in notes.items() if any(phrase in note for phrase in context_data.NOT_FOR_PEOPLE)
    }
    assert {"old-maps-online", "canmore-legacy-site", "he-nhle-legacy-list"} <= held_back
    assert held_back <= set(context_data.EXCLUDED_LINKS)


def test_the_live_sources_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/context/live-sources")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"
    items = response.json()["items"]
    ads = next(item for item in items if item["key"] == "ads-catalogue-search")
    assert "{north},{west},{south},{east}" in ads["query_pattern"]
    assert ads["link_template"] == "https://archaeologydataservice.ac.uk/data-catalogue/resource/{id}"
    assert set(ads) == {
        "key", "name", "publisher", "coverage", "endpoint", "query_pattern", "response_fields",
        "licence", "attribution", "link_template", "limits",
    }  # fmt: skip


def by_key(found: context.PointLinks) -> dict[str, str]:
    return {link.key: link.url for link in found.links}


def test_links_at_avebury_fill_each_coordinate_system(db: Session) -> None:
    found = context.links_for(db, *AVEBURY, zoom=16)
    links = by_key(found)
    assert found.grid_ref == gridref.to_gridref(*AVEBURY, 8)

    assert "center=-1.85420,51.42860&level=16" in links["he-apex-viewer"]
    assert links["nls-explore-at-point"].startswith(
        "https://maps.nls.uk/geo/explore/#zoom=16&lat=51.42860&lon=-1.85420"
    )

    _, easting, northing = gridref.to_grid(*AVEBURY)
    kyp = parse_qs(urlsplit(links["know-your-place-wilts"]).query)
    assert (kyp["x"], kyp["y"]) == ([f"{easting:.0f}"], [f"{northing:.0f}"])
    # Britain from Above takes its own zoom index, not the map's.
    assert links["britain-from-above-map"].endswith(f"#7,{easting:.0f},{northing:.0f}")

    x, y = Transformer.from_crs(4326, 3857, always_xy=True).transform(*AVEBURY)
    assert f"c={y:.2f}:{x:.2f}&z=16" in links["ncap-air-photo-finder"]
    assert all("{" not in url for url in links.values())
    assert not set(links) & set(context_data.EXCLUDED_LINKS)


def test_links_respect_a_viewers_bounds(db: Session) -> None:
    # Swindon is in Wiltshire's edition of Know Your Place. Norwich isn't.
    assert "know-your-place-wilts" in by_key(context.links_for(db, -1.78, 51.56))
    assert "know-your-place-wilts" not in by_key(context.links_for(db, 1.30, 52.63))


def test_links_follow_the_nation_once_boundaries_are_loaded(db: Session) -> None:
    # Without admin areas every British viewer is offered, trove.scot included.
    assert "trove-map-at-point" in by_key(context.links_for(db, *AVEBURY))
    db.add(admin_area("nation", "england", "England", (-6, 49.8, 2, 55.8)))
    db.commit()
    links = by_key(context.links_for(db, *AVEBURY))
    assert "trove-map-at-point" not in links
    assert "he-apex-viewer" in links


def test_links_in_northern_ireland_skip_british_grid_viewers(db: Session) -> None:
    links = by_key(context.links_for(db, *BELFAST))
    assert "britain-from-above-map" not in links  # needs British grid eastings
    assert "he-apex-viewer" not in links  # England only
    assert "google-earth-web" in links


def test_links_off_the_grids(db: Session) -> None:
    found = context.links_for(db, *PARIS)
    assert found.grid_ref is None
    # Only the viewers that cover the wider world, not the British ones.
    assert set(by_key(found)) == {"google-earth-web"}


def test_the_links_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/context/links", params={"lon": AVEBURY[0], "lat": AVEBURY[1]})
    assert response.status_code == 200
    # Shorter than the catalogue's day, because the answer follows the admin areas.
    assert response.headers["cache-control"] == "public, max-age=3600"
    body = response.json()
    assert body["grid_ref"].startswith("SU ")
    item = next(item for item in body["items"] if item["key"] == "he-apex-viewer")
    assert item["verified"] == "not_tested"
    assert item["no_frame"] is False
    assert "level=15" in item["url"]


@pytest.mark.parametrize(
    "params", [{"lon": "200", "lat": "51"}, {"lon": "-1"}, {"lon": "-1", "lat": "51", "zoom": "40"}]
)
def test_the_links_endpoint_needs_a_position(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/api/v1/context/links", params=params).status_code == 422
