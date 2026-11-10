"""The tile catalogue: names, bounds and coverage, known without a network call."""

from __future__ import annotations

import pytest

from fieldclub.terrain.catalogue import (
    TileNameError,
    england_catalogue,
    normalise_name,
    tile_name_at,
    tile_origin,
)


def test_the_england_catalogue_lists_every_tile_in_the_supply() -> None:
    catalogue = england_catalogue()
    assert len(catalogue) == 5_877
    assert catalogue.total_bytes == pytest.approx(353.6e9, rel=0.001)
    su16nw = catalogue.get("SU16nw")
    assert su16nw is not None
    assert su16nw.size == 48_197_942
    assert su16nw.remote_path == "composite/2022/GeoTiffs/1m/DTM/SU16nw_DTM_1m.tif"


def test_tile_names_give_their_bounds() -> None:
    assert tile_origin("SU16nw") == (410_000, 165_000)
    assert tile_origin("su16SE") == (415_000, 160_000)
    tile = england_catalogue().get("SU16nw")
    assert tile is not None
    assert tile.bounds == (410_000, 165_000, 415_000, 170_000)


def test_names_round_trip_through_positions() -> None:
    for name in ("SU16nw", "SU16ne", "SU16sw", "SU16se", "TQ38sw", "NZ27ne"):
        west, south = tile_origin(name)
        assert tile_name_at(west + 1, south + 1) == name
        assert tile_name_at(west + 4_999.9, south + 4_999.9) == name


@pytest.mark.parametrize("name", ["SU16", "SU16xx", "S16nw", "SU1nw", "../SU16nw", "J33nw"])
def test_anything_that_is_not_a_tile_name_is_refused(name: str) -> None:
    with pytest.raises(TileNameError):
        tile_origin(name)


def test_normalising_names() -> None:
    assert normalise_name(" su16NW ") == "SU16nw"


def test_covering_returns_only_listed_tiles() -> None:
    catalogue = england_catalogue()
    # Avebury and the sea off Land's End.
    names = {tile.name for tile in catalogue.covering((409_000, 168_000, 411_000, 171_000))}
    assert names == {"SU06ne", "SU16nw", "SU07se", "SU17sw"}
    assert catalogue.covering((100_000, 10_000, 105_000, 15_000)) == []
    assert "SU16nw" in catalogue
    assert "SV00sw" not in catalogue
