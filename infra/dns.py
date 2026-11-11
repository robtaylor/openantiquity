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
again: a record set that already matches is not written, and removals are
made before additions, so a run that stopped half-way is finished by the next.

Two guards against a slip in the file. NS and SOA record sets can't be listed
at all, because they hold the zone together. Replacing or removing an MX
record set, which would stop the domain's mail, needs `apply --allow-mail`.

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
# How many of a zone's records `show` asks for at a time.
PAGE_SIZE = 100

# Record sets that hold the zone together. The file may not list them.
PROTECTED_TYPES = frozenset({"NS", "SOA"})
# Types whose values are host names. Gandi wants each written in full, ending in a dot, and a
# name without one would be read as relative to the zone.
HOST_TYPES = frozenset({"ALIAS", "CNAME", "MX", "SRV"})

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
        if kind.upper() in PROTECTED_TYPES:
            raise DnsError(f"{where} lists a {kind.upper()} record set, which this tool never changes")
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
            if len({_normal(kind.upper(), value) for value in values}) != len(values):
                raise DnsError(f"{where} gives the same value more than once in values")
            if kind.upper() in HOST_TYPES and not all(value.strip().endswith(".") for value in values):
                raise DnsError(f"{where} needs each of its values to be a full host name ending in a dot")
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


def _normal(kind: str, value: str) -> str:
    """A value as it is compared: trimmed, and lower-cased where it is a host name."""
    value = value.strip()
    return value.lower() if kind in HOST_TYPES else value


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


def _ask(
    client: httpx.Client, method: str, path: str, *, missing_ok: bool = False, **kwargs: Any
) -> httpx.Response:
    """One request. A refusal is reported with the status and Gandi's message, never the request."""
    try:
        response = client.request(method, path, **kwargs)
    except httpx.HTTPError as error:
        raise DnsError(f"{method} {path} failed: {type(error).__name__}") from None
    if response.status_code >= 400 and not (missing_ok and response.status_code == 404):
        try:
            message = str(response.json().get("message", ""))
        except ValueError:
            message = ""
        raise DnsError(f"{method} {path} was refused with {response.status_code}: {message[:200]}")
    return response


def _path(wanted: Wanted) -> str:
    return f"/domains/{wanted.domain}/records/{wanted.name}/{wanted.type}"


def _json(response: httpx.Response, method: str, path: str, shape: type) -> Any:
    """The answer's JSON, checked to be the list or object the caller expects."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, shape):
        raise DnsError(f"{method} {path} answered {response.status_code} with something this tool can't read")
    return body


def _check_zones(client: httpx.Client, domains: Sequence[str]) -> None:
    """Stop before anything is compared if a zone isn't there, so a misspelt one is never read as empty."""
    for domain in domains:
        response = _ask(client, "GET", f"/domains/{domain}", missing_ok=True)
        if response.status_code == 404:
            raise DnsError(f"The zone {domain} isn't at Gandi, or this token can't see it")


def _held(client: httpx.Client, wanted: Wanted) -> Held | None:
    response = _ask(client, "GET", _path(wanted), missing_ok=True)
    if response.status_code == 404:
        return None
    body = _json(response, "GET", _path(wanted), dict)
    values = body.get("rrset_values", [])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise DnsError(f"GET {_path(wanted)} answered with values this tool can't read")
    ttl = body.get("rrset_ttl")
    return Held(ttl=ttl if isinstance(ttl, int) else None, values=tuple(values))


def _action(wanted: Wanted, held: Held | None) -> Action:
    if wanted.absent:
        return "same" if held is None else "remove"
    if held is None:
        return "add"
    # A record set's values have no order, and host names no case.
    have = sorted(_normal(wanted.type, value) for value in held.values)
    want = sorted(_normal(wanted.type, value) for value in wanted.values)
    # Where Gandi doesn't say what the time to live is, there is nothing to compare it with.
    same_ttl = held.ttl is None or held.ttl == wanted.ttl
    return "same" if have == want and same_ttl else "replace"


def plan(client: httpx.Client, wanted: Sequence[Wanted]) -> list[Change]:
    """Compare each listed record set with what Gandi holds. Reads only."""
    _check_zones(client, sorted({record.domain for record in wanted}))
    changes: list[Change] = []
    for record in wanted:
        held = _held(client, record)
        changes.append(Change(wanted=record, held=held, action=_action(record, held)))
    return changes


def apply(client: httpx.Client, changes: Sequence[Change], *, allow_mail: bool = False) -> None:
    """Write each record set the plan says differs, and nothing else.

    Removals go first. A CNAME can't share a name with another type, so moving a name from one
    to the other only works in that order, and a run that failed half-way is finished by the next.
    """
    differing = [change for change in changes if change.action != "same"]
    mail = [change.wanted for change in differing if change.wanted.type == "MX" and change.action != "add"]
    if mail and not allow_mail:
        names = ", ".join(f"{record.name} MX in {record.domain}" for record in mail)
        raise DnsError(f"This would replace or remove mail records ({names}). To do that, add --allow-mail")
    for change in differing:
        if change.action == "remove":
            _ask(client, "DELETE", _path(change.wanted))
    for change in differing:
        if change.action in ("add", "replace"):
            record = change.wanted
            body = {"rrset_ttl": record.ttl, "rrset_values": list(record.values)}
            _ask(client, "PUT", _path(record), json=body)


def _line(change: Change) -> str:
    record = change.wanted
    mark = {"add": "+", "replace": "~", "remove": "-", "same": "="}[change.action]
    now = "absent" if record.absent else f"{record.ttl}  {', '.join(record.values)}"
    line = f"{mark} {record.domain:<22} {record.name:<12} {record.type:<6} {now}"
    if change.action in ("replace", "remove") and change.held is not None:
        line += f"\n    was: {change.held.ttl}  {', '.join(change.held.values)}"
    return line


def _show(client: httpx.Client, domains: Sequence[str]) -> None:
    _check_zones(client, domains)
    for domain in domains:
        print(f"== {domain}")
        path = f"/domains/{domain}/records"
        # Gandi sends a zone's records a page at a time.
        page = 1
        while True:
            answer = _ask(client, "GET", path, params={"page": page, "per_page": PAGE_SIZE})
            items = _json(answer, "GET", path, list)
            for item in items:
                if not isinstance(item, dict):
                    raise DnsError(f"GET {path} answered with a record this tool can't read")
                values = ", ".join(str(value) for value in item.get("rrset_values", []))
                name, kind = item.get("rrset_name", ""), item.get("rrset_type", "")
                print(f"   {name:<22} {kind:<6} {item.get('rrset_ttl', '')!s:<7} {values}")
            if len(items) < PAGE_SIZE:
                break
            page += 1


def main(argv: Sequence[str] | None = None, client: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make the DNS zones at Gandi match the records file.")
    parser.add_argument("command", choices=["show", "plan", "apply"])
    parser.add_argument(
        "--records", type=Path, default=RECORDS, help="the records file (default: infra/dns.toml)"
    )
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env", help="where the token is kept")
    parser.add_argument(
        "--allow-mail", action="store_true", help="let apply replace or remove MX record sets"
    )
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
            apply(client, changes, allow_mail=args.allow_mail)
            print(f"{len(differing)} record set(s) changed.")
        else:
            print(f"{len(differing)} record set(s) would change.")
    except DnsError as error:
        print(f"dns: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
