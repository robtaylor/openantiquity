"""A line as long and as detailed as the limits allow saves quickly and costs a map view little.

The road runs about 586 km north from the south coast through 5,000 smooth
points, bending gently, as a finder following Watling Street at every bend
might draw it. Saving it derives, checks and simplifies the whole shape, and
the map at zoom 9 gets its coarsest copy cut to the box.

The save is timed as the fastest of five, as the other performance tests time
a query. One save on a shared machine measures the machine as much as the
code: a save that takes a third of a second here once took 1.04 s in CI.
"""

from __future__ import annotations

import math
import time

from fastapi.testclient import TestClient

from fieldclub.services import shapes
from tests.findings.support import API
from tests.helpers import ClientAs, MakeUser

POINTS = shapes.PATH_MAX_POINTS
SOUTH, NORTH = 50.75, 56.0
# The plan's figures.
SAVE_BUDGET_S = 1.0
ZOOM_9_BUDGET_BYTES = 50_000
SAVES = 5


def _road() -> dict:
    points = []
    for i in range(POINTS):
        lat = SOUTH + (NORTH - SOUTH) * i / (POINTS - 1)
        # Bends a few kilometres across, every hundred kilometres or so.
        lon = -2.0 + 0.03 * math.sin(lat * 6) + 0.0001 * math.sin(i)
        points.append({"lon": round(lon, 7), "lat": round(lat, 7), "kind": "smooth"})
    return {"closed": False, "points": points}


def _save(client: TestClient) -> float:
    """Save the road as a new finding and say how many seconds it took."""
    body = {"feature_class": "road", "path": _road()}
    started = time.perf_counter()
    made = client.post(f"{API}/findings", json=body)
    saved_in = time.perf_counter() - started
    assert made.status_code == 201, made.text
    assert 550_000 < made.json()["location"]["shape"]["length_m"] <= shapes.LINE_MAX_LENGTH_M
    return saved_in


def test_a_5000_point_600_km_line_saves_in_a_second(client_as: ClientAs, make_user: MakeUser) -> None:
    fastest = min(_save(client_as(make_user())) for _ in range(SAVES))
    assert fastest < SAVE_BUDGET_S, f"the fastest of {SAVES} saves took {fastest:.2f} s"


def test_a_5000_point_600_km_line_draws_at_zoom_9_in_50_kb(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user())
    _save(client)

    # The whole road in one view, the worst a zoom 9 view can ask for.
    whole = f"-2.2,{SOUTH - 0.05},-1.8,{NORTH + 0.05}"
    drawn = client.get(f"{API}/findings", params={"format": "geojson", "bbox": whole, "zoom": 9})
    assert drawn.status_code == 200
    (feature,) = drawn.json()["features"]
    assert feature["properties"]["shape"]["type"] in ("LineString", "MultiLineString")
    assert len(drawn.content) < ZOOM_9_BUDGET_BYTES, f"zoom 9 sent {len(drawn.content):,} bytes"
