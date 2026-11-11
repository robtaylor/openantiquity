"""The errors of ingest that more than one module raises.

`IngestError` is shared by the runner and the adapters. It lives here, not
in `runner`, so that the adapters, which know nothing about our tables, can
raise it without importing the database layer. The others are raised by the
runner and by the reference loaders in `ingest/reference/`.
"""

from __future__ import annotations

from fieldclub.errors import AppError


class IngestError(AppError):
    code = "ingest_error"
    message = "The ingest run failed."


class InvalidRecordError(IngestError):
    """A connector yielded a record that breaks the rules for `records`."""

    code = "ingest_invalid_record"


class EmptyIngestError(IngestError):
    """A full run yielded nothing. Deleting every row on that evidence would be reckless."""

    code = "ingest_empty"


class ShrinkTooLargeError(IngestError):
    """A full run is missing so much of what is stored that upstream probably cut its answer short."""

    code = "ingest_shrink_too_large"


class IngestFailedError(IngestError):
    """Raised after a failed run has been recorded. `__cause__` is what went wrong."""

    code = "ingest_failed"

    def __init__(self, source_key: str, run_id: int, cause: BaseException) -> None:
        self.source_key = source_key
        self.run_id = run_id
        super().__init__(f"Ingest of {source_key} failed (run {run_id}): {type(cause).__name__}: {cause}")


__all__ = [
    "EmptyIngestError",
    "IngestError",
    "IngestFailedError",
    "InvalidRecordError",
    "ShrinkTooLargeError",
]
