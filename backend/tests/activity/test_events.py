"""The event hub and GET /events/stream.

The hub tests drive one `EventHub` on an event loop of their own, and record
events through ordinary sessions in a worker thread, as the API does. The
stream tests run the app under a real uvicorn server, because a test client
waits for a response to finish and a stream never does.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
from collections.abc import Coroutine, Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import text
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.models import Finding, User
from fieldclub.services import events, findings, review, sensitivity
from fieldclub.services.events import Announcement, EventHub, Signal, StreamFilter, TooManyStreamsError
from fieldclub.vocab import Visible
from tests.activity.support import TIMEOUT_S, next_activity, read_event
from tests.findings.support import create
from tests.helpers import MakeUser

# Long enough for a check to time out and psycopg to give up cancelling it.
SILENT_S = 20.0


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    async def bounded() -> T:
        return await asyncio.wait_for(coroutine, TIMEOUT_S)

    return asyncio.run(bounded())


async def started_hub(lookup: events.Lookup = events.lookup_public, **options: Any) -> EventHub:
    settings: dict[str, Any] = {
        "queue_size": 16,
        "max_per_address": 4,
        "max_streams": 20,
        "retry_delays_s": (0.05,),
    } | options
    hub = EventHub(events.conninfo(), lookup, **settings)
    hub.start()
    await asyncio.wait_for(hub.connected.wait(), TIMEOUT_S)
    return hub


async def received(subscription: events.Subscription, timeout: float = 5.0) -> Announcement | Signal:
    item = await subscription.next(timeout)
    assert item is not None, "nothing arrived"
    return item


async def nothing_for(subscription: events.Subscription, seconds: float = 0.3) -> bool:
    return await subscription.next(seconds) is None


def _comment(finding_id: int, user_id: int) -> int:
    """A comment from a session of its own, committed, as a request would make it."""
    with fieldclub_db.SessionLocal() as session:
        finding, user = session.get(Finding, finding_id), session.get(User, user_id)
        assert finding is not None
        assert user is not None
        made = findings.add_comment(session, finding, user, "Seen it from the footpath.")
        session.commit()
        return made.id


async def comment_elsewhere(finding: Finding, user: User) -> int:
    return await asyncio.to_thread(_comment, finding.id, user.id)


@pytest.fixture
def scene(db: Session, make_user: MakeUser) -> dict[str, Any]:
    finder = make_user(handle="Finder")
    near = create(db, finder, title="Near")
    far = create(db, finder, title="Far", lon=-2.5, lat=53.0)
    return {"finder": finder, "near": near, "far": far, "talker": make_user(handle="Talker")}


# --------------------------------------------------------------------------
# The hub
# --------------------------------------------------------------------------


def test_two_clients_receive_an_event_recorded_in_another_session(scene: dict[str, Any]) -> None:
    async def scenario() -> list[Announcement | Signal]:
        hub = await started_hub()
        first, second = hub.subscribe(StreamFilter(), "a"), hub.subscribe(StreamFilter(), "b")
        await comment_elsewhere(scene["near"], scene["talker"])
        got = [await received(first), await received(second)]
        await hub.stop()
        return got

    got = run(scenario())
    assert got[0] == got[1]
    event = got[0]
    assert isinstance(event, Announcement)
    assert asdict(event) == {
        "id": event.id,
        "kind": "comment_added",
        "finding": scene["near"].public_id,
        "investigation": None,
        "actor": "Talker",
    }


def test_filters_by_finding_and_by_square(scene: dict[str, Any]) -> None:
    near, far = scene["near"], scene["far"]
    centre = sensitivity.square_centre(near)
    assert centre is not None
    around = (centre[0] - 0.001, centre[1] - 0.001, centre[0] + 0.001, centre[1] + 0.001)

    async def scenario() -> None:
        hub = await started_hub()
        on_far = hub.subscribe(StreamFilter(finding=far.public_id), "a")
        in_box = hub.subscribe(StreamFilter(bbox=around), "a")
        elsewhere = hub.subscribe(StreamFilter(bbox=(0.0, 0.0, 1.0, 1.0)), "a")
        await comment_elsewhere(near, scene["talker"])
        got = await received(in_box)
        assert isinstance(got, Announcement)
        assert got.finding == near.public_id
        assert await nothing_for(on_far)
        assert await nothing_for(elsewhere)
        await comment_elsewhere(far, scene["talker"])
        got = await received(on_far)
        assert isinstance(got, Announcement)
        assert got.finding == far.public_id
        assert await nothing_for(in_box)
        await hub.stop()

    run(scenario())


def test_events_the_public_feed_leaves_out_are_never_announced(db: Session, scene: dict[str, Any]) -> None:
    near, far = scene["near"], scene["far"]
    near.hidden_at = datetime.now(UTC)
    db.commit()

    async def scenario() -> None:
        hub = await started_hub()
        everything = hub.subscribe(StreamFilter(), "a")
        await comment_elsewhere(near, scene["talker"])
        await comment_elsewhere(far, scene["talker"])
        got = await received(everything)
        assert isinstance(got, Announcement)
        assert got.finding == far.public_id
        assert await nothing_for(everything)
        await hub.stop()

    run(scenario())


def test_a_second_look_is_announced_with_no_actor(
    db: Session, scene: dict[str, Any], make_user: MakeUser
) -> None:
    near, reviewer = scene["near"], make_user(handle="Reviewer")

    def answer_elsewhere() -> None:
        with fieldclub_db.SessionLocal() as session:
            finding, user = session.get(Finding, near.id), session.get(User, reviewer.id)
            assert finding is not None
            assert user is not None
            review.put_observation(session, finding, user, review.Answer(visible=Visible.NO))
            session.commit()

    async def scenario() -> Announcement | Signal:
        hub = await started_hub()
        everything = hub.subscribe(StreamFilter(), "a")
        await asyncio.to_thread(answer_elsewhere)
        got = await received(everything)
        await hub.stop()
        return got

    got = run(scenario())
    assert isinstance(got, Announcement)
    assert (got.kind, got.actor) == ("observation_added", None)


def test_a_slow_client_is_dropped_and_the_others_carry_on(scene: dict[str, Any]) -> None:
    async def scenario() -> None:
        hub = await started_hub(queue_size=2)
        slow = hub.subscribe(StreamFilter(), "slow")
        quick = hub.subscribe(StreamFilter(), "quick")
        heard = []
        for _ in range(4):
            await comment_elsewhere(scene["near"], scene["talker"])
            heard.append(await received(quick))
        assert all(isinstance(item, Announcement) for item in heard)
        assert len({item.id for item in heard if isinstance(item, Announcement)}) == 4
        # The slow one fell three behind a queue of two: everything it held is
        # gone, and all it will read is that it was dropped.
        assert slow.ended
        assert slow.queue.qsize() == 1
        assert await received(slow) is Signal.DROPPED
        assert hub.subscriptions == {quick}
        await hub.stop()

    run(scenario())


def test_a_dropped_client_keeps_its_place_until_its_response_ends(scene: dict[str, Any]) -> None:
    """A client that stopped reading may still hold its connection, so it still counts."""

    async def scenario() -> None:
        hub = await started_hub(queue_size=1, max_per_address=1, max_streams=2)
        stuck = hub.subscribe(StreamFilter(), "a")
        hub.subscribe(StreamFilter(), "b")
        for _ in range(2):
            await comment_elsewhere(scene["near"], scene["talker"])
        await asyncio.sleep(0.3)
        assert stuck.ended
        assert stuck not in hub.subscriptions
        assert hub.held == 2
        with pytest.raises(TooManyStreamsError):
            hub.subscribe(StreamFilter(), "a")
        with pytest.raises(TooManyStreamsError):
            hub.subscribe(StreamFilter(), "c")
        # Its response has ended: the place is free.
        hub.unsubscribe(stuck)
        assert hub.held == 1
        hub.subscribe(StreamFilter(), "a")
        await hub.stop()
        assert hub.held == 0

    run(scenario())


def test_an_event_that_cant_be_checked_is_skipped_and_the_listener_carries_on(
    scene: dict[str, Any],
) -> None:
    calls: list[int] = []

    async def failing_once(activity_id: int) -> events.Listed | None:
        calls.append(activity_id)
        if len(calls) == 1:
            raise RuntimeError("not a database error")
        return await events.lookup_public(activity_id)

    async def scenario() -> None:
        hub = await started_hub(lookup=failing_once)
        everything = hub.subscribe(StreamFilter(), "a")
        await comment_elsewhere(scene["near"], scene["talker"])
        assert await nothing_for(everything)
        await comment_elsewhere(scene["far"], scene["talker"])
        got = await received(everything)
        assert isinstance(got, Announcement)
        assert got.finding == scene["far"].public_id
        assert len(calls) == 2
        await hub.stop()

    run(scenario())


def test_the_listener_starts_again_after_any_failure(scene: dict[str, Any], monkeypatch: Any) -> None:
    async def scenario() -> None:
        hub = await started_hub()
        everything = hub.subscribe(StreamFilter(), "a")
        deliver = hub.deliver

        async def failing_once(payload: str) -> None:
            monkeypatch.setattr(hub, "deliver", deliver)
            raise RuntimeError("not a connection error")

        monkeypatch.setattr(hub, "deliver", failing_once)
        await comment_elsewhere(scene["near"], scene["talker"])
        assert await received(everything) is Signal.RESYNC
        await comment_elsewhere(scene["far"], scene["talker"])
        got = await received(everything)
        assert isinstance(got, Announcement)
        assert got.finding == scene["far"].public_id
        await hub.stop()

    run(scenario())


class _Fatal(BaseException):
    """Something no handler in the hub catches, to stop the listener for good."""


def test_a_listener_that_stops_is_started_by_the_next_client(scene: dict[str, Any]) -> None:
    fatal = [True]

    async def lookup(activity_id: int) -> events.Listed | None:
        if fatal.pop() if fatal else False:
            raise _Fatal()
        return await events.lookup_public(activity_id)

    async def scenario() -> None:
        hub = await started_hub(lookup=lookup)
        first = hub.subscribe(StreamFilter(), "a")
        await comment_elsewhere(scene["near"], scene["talker"])
        for _ in range(100):
            if not hub.connected.is_set():
                break
            await asyncio.sleep(0.05)
        assert not hub.connected.is_set(), "the listener didn't stop"
        await asyncio.sleep(0)
        second = hub.subscribe(StreamFilter(), "b")
        await asyncio.wait_for(hub.connected.wait(), TIMEOUT_S)
        # Both are told they may have missed something.
        assert await received(first) is Signal.RESYNC
        assert await received(second) is Signal.RESYNC
        await comment_elsewhere(scene["far"], scene["talker"])
        got = await received(second)
        assert isinstance(got, Announcement)
        assert got.finding == scene["far"].public_id
        await hub.stop()

    run(scenario())


def test_stopping_never_raises_what_the_listener_raised(db: Session) -> None:
    async def scenario() -> None:
        hub = await started_hub()
        task = hub._task
        assert task is not None

        async def dies() -> None:
            raise RuntimeError("the listener went wrong")

        # A listener that died before its done-callback ran.
        hub._task = asyncio.get_running_loop().create_task(dies())
        await asyncio.sleep(0)
        await hub.stop()
        task.cancel()
        await asyncio.wait([task])

    run(scenario())


def test_the_listener_reconnects_after_its_connection_is_killed(database: Any, scene: dict[str, Any]) -> None:
    def kill(pid: int) -> None:
        with database.connect() as conn:
            assert conn.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}) is True

    async def scenario() -> None:
        hub = await started_hub(idle_check_s=0.2)
        everything = hub.subscribe(StreamFilter(), "a")
        before = hub.backend_pid
        assert before is not None
        await asyncio.to_thread(kill, before)
        # Clients are told they may have missed something, once it is back.
        assert await received(everything) is Signal.RESYNC
        assert hub.connected.is_set()
        assert hub.backend_pid not in (None, before)
        await comment_elsewhere(scene["near"], scene["talker"])
        got = await received(everything)
        assert isinstance(got, Announcement)
        assert got.kind == "comment_added"
        await hub.stop()

    run(scenario())


class SilencingProxy:
    """A TCP relay to the database that can go silent on the connections it already carries.

    `silence()` stands for a machine Fly suspended and resumed, or a network
    that dropped its state: those connections stay open, bytes sent on them
    are taken and never delivered, and nothing ever comes back. Connections
    made afterwards are relayed as usual.
    """

    def __init__(self, host: str, port: int) -> None:
        self.target = (host, port)
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.silenced: set[socket.socket] = set()
        self.sockets: list[socket.socket] = []
        self.guard = threading.Lock()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            upstream = socket.create_connection(self.target)
            with self.guard:
                self.sockets += [client, upstream]
            for source, sink in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pump, args=(source, sink), daemon=True).start()

    def _pump(self, source: socket.socket, sink: socket.socket) -> None:
        while True:
            try:
                data = source.recv(65536)
            except OSError:
                return
            if not data:
                return
            with self.guard:
                silent = source in self.silenced
            if not silent:
                with contextlib.suppress(OSError):
                    sink.sendall(data)

    def silence(self) -> None:
        with self.guard:
            self.silenced.update(self.sockets)

    def close(self) -> None:
        self.listener.close()
        with self.guard:
            for sock in self.sockets:
                sock.close()


@pytest.fixture
def silencing_proxy() -> Iterator[SilencingProxy]:
    url = fieldclub_db.get_engine().url
    assert url.host is not None
    proxy = SilencingProxy(url.host, url.port or 5432)
    yield proxy
    proxy.close()


def through(proxy: SilencingProxy) -> str:
    return make_conninfo(events.conninfo(), host="127.0.0.1", port=str(proxy.port))


def test_the_listener_replaces_a_connection_that_went_silent(
    silencing_proxy: SilencingProxy, scene: dict[str, Any]
) -> None:
    async def scenario() -> None:
        hub = EventHub(
            through(silencing_proxy),
            events.lookup_public,
            queue_size=16,
            max_per_address=4,
            max_streams=20,
            retry_delays_s=(0.05,),
            idle_check_s=0.2,
            check_timeout_s=0.5,
        )
        hub.start()
        await asyncio.wait_for(hub.connected.wait(), TIMEOUT_S)
        everything = hub.subscribe(StreamFilter(), "a")
        before = hub.backend_pid
        silencing_proxy.silence()
        # No error ever arrives on the old connection: only the hub's own check can tell.
        assert await received(everything, timeout=SILENT_S) is Signal.RESYNC
        assert hub.backend_pid not in (None, before)
        await comment_elsewhere(scene["near"], scene["talker"])
        got = await received(everything)
        assert isinstance(got, Announcement)
        assert got.finding == scene["near"].public_id
        await hub.stop()

    asyncio.run(asyncio.wait_for(scenario(), SILENT_S * 2))


def test_a_new_client_has_the_connection_checked_at_once(
    silencing_proxy: SilencingProxy, scene: dict[str, Any]
) -> None:
    async def scenario() -> None:
        # The timed check is an hour away, as the first visitor to a resumed machine might find it.
        hub = EventHub(
            through(silencing_proxy),
            events.lookup_public,
            queue_size=16,
            max_per_address=4,
            max_streams=20,
            retry_delays_s=(0.05,),
            idle_check_s=3600,
            check_timeout_s=0.5,
        )
        hub.start()
        await asyncio.wait_for(hub.connected.wait(), TIMEOUT_S)
        await asyncio.sleep(0.1)
        silencing_proxy.silence()
        arriving = hub.subscribe(StreamFilter(), "a")
        assert await received(arriving, timeout=SILENT_S) is Signal.RESYNC
        await comment_elsewhere(scene["far"], scene["talker"])
        got = await received(arriving)
        assert isinstance(got, Announcement)
        await hub.stop()

    asyncio.run(asyncio.wait_for(scenario(), SILENT_S * 2))


def test_the_listener_asks_for_tcp_keepalives(db: Session) -> None:
    async def scenario() -> None:
        hub = await started_hub()
        pid = hub.backend_pid
        await hub.stop()
        assert pid is not None

    seen: list[dict[str, Any]] = []
    real = psycopg.AsyncConnection.connect

    async def connect(conninfo: str, **kwargs: Any) -> Any:
        seen.append(conninfo_to_dict(conninfo))
        return await real(conninfo, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(psycopg.AsyncConnection, "connect", connect)
        run(scenario())
    assert seen
    wanted = {name: str(value) for name, value in fieldclub_db.KEEPALIVES.items()}
    wanted["connect_timeout"] = str(events.CHECK_TIMEOUT_S.__ceil__())
    assert all(params.items() >= wanted.items() for params in seen)


def test_a_listen_that_gets_no_answer_is_given_up_and_retried(db: Session) -> None:
    """A reconnect that reaches a peer which accepts the connection and then answers nothing."""
    real = psycopg.AsyncConnection.connect
    attempts: list[int] = []

    async def connect(conninfo: str, **kwargs: Any) -> Any:
        conn = await real(conninfo, **kwargs)
        attempts.append(conn.info.backend_pid)
        if len(attempts) == 1:
            execute = conn.execute

            async def unanswered(query: Any, *args: Any, **kw: Any) -> Any:
                if str(query).startswith("LISTEN"):
                    await asyncio.Event().wait()
                return await execute(query, *args, **kw)

            conn.execute = unanswered
        return conn

    async def scenario() -> None:
        hub = EventHub(
            events.conninfo(),
            events.lookup_public,
            queue_size=16,
            max_per_address=4,
            max_streams=20,
            retry_delays_s=(0.05,),
            check_timeout_s=0.5,
        )
        hub.start()
        await asyncio.wait_for(hub.connected.wait(), TIMEOUT_S)
        assert len(attempts) == 2, "the first connection's LISTEN should have been given up"
        assert hub.backend_pid == attempts[1]
        await hub.stop()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(psycopg.AsyncConnection, "connect", connect)
        run(scenario())


def test_making_the_connection_has_a_time_limit(caplog: pytest.LogCaptureFixture) -> None:
    # A server that completes the TCP handshake and never says anything.
    silent = socket.create_server(("127.0.0.1", 0))
    port = silent.getsockname()[1]

    async def scenario() -> None:
        hub = EventHub(
            make_conninfo(events.conninfo(), host="127.0.0.1", port=str(port)),
            events.lookup_public,
            queue_size=16,
            max_per_address=4,
            max_streams=20,
            retry_delays_s=(0.05,),
            check_timeout_s=0.5,
        )
        assert hub.connect_timeout_s == 2, "libpq's shortest connect_timeout"
        hub.start()
        await asyncio.sleep(hub.connect_timeout_s * 2 + 1.5)
        assert not hub.connected.is_set()
        await hub.stop()

    try:
        with caplog.at_level("WARNING", logger="fieldclub.services.events"):
            run(scenario())
    finally:
        silent.close()
    failures = [r for r in caplog.records if "event listener failed" in r.getMessage()]
    assert len(failures) >= 2, "each attempt should end at the time limit, not hang"


def test_caps_per_address_and_per_process(db: Session) -> None:
    async def scenario() -> None:
        hub = await started_hub(max_per_address=2, max_streams=3)
        first = hub.subscribe(StreamFilter(), "a")
        hub.subscribe(StreamFilter(), "a")
        with pytest.raises(TooManyStreamsError):
            hub.subscribe(StreamFilter(), "a")
        hub.subscribe(StreamFilter(), "b")
        with pytest.raises(TooManyStreamsError):
            hub.subscribe(StreamFilter(), "c")
        hub.unsubscribe(first)
        hub.unsubscribe(first)  # harmless twice
        hub.subscribe(StreamFilter(), "a")
        await hub.stop()

    run(scenario())


def test_stopping_ends_every_client_and_the_listener(db: Session) -> None:
    async def scenario() -> None:
        hub = await started_hub()
        clients = [hub.subscribe(StreamFilter(), "a") for _ in range(3)]
        await hub.stop()
        for client in clients:
            assert await received(client) is Signal.CLOSED
        assert hub.subscriptions == frozenset()
        assert not hub.connected.is_set()
        await hub.stop()  # idempotent
        with pytest.raises(AssertionError, match="stopped"):
            hub.subscribe(StreamFilter(), "a")

    run(scenario())


def test_payloads_that_arent_events_are_ignored(db: Session) -> None:
    async def scenario() -> None:
        hub = await started_hub()
        client = hub.subscribe(StreamFilter(), "a")
        for payload in (
            "not json",
            "[]",
            '{"id": 1}',
            json.dumps(
                {"id": "1", "kind": "x", "finding": None, "investigation": None, "actor": None, "lon": 1}
            ),
        ):
            await hub.deliver(payload)
        assert await nothing_for(client)
        await hub.stop()

    run(scenario())


def test_the_process_has_one_hub_per_loop(db: Session) -> None:
    async def scenario() -> EventHub:
        hub = events.get_hub(queue_size=4, max_per_address=1, max_streams=1)
        assert events.get_hub(queue_size=4, max_per_address=1, max_streams=1) is hub
        await events.stop_hub()
        assert events.get_hub(queue_size=4, max_per_address=1, max_streams=1) is not hub
        await events.stop_hub()
        return hub

    first = run(scenario())
    assert run(scenario()) is not first


# --------------------------------------------------------------------------
# Over HTTP, through a real server
# --------------------------------------------------------------------------


def test_two_browsers_receive_an_event_over_http(server: str, scene: dict[str, Any]) -> None:
    with (
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as one,
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as two,
        one.stream("GET", "/api/v1/events/stream") as first,
        two.stream("GET", "/api/v1/events/stream", params={"finding": scene["near"].public_id}) as second,
    ):
        assert first.status_code == second.status_code == 200
        assert first.headers["content-type"].startswith("text/event-stream")
        assert first.headers["cache-control"] == "no-cache"
        first_lines, second_lines = first.iter_lines(), second.iter_lines()
        assert read_event(first_lines) == {"comment": "connected", "retry": "3000"}
        # Neither stream holds a database connection while it waits.
        assert fieldclub_db.get_engine().pool.checkedout() == 0  # pyright: ignore[reportAttributeAccessIssue]
        comment_id = _comment(scene["near"].id, scene["talker"].id)
        got = [next_activity(first_lines), next_activity(second_lines)]
    assert got[0] == got[1]
    assert set(got[0]) == {"id", "kind", "finding", "investigation", "actor"}
    assert (got[0]["kind"], got[0]["finding"], got[0]["actor"]) == (
        "comment_added",
        scene["near"].public_id,
        "Talker",
    )
    assert comment_id


def test_heartbeats_keep_an_idle_stream_open(server: str, env: Any, db: Session) -> None:
    env(EVENTS_HEARTBEAT_S="0.1")
    with (
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as browser,
        browser.stream("GET", "/api/v1/events/stream") as stream,
    ):
        lines = stream.iter_lines()
        comments = [read_event(lines).get("comment") for _ in range(3)]
    assert comments[1:] == ["ping", "ping"]


def test_a_stream_ends_after_its_longest_life(server: str, env: Any, db: Session) -> None:
    env(EVENTS_MAX_STREAM_S="0.3", EVENTS_HEARTBEAT_S="0.1")
    with (
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as browser,
        browser.stream("GET", "/api/v1/events/stream") as stream,
    ):
        body = "".join(stream.iter_text())
    assert body.startswith(": connected\nretry: 3000\n\n")
    assert body.endswith(": ping\n\n")


def test_one_address_may_hold_only_so_many_streams(server: str, env: Any, db: Session) -> None:
    env(EVENTS_MAX_PER_ADDRESS="1")
    with (
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as browser,
        browser.stream("GET", "/api/v1/events/stream") as held,
    ):
        assert held.status_code == 200
        refused = browser.get("/api/v1/events/stream")
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "too_many_streams"
    # Once the first is closed the address may open another.
    with (
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as browser,
        browser.stream("GET", "/api/v1/events/stream") as again,
    ):
        assert again.status_code == 200


@pytest.mark.parametrize(
    ("params", "code"), [({"bbox": "1,2"}, "invalid_bbox"), ({"finding": "!!"}, "finding_not_found")]
)
def test_bad_filters_are_refused_before_streaming(server: str, db: Session, params: dict, code: str) -> None:
    with httpx.Client(base_url=server, timeout=TIMEOUT_S) as browser:
        response = browser.get("/api/v1/events/stream", params=params)
    assert response.json()["error"]["code"] == code


def test_shutting_down_closes_open_streams(server: str, db: Session) -> None:
    with (
        httpx.Client(base_url=server, timeout=TIMEOUT_S) as browser,
        browser.stream("GET", "/api/v1/events/stream") as stream,
    ):
        lines = stream.iter_lines()
        read_event(lines)
        hub = events._hub
        assert hub is not None
        asyncio.run_coroutine_threadsafe(events.stop_hub(), hub.loop).result(TIMEOUT_S)
        assert read_event(lines) == {"event": "closed", "data": "{}"}
