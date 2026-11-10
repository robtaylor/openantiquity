"""Public ids: short, unambiguous and unique."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from fieldclub.models import Finding, Investigation
from fieldclub.services import ids
from tests.helpers import MakeFinding


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


def test_new_public_id_is_free(db: Session, make_finding: MakeFinding) -> None:
    taken = {make_finding().public_id for _ in range(5)}
    fresh = ids.new_public_id(db, Finding)
    assert fresh not in taken
    assert ids.normalise(fresh) == fresh


def test_new_public_id_retries_past_a_clash(
    db: Session, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_finding(public_id="AAAAAA")
    make_finding(public_id="BBBBBB")
    offered = iter(["AAAAAA", "BBBBBB", "CCCCCC"])
    monkeypatch.setattr(ids, "generate", lambda: next(offered))
    assert ids.new_public_id(db, Finding) == "CCCCCC"


def test_ids_are_unique_per_table_not_across_tables(
    db: Session, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_finding(public_id="AAAAAA")
    monkeypatch.setattr(ids, "generate", lambda: "AAAAAA")
    assert ids.new_public_id(db, Investigation) == "AAAAAA"


def test_gives_up_when_nothing_is_free(
    db: Session, make_finding: MakeFinding, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_finding(public_id="AAAAAA")
    monkeypatch.setattr(ids, "generate", lambda: "AAAAAA")
    with pytest.raises(ids.IdGenerationError) as caught:
        ids.new_public_id(db, Finding)
    assert caught.value.code == "id_generation_failed"
