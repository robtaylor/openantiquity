from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from fieldclub.ingest.connectors import (
    bern_xronos_radiocarbon,
    datacite_ads_dois,
    isaw_pleiades_places,
    ribonline_rib_sites,
)

# Each connector's gap between requests. The tests don't wait.
DELAYS = (datacite_ads_dois, bern_xronos_radiocarbon, ribonline_rib_sites, isaw_pleiades_places)


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    """Each test downloads into its own `var/`, so no test sees another's cached download."""
    env(VAR_DIR=str(tmp_path / "var"))


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in DELAYS:
        monkeypatch.setattr(module, "DELAY_S", 0.0)
