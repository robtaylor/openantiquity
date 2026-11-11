"""`infra/dns.py` makes the zones at Gandi match `infra/dns.toml`, touching only what the file lists.

The tool is loaded from its file and run against a stand-in for Gandi's LiveDNS API that keeps
its zones in memory.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TOKEN = "pat-not-a-real-token-51d2"

Zone = dict[tuple[str, str], dict[str, Any]]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("infra_dns", REPO_ROOT / "infra" / "dns.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses look their module up by name while it is still being run.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dns = _load()


class FakeGandi:
    """LiveDNS, as far as the tool uses it: one record set read, replaced or deleted at a time."""

    def __init__(self, zones: dict[str, Zone]) -> None:
        self.zones = zones
        self.calls: list[tuple[str, str]] = []
        self.tokens: set[str] = set()
        self.refuse: int | None = None

    def client(self) -> httpx.Client:
        return dns.gandi_client(TOKEN, transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        self.tokens.add(request.headers.get("Authorization", ""))
        if self.refuse is not None:
            body = {"code": self.refuse, "message": "Permission denied to change the zone"}
            return httpx.Response(self.refuse, json=body)
        parts = request.url.path.removeprefix("/v5/livedns/domains/").split("/")
        domain, rest = parts[0], parts[1:]
        zone = self.zones.get(domain)
        if zone is None:
            return httpx.Response(404, json={"message": "The resource could not be found."})
        if rest == ["records"] and request.method == "GET":
            items = [
                {"rrset_name": name, "rrset_type": kind, **record}
                for (name, kind), record in sorted(zone.items())
            ]
            return httpx.Response(200, json=items)
        assert len(rest) == 3, request.url.path
        assert rest[0] == "records", request.url.path
        key = (rest[1], rest[2])
        if request.method == "GET":
            if key not in zone:
                return httpx.Response(404, json={"message": "Can't find the DNS record"})
            return httpx.Response(200, json={"rrset_name": key[0], "rrset_type": key[1], **zone[key]})
        if request.method == "PUT":
            sent = json.loads(request.content)
            zone[key] = {"rrset_ttl": sent["rrset_ttl"], "rrset_values": sent["rrset_values"]}
            return httpx.Response(201, json={"message": "DNS Record Created"})
        if request.method == "DELETE":
            del zone[key]
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    def writes(self) -> list[tuple[str, str]]:
        return [call for call in self.calls if call[0] != "GET"]


def held(ttl: int, *values: str) -> dict[str, Any]:
    return {"rrset_ttl": ttl, "rrset_values": list(values)}


@pytest.fixture
def gandi() -> FakeGandi:
    return FakeGandi(
        {
            "example.org": {
                ("@", "A"): held(10800, "203.0.113.9"),
                ("@", "MX"): held(10800, "10 spool.mail.example.", "50 fb.mail.example."),
                ("www", "CNAME"): held(10800, "parking.example."),
            },
            "example.net": {("@", "A"): held(10800, "203.0.113.9")},
        }
    )


def records(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "dns.toml"
    path.write_text(text)
    return path


WANTED = """
[[record]]
domains = ["example.org", "example.net"]
name = "@"
type = "A"
ttl = 300
values = ["198.51.100.7"]

[[record]]
domains = ["example.org"]
name = "@"
type = "CAA"
ttl = 3600
values = ['0 issue "pki.goog"', '0 issue "letsencrypt.org"']

[[record]]
domains = ["example.org"]
name = "www"
type = "CNAME"
absent = true
"""


def test_the_plan_says_what_would_be_added_replaced_and_removed(gandi: FakeGandi, tmp_path: Path) -> None:
    wanted = dns.load(records(tmp_path, WANTED))

    plan = dns.plan(gandi.client(), wanted)

    said = [(change.action, change.wanted.domain, change.wanted.name, change.wanted.type) for change in plan]
    assert said == [
        ("replace", "example.org", "@", "A"),
        ("replace", "example.net", "@", "A"),
        ("add", "example.org", "@", "CAA"),
        ("remove", "example.org", "www", "CNAME"),
    ]
    assert gandi.writes() == []


def test_apply_makes_the_zones_match_and_a_second_run_changes_nothing(
    gandi: FakeGandi, tmp_path: Path
) -> None:
    wanted = dns.load(records(tmp_path, WANTED))

    dns.apply(gandi.client(), dns.plan(gandi.client(), wanted))

    org = gandi.zones["example.org"]
    assert org[("@", "A")] == held(300, "198.51.100.7")
    assert org[("@", "CAA")] == held(3600, '0 issue "pki.goog"', '0 issue "letsencrypt.org"')
    assert ("www", "CNAME") not in org
    assert gandi.zones["example.net"][("@", "A")] == held(300, "198.51.100.7")

    gandi.calls.clear()
    again = dns.plan(gandi.client(), wanted)
    dns.apply(gandi.client(), again)
    assert {change.action for change in again} == {"same"}
    assert gandi.writes() == []


def test_a_record_the_file_does_not_list_is_never_touched(gandi: FakeGandi, tmp_path: Path) -> None:
    wanted = dns.load(records(tmp_path, WANTED))

    dns.apply(gandi.client(), dns.plan(gandi.client(), wanted))

    mail = gandi.zones["example.org"][("@", "MX")]
    assert mail == held(10800, "10 spool.mail.example.", "50 fb.mail.example.")
    assert not [call for call in gandi.calls if call[1].endswith("/MX")]


def test_the_same_values_in_another_order_are_not_a_change(gandi: FakeGandi, tmp_path: Path) -> None:
    text = """
[[record]]
domains = ["example.org"]
name = "@"
type = "MX"
ttl = 10800
values = ["50 fb.mail.example.", "10 spool.mail.example."]
"""
    plan = dns.plan(gandi.client(), dns.load(records(tmp_path, text)))

    assert [change.action for change in plan] == ["same"]


def test_removing_what_is_not_there_is_not_a_change(gandi: FakeGandi, tmp_path: Path) -> None:
    text = """
[[record]]
domains = ["example.net"]
name = "www"
type = "CNAME"
absent = true
"""
    plan = dns.plan(gandi.client(), dns.load(records(tmp_path, text)))

    assert [change.action for change in plan] == ["same"]


def test_every_request_carries_the_token_and_a_refusal_never_repeats_it(
    gandi: FakeGandi, tmp_path: Path
) -> None:
    wanted = dns.load(records(tmp_path, WANTED))
    plan = dns.plan(gandi.client(), wanted)
    assert gandi.tokens == {f"Bearer {TOKEN}"}

    gandi.refuse = 403
    with pytest.raises(dns.DnsError) as refused:
        dns.apply(gandi.client(), plan)

    assert "403" in str(refused.value)
    assert "Permission denied" in str(refused.value)
    assert TOKEN not in str(refused.value)
    assert TOKEN not in repr(refused.value)


def test_the_token_is_read_from_the_env_file_and_a_missing_one_is_named(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"OTHER=1\nGANDI_DNS_SSL={TOKEN}\n")
    assert dns.read_token(env_file, environ={}) == TOKEN
    assert (
        dns.read_token(env_file, environ={"GANDI_DNS_SSL": "from-the-environment"}) == "from-the-environment"
    )

    env_file.write_text("OTHER=1\n")
    with pytest.raises(dns.DnsError, match="GANDI_DNS_SSL"):
        dns.read_token(env_file, environ={})


def _record(**fields: str) -> str:
    """One record in the file's own form, with `fields` replacing or adding lines."""
    lines = {
        "domains": '["example.org"]',
        "name": '"@"',
        "type": '"A"',
        "ttl": "300",
        "values": '["198.51.100.7"]',
    }
    lines.update(fields)
    return "[[record]]\n" + "".join(f"{key} = {value}\n" for key, value in lines.items() if value)


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        (_record(ttl="60"), "ttl"),
        (_record(values="[]"), "values"),
        (_record(absent="true", ttl=""), "absent"),
        (_record(domains="[]"), "domains"),
        (_record(value='"x"'), "value"),
    ],
)
def test_a_record_the_file_gets_wrong_is_refused_before_anything_is_asked(
    tmp_path: Path, text: str, complaint: str
) -> None:
    with pytest.raises(dns.DnsError, match=complaint):
        dns.load(records(tmp_path, text))


def test_the_same_record_set_listed_twice_is_refused(tmp_path: Path) -> None:
    text = WANTED + _record(domains='["example.net"]', values='["198.51.100.8"]')

    with pytest.raises(dns.DnsError, match="twice"):
        dns.load(records(tmp_path, text))


def test_the_command_prints_the_plan_and_changes_nothing(
    gandi: FakeGandi, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = records(tmp_path, WANTED)

    status = dns.main(["plan", "--records", str(path)], client=gandi.client())

    printed = capsys.readouterr().out
    assert status == 0
    assert "example.org" in printed
    assert "CAA" in printed
    assert "198.51.100.7" in printed
    assert TOKEN not in printed
    assert gandi.writes() == []


def test_the_repository_s_own_records_file_is_valid() -> None:
    wanted = dns.load(REPO_ROOT / "infra" / "dns.toml")

    assert wanted
    assert {record.domain for record in wanted} <= {
        "openantiquity.org",
        "openantiquity.com",
        "openantiquity.co.uk",
    }
