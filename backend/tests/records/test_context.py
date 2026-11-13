from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.services import context
from fieldclub.vocab import CreditPlacement, LinkShows, LinkVerified, LiveFormat
from tests.helpers import AVEBURY, admin_area
from tests.records import context_data

BELFAST = (-5.93, 54.597)
DUBLIN = (-6.26, 53.35)
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
    # A withheld source isn't served at all, so its endpoint and pattern can't be used by mistake.
    assert {item["key"] for item in items} == {
        item["key"] for item in context.live_sources() if item["shown"]
    }
    assert all(item["shown"] for item in items)
    assert "ads-catalogue-search" not in {item["key"] for item in items}
    wiltshire = next(item for item in items if item["key"] == "wiltshire-her-monuments")
    assert "{west},{south},{east},{north}" in wiltshire["query_pattern"]
    assert set(wiltshire) == {
        "key", "name", "publisher", "coverage", "endpoint", "query_pattern", "response_fields",
        "licence", "attribution", "link_template", "limits", "answer_format", "id_field",
        "name_field", "limit_param", "max_limit", "min_zoom", "shown", "credit_placement", "credit",
        "licence_label", "homepage", "credit_field", "licence_field", "preferred_credit_field",
    }  # fmt: skip
    assert (wiltshire["answer_format"], wiltshire["id_field"], wiltshire["name_field"]) == (
        "geojson",
        "MonUID",
        "Name",
    )
    assert (wiltshire["limit_param"], wiltshire["max_limit"], wiltshire["min_zoom"]) == (
        "resultRecordCount",
        1000,
        13,
    )


def test_the_catalogue_keeps_how_to_read_a_withheld_source() -> None:
    ads = next(item for item in context.live_sources() if item["key"] == "ads-catalogue-search")
    assert ads["shown"] is False
    assert "{north},{west},{south},{east}" in ads["query_pattern"]
    assert ads["link_template"] == "https://archaeologydataservice.ac.uk/data-catalogue/resource/{id}"
    assert (ads["answer_format"], ads["id_field"], ads["name_field"]) == (
        "ads_search",
        "id",
        "data.title.text",
    )
    assert (ads["limit_param"], ads["max_limit"], ads["min_zoom"]) == ("size", 50, 14)


def test_each_live_source_says_how_to_read_it_without_guessing() -> None:
    worklist = json.loads((context_data.WORKLISTS / "sources.json").read_text(encoding="utf-8"))
    shapes = {
        entry["key"]: entry["response_shape"] + " ".join(entry["gotchas"]) for entry in worklist["live"]
    }
    # "Full record as search hits".
    shapes["ads-catalogue-record"] += shapes["ads-catalogue-search"]
    for item in context.live_sources():
        key, pattern = item["key"], item["query_pattern"]
        assert item["answer_format"] in set(LiveFormat), key
        if "f=geojson" in pattern:
            assert item["answer_format"] == LiveFormat.GEOJSON, key
        # A field named is one the work-list names.
        for field in (item["id_field"], item["name_field"]):
            assert field is None or field.split(".")[-1] in shapes[key], (key, field)
        # The pattern carries no cap of its own: the browser adds `limit_param`.
        assert (item["limit_param"] is None) is (item["max_limit"] is None), key
        if item["limit_param"] is not None:
            assert f"{item['limit_param']}=" not in pattern, key
            assert item["max_limit"] > 0
        assert "resultRecordCount=2" not in pattern
        # Only a request by id has no zoom to ask from.
        assert (item["min_zoom"] is None) is ("{id}" in pattern), key
        assert item["min_zoom"] is None or 0 <= item["min_zoom"] <= 20


def test_each_live_source_says_how_to_credit_it_or_is_not_shown() -> None:
    worklist = json.loads((context_data.WORKLISTS / "sources.json").read_text(encoding="utf-8"))
    entries = {entry["key"]: entry for entry in worklist["live"]}
    shapes = {key: entry["response_shape"] + entry["attribution"] for key, entry in entries.items()}
    items = {item["key"]: item for item in context.live_sources()}
    for key, item in items.items():
        if not item["shown"]:
            assert (item["credit"], item["licence_label"], item["credit_field"]) == (None, None, None), key
            assert item["preferred_credit_field"] is None, key
            continue
        assert item["credit"], key
        assert item["licence_label"], key
        # Not the research notes, which the browser used to show.
        assert item["licence_label"] != item["licence"], key
        assert item["homepage"] is None or item["homepage"].startswith("https://"), key
        for field in (item["credit_field"], item["licence_field"], item["preferred_credit_field"]):
            if field is not None:
                named = [part for part in field.split(".") if not part.isdigit() and part != "value"]
                assert named[-1] in shapes[key], (key, field)
    shown = {key for key, item in items.items() if item["shown"]}
    assert shown == {
        "he-aerial-photos-obliques",
        "he-aerial-photos-verticals",
        "dnpa-dartmoor-her",
        "wiltshire-her-monuments",
        "wolverhampton-walsall-her",
        "cambridge-cucap-pois",
        "wikimedia-commons-geosearch",
        "wikimedia-wikipedia-geosearch",
    }
    # The publisher's words where it prescribes them, and the per-record credit where it asks for one.
    assert (
        "© Crown copyright and database rights 2026 OS AC0000823576" in items["dnpa-dartmoor-her"]["credit"]
    )
    assert items["he-aerial-photos-obliques"]["credit_field"] == "Copyright"
    commons = items["wikimedia-commons-geosearch"]
    assert commons["credit_field"].endswith("extmetadata.Artist.value")
    # The work-list's credit names the file's own Attribution, so the request asks for it.
    assert commons["preferred_credit_field"].endswith("extmetadata.Attribution.value")
    filters = parse_qs(urlsplit(commons["query_pattern"]).query)["iiextmetadatafilter"]
    assert "Attribution" in filters[0].split("|")
    # "Link to the article and state the licence".
    assert items["wikimedia-wikipedia-geosearch"]["link_template"] == "https://en.wikipedia.org/wiki/{title}"
    # Scotland isn't in the first release, and its terms are for personal research only.
    assert items["aberdeenshire-her"]["shown"] is False


def test_each_deep_link_says_what_its_viewer_shows(client: TestClient) -> None:
    worklist = json.loads((context_data.WORKLISTS / "deep-links.json").read_text(encoding="utf-8"))
    assert all(entry["shows"] in set(LinkShows) for entry in worklist)
    shows = {link["key"]: link["shows"] for link in context.deep_links()}
    assert shows["nls-explore-at-point"] == "historic_maps"
    assert shows["nls-side-by-side-lidar"] == "lidar"
    assert shows["ncap-air-photo-finder"] == "aerial_photographs"
    assert shows["he-nhle-list-entry"] == "records"
    assert shows["geograph-photo"] == "photographs"
    items = client.get("/api/v1/context/links", params={"lon": AVEBURY[0], "lat": AVEBURY[1]}).json()["items"]
    assert items
    assert all(item["shows"] == shows[item["key"]] for item in items)


def test_each_link_has_a_name_fit_to_show(client: TestClient) -> None:
    for link in context.deep_links():
        assert "at a point" not in link["title"], link["key"]
        assert link["title"], link["key"]
        assert link["title"].strip() == link["title"], link["key"]
    titles = {link["key"]: link["title"] for link in context.deep_links()}
    assert titles["he-apex-viewer"] == "Historic England Aerial Photo Explorer"
    assert titles["know-your-place-wilts"] == "Know Your Place: Wiltshire"
    items = client.get("/api/v1/context/links", params={"lon": AVEBURY[0], "lat": AVEBURY[1]}).json()["items"]
    assert all(item["title"] == titles[item["key"]] for item in items)
    assert "Google Earth" in {item["title"] for item in items}


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


def test_a_source_with_no_page_for_each_record_is_seen_in_the_viewer_that_holds_its_material() -> None:
    # The names read from the six-inch map: the map itself, at the place the lettering sits.
    url = context.material_url("portsmouth-gb1900-gazetteer", -1.64501, 53.39622)
    assert url == "https://maps.nls.uk/geo/explore/#zoom=16&lat=53.39622&lon=-1.64501&layers=6&b=1"
    # Any other source's records have their own page or none.
    assert context.material_url("he-nhle-scheduled-monuments", -1.64501, 53.39622) is None
    # Every viewer named is a deep link that opens at a point.
    at_a_point = {link["key"] for link in context.deep_links() if link["for_point"]}
    assert {viewer for viewer, _ in context.MATERIAL_VIEWERS.values()} <= at_a_point


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


def test_a_point_on_the_irish_grid_is_not_taken_for_northern_ireland(db: Session) -> None:
    """The Irish Grid covers the whole island, so until the nations are loaded nothing is guessed."""
    assert gridref.to_grid(*DUBLIN)[0] is gridref.GridSystem.IRISH
    assert set(by_key(context.links_for(db, *DUBLIN))) == {"google-earth-web"}
    assert "ncap-air-photo-finder" not in by_key(context.links_for(db, *BELFAST))
    db.add(admin_area("nation", "northern_ireland", "Northern Ireland", (-8.2, 54.0, -5.4, 55.3)))
    db.commit()
    assert "ncap-air-photo-finder" in by_key(context.links_for(db, *BELFAST))
    assert set(by_key(context.links_for(db, *DUBLIN))) == {"google-earth-web"}


def test_a_point_off_the_north_coast_takes_northern_irelands_viewers_only_from_its_boundary(
    db: Session,
) -> None:
    """At sea on the Irish Grid nothing is guessed, but a loaded nation within reach is offered."""
    offshore = (-7.0, 55.35)  # about 6 km north of the box below
    assert gridref.to_grid(*offshore)[0] is gridref.GridSystem.IRISH
    assert set(by_key(context.links_for(db, *offshore))) == {"google-earth-web"}
    db.add(admin_area("nation", "northern_ireland", "Northern Ireland", (-8.2, 54.0, -5.4, 55.3)))
    db.commit()
    assert "ncap-air-photo-finder" in by_key(context.links_for(db, *offshore))


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


def test_each_shown_live_source_says_where_its_credit_goes() -> None:
    """Once for the layer, or beside each record. Where the research didn't say, the stricter."""
    items = {item["key"]: item for item in context.live_sources()}
    for key, item in items.items():
        if item["shown"]:
            assert item["credit_placement"] in {placement.value for placement in CreditPlacement}, key
        else:
            assert item["credit_placement"] is None, key
    # A source whose terms ask for a credit taken from each record shows it beside each record.
    for key, item in items.items():
        if item["credit_field"] is not None:
            assert item["credit_placement"] == CreditPlacement.RECORD, key
    # The research recorded no placement for these, so they take the stricter.
    for key in (
        "dnpa-dartmoor-her",
        "wiltshire-her-monuments",
        "wolverhampton-walsall-her",
        "cambridge-cucap-pois",
    ):
        assert items[key]["credit_placement"] == CreditPlacement.RECORD, key


def test_a_link_says_how_it_was_checked_in_words_meta_gives(client: TestClient) -> None:
    values = {item["verified"] for item in context.deep_links()}
    # The values the catalogue holds are exactly the enum's, so none is served as an unknown string.
    assert values == {value.value for value in LinkVerified}
    words = client.get("/api/v1/meta").json()["vocab"]["link_verified"]
    assert [item["id"] for item in words] == [value.value for value in LinkVerified]
    assert all(item["label"] and item["description"] for item in words)
    schema = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert schema["ContextLink"]["properties"]["verified"] == {"$ref": "#/components/schemas/LinkVerified"}
