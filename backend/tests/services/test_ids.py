"""Public ids: short, unambiguous and unique."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from fieldclub.models import Finding, Investigation
from fieldclub.models.common import db_point
from fieldclub.services import findings, ids, investigations
from tests.helpers import AVEBURY, MakeFinding, count


def test_ids_are_six_characters_of_crockford_base32() -> None:
    for _ in range(2000):
        candidate = ids.generate()
        assert len(candidate) == 6
        assert set(candidate) <= set(ids.ALPHABET)


def test_the_alphabet_has_no_ambiguous_letters() -> None:
    assert ids.ALPHABET == "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    assert not set("ILOU") & set(ids.ALPHABET)


def test_generation_is_random() -> None:
    assert len({ids.generate() for _ in range(5000)}) > 4990


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("7K3QXM", "7K3QXM"),
        ("7k3qxm", "7K3QXM"),
        (" 7k3-qxm ", "7K3QXM"),
        ("OIL000", "011000"),
        ("oil000", "011000"),
        ("7K3QX", None),
        ("7K3QXMM", None),
        ("7K3QXU", None),
        ("7K3Q!M", None),
        ("", None),
    ],
)
def test_normalise(typed: str, expected: str | None) -> None:
    assert ids.normalise(typed) == expected


def _insert_finding(db: Session, author_id: int) -> Finding:
    """A finding inserted with `insert_with_public_id`, as `create_finding` does."""
    return ids.insert_with_public_id(
        db,
        lambda public_id: Finding(
            public_id=public_id,
            author_id=author_id,
            title="Test",
            feature_class="enclosure",
            location=db_point(*AVEBURY),
            view_state={},
        ),
        findings.PUBLIC_ID_CONSTRAINT,
    )


def _insert_investigation(db: Session, owner_id: int) -> Investigation:
    return ids.insert_with_public_id(
        db,
        lambda public_id: Investigation(public_id=public_id, owner_id=owner_id, title="Test"),
        investigations.PUBLIC_ID_CONSTRAINT,
    )


def test_an_inserted_public_id_is_free(db: Session, make_finding: MakeFinding) -> None:
    taken = {make_finding().public_id for _ in range(5)}
    fresh = _insert_finding(db, make_finding().author_id).public_id
    assert fresh not in taken
    assert ids.normalise(fresh) == fresh


def test_insertion_retries_past_a_clash(
    db: Session, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_finding(public_id="AAAAAA")
    author_id = make_finding(public_id="BBBBBB").author_id
    offered = iter(["AAAAAA", "BBBBBB", "CCCCCC"])
    monkeypatch.setattr(ids, "generate", lambda: next(offered))
    assert _insert_finding(db, author_id).public_id == "CCCCCC"
    assert count(db, Finding) == 3


def test_ids_are_unique_per_table_not_across_tables(
    db: Session, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    author_id = make_finding(public_id="AAAAAA").author_id
    monkeypatch.setattr(ids, "generate", lambda: "AAAAAA")
    assert _insert_investigation(db, author_id).public_id == "AAAAAA"


def test_gives_up_when_nothing_is_free(
    db: Session, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    author_id = make_finding(public_id="AAAAAA").author_id
    monkeypatch.setattr(ids, "generate", lambda: "AAAAAA")
    with pytest.raises(ids.IdGenerationError) as caught:
        _insert_finding(db, author_id)
    assert caught.value.code == "id_generation_failed"
    # Each clash was rolled back to its savepoint, so the session is still usable.
    assert count(db, Finding) == 1
