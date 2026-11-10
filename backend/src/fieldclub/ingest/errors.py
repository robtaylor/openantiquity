"""The base error of ingest, shared by the runner and the adapters.

It lives here, not in `runner`, so that the adapters, which know nothing
about our tables, can raise it without importing the database layer.
"""

from __future__ import annotations

from fieldclub.errors import AppError


class IngestError(AppError):
    code = "ingest_error"
    message = "The ingest run failed."


__all__ = ["IngestError"]
