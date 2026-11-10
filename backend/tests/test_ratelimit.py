"""Token buckets, alone and as a FastAPI dependency."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import Depends, FastAPI, Request
from sqlalchemy.orm import Session

from fieldclub import ratelimit
from fieldclub.errors import RateLimitedError, install_error_handlers
from fieldclub.ratelimit import RateLimiter, address_key, rate_limit
from tests.helpers import ClientFor, MakeUser


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_a_bucket_allows_its_capacity_then_refuses(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=3, per_seconds=60, clock=clock)
    for _ in range(3):
        limiter.hit("alice")
    with pytest.raises(RateLimitedError) as caught:
        limiter.hit("alice")
    assert caught.value.status_code == 429
    assert caught.value.code == "rate_limited"
    assert caught.value.retry_after_s == pytest.approx(20.0)
    assert caught.value.headers == {"Retry-After": "20"}


def test_keys_have_separate_buckets(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=1, per_seconds=60, clock=clock)
    limiter.hit("alice")
    limiter.hit("bob")
    with pytest.raises(RateLimitedError):
        limiter.hit("alice")


def test_tokens_refill_steadily_and_never_beyond_capacity(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=4, per_seconds=40, clock=clock)
    for _ in range(4):
        limiter.hit("alice")
    clock.advance(9.9)
    with pytest.raises(RateLimitedError):
        limiter.hit("alice")
    clock.advance(0.2)
    limiter.hit("alice")
    clock.advance(10_000)
    assert limiter.remaining("alice") == pytest.approx(4.0)
    for _ in range(4):
        limiter.hit("alice")
    with pytest.raises(RateLimitedError):
        limiter.hit("alice")


def test_a_refused_request_costs_nothing(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=1, per_seconds=10, clock=clock)
    limiter.hit("alice")
    for _ in range(50):
        with pytest.raises(RateLimitedError):
            limiter.hit("alice")
    clock.advance(10)
    limiter.hit("alice")


def test_retry_after_rounds_up_to_a_whole_second(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=10, per_seconds=1, clock=clock)
    for _ in range(10):
        limiter.hit("alice")
    with pytest.raises(RateLimitedError) as caught:
        limiter.hit("alice")
    assert caught.value.headers == {"Retry-After": "1"}


def test_cost(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=5, per_seconds=50, clock=clock)
    limiter.hit("alice", cost=4)
    with pytest.raises(RateLimitedError):
        limiter.hit("alice", cost=2)
    limiter.hit("alice", cost=1)


def test_idle_buckets_are_pruned_so_memory_is_bounded(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=2, per_seconds=10, clock=clock, max_keys=100)
    for index in range(100):
        limiter.hit(f"ip:{index}")
    assert len(limiter) == 100
    clock.advance(11)
    limiter.hit("ip:new")
    assert len(limiter) == 1


def test_a_flood_of_live_keys_keeps_memory_bounded(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=2, per_seconds=10, clock=clock, max_keys=50)
    for index in range(120):
        limiter.hit(f"ip:{index}")
    assert len(limiter) == 50


def test_a_flood_of_new_keys_does_not_reset_anyone_elses_limit(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=2, per_seconds=3600, clock=clock, max_keys=50)
    for index in range(49):
        limiter.hit(f"ip:{index}")
        clock.advance(0.01)
    limiter.hit("victim")
    limiter.hit("victim")
    with pytest.raises(RateLimitedError):
        limiter.hit("victim")

    # The table is full of live keys. More arrive, fewer than the table holds.
    for index in range(49):
        clock.advance(0.01)
        limiter.hit(f"flood:{index}")
    assert len(limiter) == 50
    with pytest.raises(RateLimitedError):
        limiter.hit("victim")
    assert limiter.remaining("victim") < 1.0


def test_only_the_key_used_longest_ago_is_forgotten(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=1, per_seconds=3600, clock=clock, max_keys=3)
    for key in ("a", "b", "c"):
        limiter.hit(key)
        clock.advance(1)
    # Using "a" again, even when refused, makes it the most recent.
    with pytest.raises(RateLimitedError):
        limiter.hit("a")
    clock.advance(1)
    limiter.hit("d")
    assert len(limiter) == 3
    assert limiter.remaining("b") == pytest.approx(1.0), "b was the oldest, and was forgotten"
    for key in ("a", "c", "d"):
        assert limiter.remaining(key) < 1.0, key


def test_refilled_buckets_go_before_live_ones(clock: FakeClock) -> None:
    limiter = RateLimiter("test", capacity=1, per_seconds=10, clock=clock, max_keys=3)
    limiter.hit("old-1")
    limiter.hit("old-2")
    clock.advance(11)
    limiter.hit("live")
    clock.advance(1)
    limiter.hit("new")
    assert len(limiter) == 2
    with pytest.raises(RateLimitedError):
        limiter.hit("live")


def test_bad_parameters_are_refused() -> None:
    with pytest.raises(AssertionError):
        RateLimiter("test", capacity=0, per_seconds=1)
    with pytest.raises(AssertionError):
        RateLimiter("test", capacity=1, per_seconds=0)
    limiter = RateLimiter("test", capacity=1, per_seconds=1)
    with pytest.raises(AssertionError):
        limiter.hit("alice", cost=2)


def test_named_limiters_are_shared_and_must_agree() -> None:
    first = ratelimit.get_limiter("test_shared", 5, 60)
    assert ratelimit.get_limiter("test_shared", 5, 60) is first
    with pytest.raises(AssertionError, match="different limits"):
        ratelimit.get_limiter("test_shared", 6, 60)


# --------------------------------------------------------------------------
# Which address a caller is counted under
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ip", "key"),
    [
        ("203.0.113.5", "203.0.113.5"),
        (" 203.0.113.5 ", "203.0.113.5"),
        ("2001:db8:1:2::1", "2001:db8:1:2::"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::"),
        ("2001:0DB8:0001:0002:abcd::1", "2001:db8:1:2::"),
        ("2001:db8:1:3::1", "2001:db8:1:3::"),
        ("::ffff:203.0.113.5", "203.0.113.5"),
        ("::1", "::"),
        ("testclient", "testclient"),
        ("not an address", "not an address"),
    ],
)
def test_address_key(ip: str, key: str) -> None:
    assert address_key(ip) == key


# --------------------------------------------------------------------------
# As a dependency
# --------------------------------------------------------------------------


@pytest.fixture
def limited_app(db: Session, limits_on: None) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/thing", dependencies=[Depends(rate_limit("test_thing", 2, per_seconds=3600))])
    def thing() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_dependency_limits_by_ip_for_anonymous_callers(limited_app: FastAPI, client_for: ClientFor) -> None:
    client = client_for(limited_app, with_header=False)
    here = {"X-Forwarded-For": "203.0.113.5"}
    assert client.post("/thing", headers=here).status_code == 200
    assert client.post("/thing", headers=here).status_code == 200
    refused = client.post("/thing", headers=here)
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) >= 1
    # Someone else is unaffected.
    assert client.post("/thing", headers={"X-Forwarded-For": "203.0.113.6"}).status_code == 200


def test_one_ipv6_subscriber_has_one_budget_however_many_addresses_they_use(
    limited_app: FastAPI, client_for: ClientFor
) -> None:
    client = client_for(limited_app, with_header=False)

    def post(address: str) -> int:
        return client.post("/thing", headers={"X-Forwarded-For": address}).status_code

    # A subscriber is handed a whole /64 and can pick any address in it.
    assert [post(f"2001:db8:1:2::{suffix:x}") for suffix in range(1, 41)] == [200, 200] + [429] * 38
    assert post("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == 429
    assert post("2001:db8:1:3::1") == 200, "the next /64 is someone else"
    # An IPv4 address is the same caller whether or not it arrives wrapped in IPv6.
    assert [post("198.51.100.7"), post("::ffff:198.51.100.7"), post("198.51.100.7")] == [200, 200, 429]


def test_a_forwarded_for_line_of_the_callers_own_is_not_believed(
    limited_app: FastAPI, client_for: ClientFor
) -> None:
    client = client_for(limited_app, with_header=False)

    def post(pretending_to_be: str) -> int:
        # The proxy adds the real address as a line of its own, after the caller's.
        lines = [("X-Forwarded-For", pretending_to_be), ("X-Forwarded-For", "203.0.113.50")]
        return client.post("/thing", headers=lines).status_code

    assert [post(f"10.9.8.{n}") for n in range(25)] == [200, 200] + [429] * 23


def test_enforce_spends_from_the_callers_bucket(limited_app: FastAPI, client_for: ClientFor) -> None:
    limiter = ratelimit.get_limiter("test_enforce", 1, 3600)

    @limited_app.post("/sometimes")
    def sometimes(request: Request, costly: bool = False) -> dict[str, bool]:
        if costly:
            ratelimit.enforce(limiter, request, None)
        return {"ok": True}

    client = client_for(limited_app, with_header=False)
    here = {"X-Forwarded-For": "203.0.113.5"}
    assert [client.post("/sometimes", headers=here).status_code for _ in range(3)] == [200] * 3
    assert client.post("/sometimes?costly=true", headers=here).status_code == 200
    assert client.post("/sometimes?costly=true", headers=here).status_code == 429
    assert client.post("/sometimes", headers=here).status_code == 200


def test_dependency_limits_by_user_when_signed_in(
    limited_app: FastAPI, make_user: MakeUser, client_for: ClientFor
) -> None:
    alice, bob = client_for(limited_app, make_user()), client_for(limited_app, make_user())
    # Same address, different people: each has their own budget.
    here = {"X-Forwarded-For": "203.0.113.9"}
    assert [alice.post("/thing", headers=here).status_code for _ in range(3)] == [200, 200, 429]
    assert bob.post("/thing", headers=here).status_code == 200
    # And Alice is still limited from another address.
    assert alice.post("/thing", headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 429


def test_dependency_can_be_switched_off(
    limited_app: FastAPI, env: Callable[..., None], client_for: ClientFor
) -> None:
    env(RATELIMIT_ENABLED="false")
    client = client_for(limited_app, with_header=False)
    assert [client.post("/thing").status_code for _ in range(5)] == [200] * 5
