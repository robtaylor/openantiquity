"""In-memory token buckets, usable as FastAPI dependencies.

    @router.post("/findings", dependencies=[Depends(rate_limit("findings", 30, per_seconds=3600))])

Each caller gets a bucket holding `capacity` tokens that refills steadily over
`per_seconds`. A request spends one token. An empty bucket means a 429 with a
`Retry-After` header. Signed-in callers are keyed by user and everyone else by
a hash of their IP address. An IPv6 caller is keyed by their /64, because a
single subscriber is handed a whole /64 and can use any address in it.

The buckets live in this process. With several instances behind a load
balancer each keeps its own count, so treat the limits as a brake on abuse and
not as exact quotas.
"""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from fieldclub.auth.deps import OptionalUser, client_ip
from fieldclub.auth.tokens import hash_ip
from fieldclub.config import get_settings
from fieldclub.errors import RateLimitedError
from fieldclub.models import User


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """A set of token buckets, one per key, sharing a capacity and refill rate."""

    def __init__(
        self,
        name: str,
        capacity: float,
        per_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 50_000,
    ) -> None:
        assert capacity > 0, "capacity must be positive"
        assert per_seconds > 0, "per_seconds must be positive"
        assert max_keys > 0, "max_keys must be positive"
        self.name = name
        self.capacity = float(capacity)
        self.per_seconds = float(per_seconds)
        self.refill_rate = self.capacity / self.per_seconds
        self._clock = clock
        self._max_keys = max_keys
        # Ordered by last use, oldest first. `hit` moves a bucket to the end.
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key: str, cost: float = 1.0) -> None:
        """Spend `cost` tokens from `key`'s bucket, or raise `RateLimitedError`."""
        assert 0 < cost <= self.capacity, "cost must be positive and no more than the capacity"
        with self._lock:
            now = self._clock()
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    self._make_room(now)
                bucket = self._buckets[key] = _Bucket(tokens=self.capacity, updated_at=now)
            else:
                elapsed = max(0.0, now - bucket.updated_at)
                bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_rate)
                bucket.updated_at = now
                self._buckets.move_to_end(key)
            if bucket.tokens < cost:
                raise RateLimitedError(retry_after_s=(cost - bucket.tokens) / self.refill_rate)
            bucket.tokens -= cost

    def remaining(self, key: str) -> float:
        """Tokens `key` has right now. For tests and diagnostics."""
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return self.capacity
            elapsed = max(0.0, self._clock() - bucket.updated_at)
            return min(self.capacity, bucket.tokens + elapsed * self.refill_rate)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _make_room(self, now: float) -> None:
        """Make space for one new key when the table is full.

        Buckets that have refilled completely carry no information and go
        first. If every bucket is still live, only the one used longest ago is
        forgotten. Clearing the table instead would let a flood of new keys
        reset every caller's limit, the flooder's own included.
        """
        assert self._buckets, "there is nothing to evict from an empty table"
        while self._buckets:
            oldest = next(iter(self._buckets.values()))
            if now - oldest.updated_at < self.per_seconds:
                break
            self._buckets.popitem(last=False)
        while len(self._buckets) >= self._max_keys:
            self._buckets.popitem(last=False)

    def __len__(self) -> int:
        return len(self._buckets)


_limiters: dict[str, RateLimiter] = {}
_registry_lock = threading.Lock()


def get_limiter(name: str, capacity: float, per_seconds: float) -> RateLimiter:
    """The process-wide limiter called `name`, created on first use."""
    with _registry_lock:
        limiter = _limiters.get(name)
        if limiter is None:
            limiter = _limiters[name] = RateLimiter(name, capacity, per_seconds)
        assert (limiter.capacity, limiter.per_seconds) == (float(capacity), float(per_seconds)), (
            f"rate limiter {name!r} is already registered with different limits"
        )
        return limiter


def reset_all() -> None:
    """Empty every limiter. The tests call this between cases."""
    with _registry_lock:
        for limiter in _limiters.values():
            limiter.reset()


IPV6_SUBSCRIBER_PREFIX = 64


def address_key(ip: str) -> str:
    """The part of an address that identifies one caller for rate limiting.

    An IPv4 address is itself. An IPv6 address is its /64 network, and an
    IPv4 address written as IPv6 (`::ffff:203.0.113.5`) is the IPv4 address.
    Anything that isn't an address is used as it stands.
    """
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return ip
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        network = ipaddress.ip_network((address, IPV6_SUBSCRIBER_PREFIX), strict=False)
        return str(network.network_address)
    return str(address)


def caller_key(request: Request, user: User | None) -> str:
    """Who to count a request against: the user if signed in, otherwise their hashed address."""
    if user is not None:
        return f"user:{user.id}"
    ip = client_ip(request)
    return f"ip:{hash_ip(address_key(ip))}" if ip else "ip:unknown"


def enforce(limiter: RateLimiter, request: Request, user: User | None) -> None:
    """Spend one of the caller's tokens, or raise `RateLimitedError`.

    For a limit that depends on what the request asks for, which a dependency
    can't know. Does nothing when `FIELDCLUB_RATELIMIT_ENABLED` is false.
    """
    enforce_key(limiter, caller_key(request, user))


def enforce_key(limiter: RateLimiter, key: str) -> None:
    """Spend one of `key`'s tokens, or raise `RateLimitedError`, for a budget that isn't the caller's.

    Does nothing when `FIELDCLUB_RATELIMIT_ENABLED` is false.
    """
    if get_settings().ratelimit_enabled:
        limiter.hit(key)


def rate_limit(name: str, capacity: float, per_seconds: float) -> Callable[..., None]:
    """A dependency that allows each caller `capacity` requests per `per_seconds`.

    Routes sharing a `name` share a budget. `FIELDCLUB_RATELIMIT_ENABLED=false`
    switches every limit off.
    """
    limiter = get_limiter(name, capacity, per_seconds)

    def dependency(request: Request, user: OptionalUser) -> None:
        enforce(limiter, request, user)

    return dependency
