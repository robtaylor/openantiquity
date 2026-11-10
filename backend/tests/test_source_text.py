"""Source files hold no invisible or control characters, so what a reader sees is what runs.

`tests/README.md` asks for such characters to be written as escapes, such as `"\\u202e"`.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ALLOWED = frozenset("\n\t")


def _python_files() -> list[Path]:
    return sorted(path for folder in ("src", "tests") for path in (BACKEND / folder).rglob("*.py"))


@pytest.mark.parametrize("path", _python_files(), ids=lambda path: str(path.relative_to(BACKEND)))
def test_no_invisible_characters(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        hidden = [
            f"U+{ord(char):04X}"
            for char in line
            if char not in ALLOWED and unicodedata.category(char) in ("Cc", "Cf", "Co", "Cs", "Zl", "Zp")
        ]
        assert not hidden, f"{path.name}:{number} holds {hidden}: write them as escapes"
