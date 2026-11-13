"""The moderators' level route gives a finding's position to moderators only (Decision 0005).

It answers with the finding's page, so it is tried as every kind of viewer
against every level, with the world `tests/findings/test_leaks.py` builds.
"""

from __future__ import annotations

import pytest

from fieldclub.vocab import Sensitivity
from tests.findings import test_leaks as leaks
from tests.helpers import error_code
from tests.moderation.support import API, REASON

world = leaks.world

REFUSED = {
    "signed_out": (401, "unauthorised"),
    "member": (403, "moderators_only"),
    "finder": (403, "moderators_only"),
    "trusted": (403, "moderators_only"),
}


@pytest.mark.parametrize("viewer", leaks.VIEWERS)
@pytest.mark.parametrize("level", leaks.LEVELS)
@pytest.mark.parametrize("kind", leaks.KINDS)
def test_the_moderators_level_route_answers_only_moderators(
    world: leaks.World, viewer: str, level: Sensitivity, kind: str
) -> None:
    finding = world.of(kind, level)
    response = world.client(viewer).put(
        f"{API}/mod/findings/{finding.public_id}/sensitivity", json={"level": level.value, **REASON}
    )
    where = f"PUT /mod/findings/{{id}}/sensitivity as {viewer} ({level})"
    if viewer == "moderator":
        assert response.status_code == 200, response.text
        leaks.check(response.text, leaks.SEES[viewer], {level}, where=where)
        assert response.json()["location"]["obscured"] is False
    else:
        assert (response.status_code, error_code(response)) == REFUSED[viewer], where
        leaks.check(response.text, set(), where=where)
    assert response.headers["cache-control"] == "private, no-cache"
