#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27", "python-dotenv>=1.0"]
# ///
# ruff: noqa: T201 - a command-line tool: what it prints is its output
"""Make the project's DNS zones at Gandi match `infra/dns.toml`.

    uv run infra/dns.py show     every record in each zone the file names
    uv run infra/dns.py plan     what apply would change
    uv run infra/dns.py apply    change it

Only the record sets the file lists are read or written. Everything else in a
zone, such as Gandi's own mail records, is left as it is. A record set is one
name and type with all its values, and apply replaces it whole. Safe to run
again: a record set that already matches is not written.

The token is Gandi's personal access token for these domains, read from
`GANDI_DNS_SSL` in the environment or in the untracked `.env` at the repository
root. It goes into the request header and nowhere else: it is never printed,
and a refusal is reported with Gandi's own message only.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import dotenv_values

API = "https://api.gandi.net/v5/livedns"
TOKEN_VAR = "GANDI_DNS_SSL"
# Gandi's own limits for a record set's time to live.
MIN_TTL = 300
MAX_TTL = 2_592_000

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDS = Path(__file__).resolve().with_name("dns.toml")

Action = Literal["add", "replace", "remove", "same"]


class DnsError(Exception):
    """The records file is wrong, the token is missing, or Gandi refused a request."""


@dataclass(frozen=True)
class Wanted:
    """One record set as the file wants it: present with these values, or absent."""

    domain: str
    name: str
    type: str
    ttl: int | None
    values: tuple[str, ...]
    absent: bool


@dataclass(frozen=True)
class Held:
    """One record set as Gandi holds it."""

    ttl: int | None
    values: tuple[str, ...]


@dataclass(frozen=True)
class Change:
    wanted: Wanted
    held: Held | None
    action: Action


_KEYS = {"domains", "name", "type", "ttl", "values", "absent"}


def load(path: Path) -> list[Wanted]:
    """Read and check the records file. Nothing is asked of Gandi here."""
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DnsError(f"Can't read {path}: {error}") from error
    wanted: list[Wanted] = []
    seen: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(data.get("record", []), start=1):
        where = f"record {index} in {path.name}"
        unknown = set(entry) - _KEYS
        if unknown:
            raise DnsError(f"{where} has a key the tool doesn't know: {', '.join(sorted(unknown))}")
        domains = entry.get("domains")
        if not isinstance(domains, list) or not domains or not all(isinstance(d, str) and d for d in domains):
            raise DnsError(f"{where} needs domains, a list of at least one zone")
        name, kind = entry.get("name"), entry.get("type")
        if not isinstance(name, str) or not name or not isinstance(kind, str) or not kind:
            raise DnsError(f"{where} needs a name and a type")
        absent = entry.get("absent", False)
        values = entry.get("values", [])
        ttl = entry.get("ttl")
        if absent:
            if values or ttl is not None:
                raise DnsError(f"{where} is marked absent, so it can't also give values or a ttl")
        else:
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(v, str) and v.strip() for v in values)
            ):
                raise DnsError(f"{where} needs values, a list of at least one string")
            if not isinstance(ttl, int) or not MIN_TTL <= ttl <= MAX_TTL:
                raise DnsError(f"{where} needs a ttl between {MIN_TTL} and {MAX_TTL} seconds")
        for domain in domains:
            key = (domain, name, kind.upper())
            if key in seen:
                raise DnsError(f"{where} lists {name} {kind.upper()} for {domain}, which is listed twice")
            seen.add(key)
            wanted.append(
                Wanted(
                    domain=domain,
                    name=name,
                    type=kind.upper(),
                    ttl=None if absent else ttl,
                    values=tuple(v.strip() for v in values),
                    absent=bool(absent),
                )
            )
    if not wanted:
        raise DnsError(f"{path} lists no records")
    return wanted


def read_token(env_file: Path, environ: Mapping[str, str] | None = None) -> str:
    """The token from the environment, or else from the env file. It is never printed."""
    environ = os.environ if environ is None else environ
    token = environ.get(TOKEN_VAR) or dotenv_values(env_file).get(TOKEN_VAR)
    if not token:
        raise DnsError(f"{TOKEN_VAR} is not set in the environment or in {env_file}")
    return token


def gandi_client(token: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "openantiquity-infra"},
        timeout=30,
        transport=transport,
    )


def _ask(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    """One request. A refusal is reported with the status and Gandi's message, never the request."""
    try:
        response = client.request(method, path, **kwargs)
    except httpx.HTTPError as error:
        raise DnsError(f"{method} {path} failed: {type(error).__name__}") from None
    if response.status_code >= 400 and not (method == "GET" and response.status_code == 404):
        try:
            message = str(response.json().get("message", ""))
        except ValueError:
            message = ""
        raise DnsError(f"{method} {path} was refused with {response.status_code}: {message[:200]}")
    return response


def _path(wanted: Wanted) -> str:
    return f"/domains/{wanted.domain}/records/{wanted.name}/{wanted.type}"


def _held(client: httpx.Client, wanted: Wanted) -> Held | None:
    response = _ask(client, "GET", _path(wanted))
    if response.status_code == 404:
        return None
    body = response.json()
    return Held(ttl=body.get("rrset_ttl"), values=tuple(body.get("rrset_values", [])))


def _action(wanted: Wanted, held: Held | None) -> Action:
    if wanted.absent:
        return "same" if held is None else "remove"
    if held is None:
        return "add"
    # A record set's values have no order.
    same = sorted(held.values) == sorted(wanted.values) and held.ttl == wanted.ttl
    return "same" if same else "replace"


def plan(client: httpx.Client, wanted: Sequence[Wanted]) -> list[Change]:
    """Compare each listed record set with what Gandi holds. Reads only."""
    changes: list[Change] = []
    for record in wanted:
        held = _held(client, record)
        changes.append(Change(wanted=record, held=held, action=_action(record, held)))
    return changes


def apply(client: httpx.Client, changes: Sequence[Change]) -> None:
    """Write each record set the plan says differs, and nothing else."""
    for change in changes:
        record = change.wanted
        if change.action in ("add", "replace"):
            body = {"rrset_ttl": record.ttl, "rrset_values": list(record.values)}
            _ask(client, "PUT", _path(record), json=body)
        elif change.action == "remove":
            _ask(client, "DELETE", _path(record))


def _line(change: Change) -> str:
    record = change.wanted
    mark = {"add": "+", "replace": "~", "remove": "-", "same": "="}[change.action]
    now = "absent" if record.absent else f"{record.ttl}  {', '.join(record.values)}"
    line = f"{mark} {record.domain:<22} {record.name:<12} {record.type:<6} {now}"
    if change.action in ("replace", "remove") and change.held is not None:
        line += f"\n    was: {change.held.ttl}  {', '.join(change.held.values)}"
    return line


def _show(client: httpx.Client, domains: Sequence[str]) -> None:
    for domain in domains:
        print(f"== {domain}")
        for item in _ask(client, "GET", f"/domains/{domain}/records").json():
            values = ", ".join(item.get("rrset_values", []))
            print(
                f"   {item['rrset_name']:<22} {item['rrset_type']:<6} {item.get('rrset_ttl', ''):<7} {values}"
            )


def main(argv: Sequence[str] | None = None, client: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make the DNS zones at Gandi match the records file.")
    parser.add_argument("command", choices=["show", "plan", "apply"])
    parser.add_argument(
        "--records", type=Path, default=RECORDS, help="the records file (default: infra/dns.toml)"
    )
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env", help="where the token is kept")
    args = parser.parse_args(argv)
    try:
        wanted = load(args.records)
        client = client or gandi_client(read_token(args.env_file))
        if args.command == "show":
            _show(client, sorted({record.domain for record in wanted}))
            return 0
        changes = plan(client, wanted)
        for change in changes:
            print(_line(change))
        differing = [change for change in changes if change.action != "same"]
        if args.command == "apply":
            apply(client, changes)
            print(f"{len(differing)} record set(s) changed.")
        else:
            print(f"{len(differing)} record set(s) would change.")
    except DnsError as error:
        print(f"dns: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
