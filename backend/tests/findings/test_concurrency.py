"""Two people answering the same finding at the same moment both count.

Each answer is written and the finding reassessed under a row lock on the
finding. Without it, both transactions would read the inputs before either
committed, and the second to commit would store an assessment that is
missing the first answer.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.models import Finding, User
from fieldclub.services import review
from fieldclub.vocab import Visible
from tests.findings.support import create
from tests.helpers import MakeUser


def _answer_in_own_session(
    finding_id: int, user_id: int, *, before_commit: Callable[[], None] = lambda: None
) -> None:
    with fieldclub_db.SessionLocal() as session:
        finding = session.get(Finding, finding_id)
        user = session.get(User, user_id)
        assert finding is not None
        assert user is not None
        review.put_observation(session, finding, user, review.Answer(visible=Visible.YES))
        before_commit()
        session.commit()


def _run(*targets: Callable[[], None]) -> list[BaseException]:
    errors: list[BaseException] = []

    def wrap(target: Callable[[], None]) -> Callable[[], None]:
        def run() -> None:
            try:
                target()
            except BaseException as exc:
                errors.append(exc)

        return run

    threads = [threading.Thread(target=wrap(target)) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "an answer never finished"
    return errors


def _assert_both_counted(db: Session, finding: Finding) -> None:
    db.expire_all()
    stored = db.scalars(select(Finding).where(Finding.id == finding.id)).one()
    assert stored.observation_count == 2
    assert stored.assessment["observers"] == 2
    assert stored.tier == "seen"


def test_a_second_answer_waits_for_the_first_and_sees_it(db: Session, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    first, second = make_user(), make_user()
    holding = threading.Event()
    release = threading.Event()
    second_done = threading.Event()

    def hold() -> None:
        holding.set()
        assert release.wait(10), "the test never released the first answer"

    def first_answer() -> None:
        _answer_in_own_session(finding.id, first.id, before_commit=hold)

    def second_answer() -> None:
        assert holding.wait(10), "the first answer never took the lock"
        _answer_in_own_session(finding.id, second.id)
        second_done.set()

    def referee() -> None:
        assert holding.wait(10)
        # While the first answer holds the lock, the second can't finish.
        assert not second_done.wait(0.5), "the second answer didn't wait for the lock"
        release.set()

    assert _run(first_answer, second_answer, referee) == []
    _assert_both_counted(db, finding)


def test_answers_started_together_both_count(db: Session, make_user: MakeUser) -> None:
    for _ in range(5):
        finding = create(db, make_user())
        people = [make_user(), make_user()]
        start = threading.Barrier(2)

        def go(
            user: User, finding_id: int = finding.id, start: threading.Barrier = start
        ) -> Callable[[], None]:
            def run() -> None:
                start.wait(10)
                _answer_in_own_session(finding_id, user.id)

            return run

        assert _run(*(go(person) for person in people)) == []
        _assert_both_counted(db, finding)
