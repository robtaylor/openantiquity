"""The frontend's copy of the API's path templates matches the app's own.

A kept failure in the browser names its path by these templates
(`frontend/src/api/failures.ts`), so a route added here without them would
be written there by its words alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fieldclub.main import API_PREFIX, create_app

PATHS_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "paths.ts"


def test_the_frontend_s_path_templates_are_the_app_s() -> None:
    schema = create_app(include_dev_routes=True).openapi()
    served = sorted(
        path.removeprefix(API_PREFIX) for path in schema["paths"] if path.startswith(f"{API_PREFIX}/")
    )
    listed = [
        json.loads(found) for found in re.findall(r'^\s+("[^"]*"),$', PATHS_TS.read_text(), re.MULTILINE)
    ]
    assert listed == served, "frontend/src/api/paths.ts is out of date: run `pnpm gen:api` in frontend/"
