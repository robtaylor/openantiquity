"""`fieldclub-release`: what a deploy runs once, before any machine is replaced."""

from __future__ import annotations

import pytest

from fieldclub import release


def test_the_mirror_is_checked_before_the_schema_is_touched(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(release.terrain_cli, "main", lambda argv: order.append(("check", argv)) or 0)
    monkeypatch.setattr(release.db, "main", lambda argv: order.append(("schema", argv)))

    assert release.main([]) == 0

    assert order == [("check", ["check"]), ("schema", [])]


def test_a_failed_check_stops_the_release_with_the_schema_untouched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    made: list[int] = []
    monkeypatch.setattr(release.terrain_cli, "main", lambda argv: 1)
    monkeypatch.setattr(release.db, "main", lambda argv: made.append(1))

    assert release.main([]) == 1

    assert made == []
    assert "schema wasn't touched" in capsys.readouterr().err
