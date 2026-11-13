"""Guards for Decision 0035: no code path reads a stored feature class strictly.

A later version can have stored a class this version has no name for. Two
things would bring back the 500 that decision removed, and each has a test
here that fails the moment one is written:

- a call to `FeatureClass(...)` on a stored value, in place of `stored_class`;
- a response model field typed as the bare enumeration, which pydantic
  validates strictly when a row is handed to it as it is stored.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import types
from pathlib import Path
from typing import Annotated, Any, ForwardRef, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, TypeAdapter

import fieldclub
from fieldclub.schemas.common import RequestModel
from fieldclub.vocab import FeatureClass

LATER_CLASS = "added_by_a_later_version"
assert LATER_CLASS not in set(FeatureClass), "the class has to be one this version has no name for"

SOURCE = Path(fieldclub.__file__).parent

# The only places that may build a class from text: the reader itself, and the
# two that take a class a person sent, which the request model has checked.
MAY_CONSTRUCT = {
    ("vocab.py", "stored_class"),
    ("services/findings.py", "create_finding"),
    ("services/findings.py", "update_finding"),
}


def _constructions() -> set[tuple[str, str]]:
    """Every `FeatureClass(...)` call in the source, as its file and the function it is in."""
    found: set[tuple[str, str]] = set()
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owners: dict[ast.AST, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for inner in ast.walk(node):
                    # The innermost function wins: `ast.walk` meets an outer one first.
                    owners[inner] = node.name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name == "FeatureClass":
                found.add((path.relative_to(SOURCE).as_posix(), owners.get(node, "<module>")))
    return found


def test_only_the_reader_and_the_request_paths_build_a_class_from_text() -> None:
    assert _constructions() == MAY_CONSTRUCT, (
        "A stored class is read with `vocab.stored_class`, never `FeatureClass(...)` (Decision 0035)."
    )


def _response_models() -> list[type[BaseModel]]:
    """Every pydantic model in the package that isn't a request body."""
    for module in pkgutil.walk_packages(fieldclub.__path__, "fieldclub."):
        if ".schemas" in module.name or ".api" in module.name:
            importlib.import_module(module.name)
    found: list[type[BaseModel]] = []
    pending: list[type[BaseModel]] = list(BaseModel.__subclasses__())
    while pending:
        model = pending.pop()
        pending.extend(model.__subclasses__())
        if model.__module__.startswith("fieldclub.") and not issubclass(model, RequestModel):
            found.append(model)
    assert len(found) > 50, "the walk found too few models to be the whole API"
    return found


def _mentions_class(hint: Any) -> bool:
    if hint is FeatureClass:
        return True
    return any(_mentions_class(arg) for arg in get_args(hint))


def _is_class_or_none(hint: Any) -> bool:
    """Whether `hint` is the class, possibly annotated, possibly with None: the shapes this test can check."""
    if get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
    if hint is FeatureClass:
        return True
    if get_origin(hint) in (Union, types.UnionType):
        rest = [arg for arg in get_args(hint) if arg is not type(None)]
        return len(rest) == 1 and _is_class_or_none(rest[0])
    return False


def _class_fields() -> list[tuple[str, Any]]:
    """Every response field that can hold a class, with its type as pydantic resolved it.

    The type comes from the model's own fields, not from `get_type_hints`:
    that evaluates a generic model's annotations in the module that first
    filled it in, which lacks its type variable, and which module that is
    depends on the order the package happened to be imported in.
    """
    fields: list[tuple[str, Any]] = []
    for model in _response_models():
        for name, field in model.model_fields.items():
            where = f"{model.__module__}.{model.__name__}.{name}"
            # A name pydantic couldn't resolve would hide a class from this walk.
            assert not isinstance(field.annotation, str | ForwardRef), f"{where} has an unresolved type"
            if _mentions_class(field.annotation):
                # A validator on the whole field is kept apart from the annotation: put it back.
                hint = Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
                fields.append((where, hint))
    assert len(fields) >= 8, f"expected the response fields that carry a class, found {fields}"
    return sorted(fields, key=lambda field: field[0])


@pytest.mark.parametrize(
    ("where", "hint"), _class_fields(), ids=lambda value: value if isinstance(value, str) else ""
)
def test_a_response_field_reads_a_later_class_as_not_sure(where: str, hint: Any) -> None:
    assert _is_class_or_none(hint), f"{where} holds a class in a shape this test doesn't know how to check"
    adapter: TypeAdapter[Any] = TypeAdapter(hint)
    assert adapter.validate_python(LATER_CLASS) is FeatureClass.UNKNOWN, (
        f"{where} must be typed `ShownClass`, which reads a stored class as this version can (Decision 0035)."
    )
    assert adapter.validate_python(FeatureClass.MOAT.value) is FeatureClass.MOAT
