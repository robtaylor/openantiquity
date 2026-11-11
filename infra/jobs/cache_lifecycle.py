# ruff: noqa: T201 - a command-line tool: what it prints is its output
"""Give the tile cache bucket its expiry rule, through the S3 lifecycle interface.

    python /app/jobs/cache_lifecycle.py [--check]

Run on a machine of the web app, which holds the cache bucket's key
(infra/README.md):

    fly ssh console -a openantiquity -C "python /app/jobs/cache_lifecycle.py"

A rendered tile's key carries its style and data version, so after a style
change the old tiles are never asked for again. Half a year without being
rewritten is a fair sign of that, and a tile still wanted is rendered again in
about 0.2 s, so tiles are deleted 180 days after they were written. Nothing else
is kept in the cache bucket. Photos have a bucket of their own and no rule.

The bucket is FIELDCLUB_S3_BUCKET and the tiles are under FIELDCLUB_S3_PREFIX,
as the service stores them (`fieldclub.storage.get_storage("tiles")`). The
bucket's whole lifecycle configuration is replaced by these rules, so the
script is safe to run again. It reads the rules back and prints them. With
`--check` it only reads them, and exits 1 when they differ.

Tigris accepts only an ID, a status, a prefix filter and an expiry in days in a
rule (its object lifecycle rules page), so nothing else is sent.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from fieldclub.config import get_settings
from fieldclub.storage import s3_client

TILE_DAYS = 180


def wanted_rules(prefix: str) -> list[dict[str, Any]]:
    tiles = "/".join(part for part in (prefix.strip("/"), "tiles") if part) + "/"
    return [
        {
            "ID": "tiles-180-days",
            "Status": "Enabled",
            "Filter": {"Prefix": tiles},
            "Expiration": {"Days": TILE_DAYS},
        }
    ]


def current_rules(client: Any, bucket: str) -> list[dict[str, Any]]:
    from botocore.exceptions import ClientError

    try:
        answer = client.get_bucket_lifecycle_configuration(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "NoSuchLifecycleConfiguration":
            return []
        raise
    return [_essentials(rule) for rule in answer.get("Rules", [])]


def _essentials(rule: dict[str, Any]) -> dict[str, Any]:
    """The parts of a rule this script sets, as it sets them, whatever else the store adds."""
    return {
        "ID": rule.get("ID"),
        "Status": rule.get("Status"),
        "Filter": {"Prefix": (rule.get("Filter") or {}).get("Prefix")},
        "Expiration": {"Days": (rule.get("Expiration") or {}).get("Days")},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Give the tile cache bucket its expiry rule.")
    parser.add_argument(
        "--check", action="store_true", help="only read the rules, and exit 1 when they differ"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    if settings.storage_backend != "s3" or not settings.s3_bucket:
        sys.exit("FIELDCLUB_STORAGE_BACKEND is not s3, so there is no cache bucket to give a rule to.")
    bucket = settings.s3_bucket
    rules = wanted_rules(settings.s3_prefix)
    client = s3_client()
    if not args.check:
        client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={"Rules": rules})
    found = current_rules(client, bucket)
    print(f"{bucket}: {json.dumps(found, sort_keys=True)}")
    if found != rules:
        print(
            f"{bucket} does not have the rules wanted: {json.dumps(rules, sort_keys=True)}", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
